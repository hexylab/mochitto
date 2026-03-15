import json
import logging
import re
from dataclasses import dataclass, field

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from server.services.oauth import OAuthManager

logger = logging.getLogger(__name__)

RESPONSES_API_URL = "https://chatgpt.com/backend-api/codex/responses"
MODEL = "gpt-5.4"

SYSTEM_PROMPT_TEMPLATE = """\
ずんだもんの口調（語尾「のだ」「なのだ」）で応答するスマートホームアシスタント。
JSONのみ出力。説明文やコードブロックは不要。responseは1文で簡潔に。

intent: device_control / play_music / music_control / web_search / chat

デバイス: {devices_json}

device_control例:
{{"intent":"device_control","device_id":"ID","device_category":"light","action":"on","params":{{}},"response":"電気をつけたのだ"}}

action一覧:
- light: on, off, brightness_up, brightness_down
- aircon: on, off, set (params: temperature, mode=cool/heat/auto)
- curtain: open, close
- tv: power_on, power_off, volume_up, volume_down, channel_up, channel_down, mute
- DIYデバイス(typeが"DIY"で始まる): on/off のみ。他はparamsに button_name 指定

他のintent例:
{{"intent":"play_music","query":"米津玄師 Lemon","response":"再生するのだ"}}
{{"intent":"music_control","action":"stop","response":"止めたのだ"}}
{{"intent":"web_search","query":"明日の天気"}}
{{"intent":"chat","response":"おはようなのだ"}}
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
        self._devices_info = []
        for d in devices:
            info = {"id": d["deviceId"], "name": d["deviceName"]}
            # IR機器は remoteType、物理デバイスは deviceType
            info["type"] = d.get("remoteType", d.get("deviceType", ""))
            self._devices_info.append(info)

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
            "reasoning": {"effort": "low"},
            "max_output_tokens": 256,
        }

        if tools:
            body["tools"] = tools
            # Web検索は推論が必要なため effort を上げる
            body["reasoning"] = {"effort": "medium"}
            body["max_output_tokens"] = 512

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

    def _extract_json(self, text: str) -> dict | None:
        """LLM出力からJSONを抽出。コードブロックや前後のテキストに対応。"""
        # ```json ... ``` のコードブロックを除去
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if code_block:
            text = code_block.group(1)

        # テキスト中の最初の {...} を抽出
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return None

    async def classify_intent(self, text: str) -> IntentResult:
        response_data = await self._call_responses_api(
            user_input=text,
            system_prompt=self._build_system_prompt(),
            use_structured=True,
        )
        raw_text = self._extract_text(response_data)
        logger.debug("LLM生出力: %s", raw_text)

        parsed = self._extract_json(raw_text)
        if parsed:
            try:
                return IntentResult.from_dict(parsed)
            except KeyError as e:
                logger.warning("LLM出力のフィールド不足: %s", e)

        logger.warning("LLM出力のパースに失敗: %s", raw_text[:200])
        return IntentResult(
            intent="chat",
            response="うまく理解できなかったのだ、もう一度言ってほしいのだ",
        )

    async def web_search(self, query: str) -> str:
        response_data = await self._call_responses_api(
            user_input=query,
            system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
            tools=[{"type": "web_search"}],
            use_structured=False,
        )
        return self._extract_text(response_data)
