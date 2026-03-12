from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import request as urlrequest

from ..config import settings


@dataclass(frozen=True)
class TelegramUpdate:
    chat_id: str
    text: str
    message_id: Optional[int] = None
    username: str = ""
    first_name: str = ""

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> Optional["TelegramUpdate"]:
        message = payload.get("message") or payload.get("edited_message") or payload.get("channel_post")
        if not isinstance(message, dict):
            return None
        text = (message.get("text") or message.get("caption") or "").strip()
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return None
        return cls(
            chat_id=str(chat_id),
            text=text,
            message_id=message.get("message_id"),
            username=str(user.get("username") or ""),
            first_name=str(user.get("first_name") or ""),
        )


class TelegramBotClient:
    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.secret = settings.telegram_webhook_secret
        self.reply_limit = settings.telegram_reply_max_chars
        self.allowed_chat_ids = {item.strip() for item in settings.telegram_allowed_chat_ids.split(",") if item.strip()}

    @property
    def enabled(self) -> bool:
        return bool(settings.telegram_enabled and self.token)

    def validate_secret(self, header_value: Optional[str]) -> bool:
        if not self.secret:
            return True
        return bool(header_value) and header_value == self.secret

    def is_allowed_chat(self, chat_id: str) -> bool:
        return not self.allowed_chat_ids or chat_id in self.allowed_chat_ids

    def _api_call(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("telegram bot token is not configured")
        data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def send_message(self, chat_id: str, text: str, reply_to_message_id: int | None = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[: self.reply_limit],
            "disable_web_page_preview": True,
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return self._api_call("sendMessage", payload)
