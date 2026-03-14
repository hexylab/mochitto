import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from server.services.oauth import OAuthManager

AUTH_ENDPOINT = "https://auth.openai.com/oauth/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


@pytest.fixture
def auth_file(tmp_path: Path) -> Path:
    return tmp_path / "auth.json"


@pytest.fixture
def valid_token_data() -> dict:
    return {
        "access_token": "test_access_token",
        "refresh_token": "rt_test_refresh",
        "expires_at": time.time() + 3600,
        "client_id": CLIENT_ID,
    }


@pytest.fixture
def expired_token_data() -> dict:
    return {
        "access_token": "expired_token",
        "refresh_token": "rt_test_refresh",
        "expires_at": time.time() - 100,
        "client_id": CLIENT_ID,
    }


def test_pkce_code_verifier_length():
    manager = OAuthManager(auth_path=Path("/tmp/test_auth.json"))
    verifier = manager._generate_code_verifier()
    assert 43 <= len(verifier) <= 128


def test_pkce_challenge_is_s256():
    manager = OAuthManager(auth_path=Path("/tmp/test_auth.json"))
    verifier = manager._generate_code_verifier()
    challenge = manager._generate_code_challenge(verifier)
    assert len(challenge) > 0
    assert "+" not in challenge  # URL-safe base64


def test_load_valid_token(auth_file: Path, valid_token_data: dict):
    auth_file.write_text(json.dumps(valid_token_data))
    manager = OAuthManager(auth_path=auth_file)
    assert manager._access_token == "test_access_token"
    assert manager.is_authenticated


def test_load_no_file(auth_file: Path):
    manager = OAuthManager(auth_path=auth_file)
    assert not manager.is_authenticated


async def test_get_token_returns_valid(auth_file: Path, valid_token_data: dict):
    auth_file.write_text(json.dumps(valid_token_data))
    manager = OAuthManager(auth_path=auth_file)
    token = await manager.get_token()
    assert token == "test_access_token"


async def test_get_token_refreshes_expired(auth_file: Path, expired_token_data: dict):
    auth_file.write_text(json.dumps(expired_token_data))
    manager = OAuthManager(auth_path=auth_file)

    new_token_data = {
        "access_token": "new_access_token",
        "refresh_token": "rt_new_refresh",
        "expires_in": 3600,
    }

    with patch.object(manager, "_refresh_token", new_callable=AsyncMock, return_value=new_token_data):
        token = await manager.get_token()
        assert token == "new_access_token"


def test_authorize_url_contains_required_params(auth_file: Path):
    manager = OAuthManager(auth_path=auth_file)
    verifier = manager._generate_code_verifier()
    url = manager.get_authorize_url("http://localhost:8080/callback", verifier)
    assert "client_id=" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "scope=" in url
    assert "redirect_uri=" in url
