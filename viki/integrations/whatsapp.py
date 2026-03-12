from __future__ import annotations

import base64
import hmac
import xml.sax.saxutils as saxutils
from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Dict, Optional
from urllib import parse as urlparse
from urllib import request as urlrequest

from ..config import settings


@dataclass(frozen=True)
class WhatsAppInboundMessage:
    sender: str
    body: str
    profile_name: str = ""
    message_sid: str = ""

    @classmethod
    def from_form(cls, form: Dict[str, Any]) -> Optional["WhatsAppInboundMessage"]:
        sender = str(form.get("From") or "").strip()
        body = str(form.get("Body") or "").strip()
        if not sender:
            return None
        return cls(
            sender=sender,
            body=body,
            profile_name=str(form.get("ProfileName") or ""),
            message_sid=str(form.get("MessageSid") or ""),
        )


def twiml_message(text: str) -> str:
    escaped = saxutils.escape(text)
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped}</Message></Response>'


class TwilioWhatsAppClient:
    def __init__(self) -> None:
        self.account_sid = settings.whatsapp_account_sid
        self.auth_token = settings.whatsapp_auth_token
        self.from_number = settings.whatsapp_from_number
        self.reply_limit = settings.whatsapp_reply_max_chars
        self.allowed_senders = {item.strip().lower() for item in settings.whatsapp_allowed_senders.split(",") if item.strip()}

    @property
    def enabled(self) -> bool:
        return bool(settings.whatsapp_enabled and self.account_sid and self.auth_token and self.from_number)

    def is_allowed_sender(self, sender: str) -> bool:
        return not self.allowed_senders or sender.strip().lower() in self.allowed_senders

    def validate_signature(self, url: str, params: Dict[str, Any], signature: Optional[str]) -> bool:
        if not settings.whatsapp_validate_signature:
            return True
        if not signature or not self.auth_token:
            return False
        material = (settings.whatsapp_webhook_url or url) + "".join(f"{key}{params[key]}" for key in sorted(params))
        digest = hmac.new(self.auth_token.encode("utf-8"), material.encode("utf-8"), sha1).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    def send_message(self, to_number: str, text: str) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("twilio whatsapp is not configured")
        payload = urlparse.urlencode(
            {
                "From": self.from_number,
                "To": to_number,
                "Body": text[: self.reply_limit],
            }
        ).encode("utf-8")
        req = urlrequest.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json",
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode("utf-8")).decode("utf-8"),
            },
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=30) as response:
            return {"status": response.status, "body": response.read().decode("utf-8")}
