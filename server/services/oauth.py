import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

AUTH_ENDPOINT = "https://auth.openai.com/oauth/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPE = "openid profile email offline_access"
REFRESH_MARGIN_SECONDS = 300


class OAuthError(RuntimeError):
    """OAuth認証関連のエラー"""
    pass


class OAuthManager:
    def __init__(self, auth_path: Path = Path("auth.json")):
        self._auth_path = auth_path
        self._access_token: str | None = None
        self._refresh_token_value: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()
        self._load_token()

    @staticmethod
    def get_redirect_uri() -> str:
        return REDIRECT_URI

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def _load_token(self) -> None:
        if not self._auth_path.exists():
            return
        data = json.loads(self._auth_path.read_text())
        self._access_token = data.get("access_token")
        self._refresh_token_value = data.get("refresh_token")
        self._expires_at = data.get("expires_at", 0)

    def _save_token(self) -> None:
        data = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token_value,
            "expires_at": self._expires_at,
            "client_id": CLIENT_ID,
        }
        self._auth_path.write_text(json.dumps(data, indent=2))

    def _generate_code_verifier(self) -> str:
        return secrets.token_urlsafe(64)

    def _generate_code_challenge(self, verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def _is_token_expired(self) -> bool:
        return time.time() >= (self._expires_at - REFRESH_MARGIN_SECONDS)

    async def _refresh_token(self) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    TOKEN_ENDPOINT,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token_value,
                        "client_id": CLIENT_ID,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            raise OAuthError(f"トークンリフレッシュに失敗: {e}") from e

    async def get_token(self) -> str:
        async with self._lock:
            if self._access_token and not self._is_token_expired():
                return self._access_token

            if not self._refresh_token_value:
                raise OAuthError(
                    "認証されていません。サーバーを再起動して認証を行ってください。"
                )

            logger.info("OAuthトークンをリフレッシュ中...")
            token_data = await self._refresh_token()
            self._access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self._refresh_token_value = token_data["refresh_token"]
            self._expires_at = time.time() + token_data.get("expires_in", 3600)
            self._save_token()
            logger.info("OAuthトークンのリフレッシュ完了")
            return self._access_token

    def get_authorize_url(self, redirect_uri: str, code_verifier: str) -> str:
        code_challenge = self._generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)
        self._oauth_state = state
        params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": SCOPE,
            "state": state,
            "codex_cli_simplified_flow": "true",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": CLIENT_ID,
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        self._access_token = token_data["access_token"]
        self._refresh_token_value = token_data.get("refresh_token")
        self._expires_at = time.time() + token_data.get("expires_in", 3600)
        self._save_token()
        logger.info("OAuth認証完了。トークンを保存しました。")
