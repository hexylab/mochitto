import json
import logging
from dataclasses import dataclass, field

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from server.services.oauth import OAuthManager

logger = logging.getLogger(__name__)

RESPONSES_API_URL = "https://chatgpt.com/backend-api/codex/responses"
MODEL = "gpt-5.4"

SYSTEM_PROMPT_TEMPLATE = """\
あなたはスマートホームアシスタント「モチット」です。ずんだもんの口調（語尾に「のだ」「なのだ」）で応答してください。

ユーザーの発話を以下のintentに分類し、JSON形式（json）で出力してください。

## Intent一覧
- device_control: デバイス操作（照明、エアコン、カーテン、テレビ）
- play_music: 音楽再生
- music_control: 再生中の音楽制御（停止、一時停止、再開、音量調整）
- web_search: Web検索
- chat: 雑談・質問

## 操作可能なデバイス
{devices_json}

## 出力形式
各intentに応じたJSONを出力してください。responseフィールドにはずんだもん口調の応答を含めてください。
device_controlの場合、device_idフィールドに操作対象のデバイスIDを必ず含めてください。
"""

WEB_SEARCH_SYSTEM_PROMPT = """\
あなたはスマートホームアシスタント「モチット」です。
ずんだもんの口調（語尾に「のだ」「なのだ」）で、検索結果を簡潔に要約して応答してください。
3文以内で要点をまとめてください。
"""


@dataclass
class IntentResult:
    intent: str
    response: str | None = None
    device_type: str | None = None
    device_category: str | None = None
    action: str | None = None
    params: dict = field(default_factory=dict)
    query: str | None = None
    device_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "IntentResult":
        return cls(
            intent=data["intent"],
            response=data.get("response"),
            device_type=data.get("device_type"),
            device_category=data.get("device_category"),
            action=data.get("action"),
            params=data.get("params", {}),
            query=data.get("query"),
            device_id=data.get("device_id"),
        )


class LLMService:
    def __init__(self, oauth_manager: OAuthManager, devices_info: list[dict]):
        self._oauth = oauth_manager
        self._devices_info = devices_info

    def update_devices(self, devices: list[dict]) -> None:
        self._devices_info = [
            {"id": d["deviceId"], "name": d["deviceName"], "type": d.get("deviceType", "")}
            for d in devices
        ]

    def _build_system_prompt(self) -> str:
        devices_json = json.dumps(self._devices_info, ensure_ascii=False, indent=2)
        return SYSTEM_PROMPT_TEMPLATE.format(devices_json=devices_json)

    async def _call_responses_api(
        self,
        user_input: str,
        system_prompt: str,
        tools: list[dict] | None = None,
        use_structured: bool = False,
    ) -> dict:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(1),
            retry=retry_if_exception_type(httpx.HTTPError),
        )
        async def _do_request() -> dict:
            return await self.__call_api(user_input, system_prompt, tools, use_structured)

        return await _do_request()

    async def __call_api(
        self,
        user_input: str,
        system_prompt: str,
        tools: list[dict] | None = None,
        use_structured: bool = False,
    ) -> dict:
        token = await self._oauth.get_token()

        body: dict = {
            "model": MODEL,
            "store": False,
            "stream": True,
            "instructions": system_prompt,
            "input": [
                {"role": "user", "content": user_input},
            ],
        }

        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                RESPONSES_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    logger.error("LLM API エラー %d: %s", resp.status_code, error_body.decode())
                    resp.raise_for_status()

                # SSE ストリームからレスポンスを組み立てる
                full_response = None
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                        if event.get("type") == "response.completed":
                            full_response = event.get("response", {})
                    except json.JSONDecodeError:
                        continue

                if full_response is None:
                    raise RuntimeError("LLM API からレスポンスを取得できませんでした")
                return full_response

    def _extract_text(self, response_data: dict) -> str:
        for output in response_data.get("output", []):
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        return content["text"]
        return ""

    async def classify_intent(self, text: str) -> IntentResult:
        response_data = await self._call_responses_api(
            user_input=text,
            system_prompt=self._build_system_prompt(),
            use_structured=True,
        )
        raw_text = self._extract_text(response_data)

        try:
            parsed = json.loads(raw_text)
            return IntentResult.from_dict(parsed)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("LLM出力のパースに失敗: %s", e)
            return IntentResult(intent="chat", response=raw_text)

    async def web_search(self, query: str) -> str:
        response_data = await self._call_responses_api(
            user_input=query,
            system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
            tools=[{"type": "web_search"}],
            use_structured=False,
        )
        return self._extract_text(response_data)
