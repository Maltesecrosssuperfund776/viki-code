from __future__ import annotations

from fastapi.testclient import TestClient

from viki.api.server import create_app


class FakeProvider:
    def validate_config(self):
        return True

    def get_available_models(self):
        return ["fake/reasoning", "fake/coding"]

    async def complete(self, model, messages, **kwargs):
        system = messages[0]["content"].lower()
        if "planning swarm" in system:
            content = '''{
              "goal": "create a hello file",
              "summary": "single task plan",
              "tasks": [
                {
                  "id": "task-1",
                  "title": "write hello",
                  "objective": "write a hello.txt file",
                  "target_files": ["hello.txt"],
                  "deliverables": ["hello.txt"],
                  "commands": [],
                  "skill_requests": []
                }
              ],
              "testing_commands": [],
              "acceptance_criteria": ["hello.txt exists"]
            }'''
        elif "coding swarm" in system:
            content = '''{
              "task_id": "task-1",
              "summary": "created file",
              "file_operations": [
                {"mode": "write", "path": "hello.txt", "content": "hello from viki\\n"}
              ],
              "commands": [],
              "skill_requests": [],
              "notes": []
            }'''
        elif "testing swarm" in system:
            content = '''{
              "summary": "no-op tests",
              "commands": [{"command": "python -c \\\"print('tests ok')\\\"", "timeout": 30}],
              "expected_outputs": ["tests ok"]
            }'''
        elif "debugging swarm" in system:
            content = '''{
              "summary": "no repair needed",
              "root_cause": "none",
              "file_operations": [],
              "commands": [],
              "notes": []
            }'''
        else:
            content = '''{
              "summary": "security ok",
              "issues": [],
              "recommended_commands": []
            }'''
        return {
            "content": content,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": model or "fake",
            "provider": "fake",
        }


class StubTelegramClient:
    def __init__(self) -> None:
        self.enabled = True
        self.secret = "secret"
        self.messages: list[dict] = []

    def validate_secret(self, header_value: str | None) -> bool:
        return header_value == self.secret

    def is_allowed_chat(self, chat_id: str) -> bool:
        return chat_id == "123"

    def send_message(self, chat_id: str, text: str, reply_to_message_id: int | None = None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id})
        return {"ok": True}


class StubWhatsAppClient:
    def __init__(self) -> None:
        self.enabled = True
        self.messages: list[dict] = []

    def validate_signature(self, url: str, params: dict, signature: str | None) -> bool:
        return signature == "signed"

    def is_allowed_sender(self, sender: str) -> bool:
        return sender == "whatsapp:+15550001111"

    def send_message(self, to_number: str, text: str):
        self.messages.append({"to": to_number, "text": text})
        return {"ok": True}


def test_telegram_webhook_executes_run_and_sends_summary(tmp_path):
    app = create_app(tmp_path, provider=FakeProvider())
    server = app.state.viki_server
    server.telegram = StubTelegramClient()
    client = TestClient(app)

    response = client.post(
        "/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={
            "message": {
                "message_id": 9,
                "text": "create hello file",
                "chat": {"id": 123},
                "from": {"username": "laraib", "first_name": "Laraib"},
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert len(server.telegram.messages) >= 2
    assert "accepted task" in server.telegram.messages[0]["text"].lower()
    assert "status: completed" in server.telegram.messages[-1]["text"].lower()


def test_telegram_help_command_returns_inline_response(tmp_path):
    app = create_app(tmp_path, provider=FakeProvider())
    server = app.state.viki_server
    server.telegram = StubTelegramClient()
    client = TestClient(app)

    response = client.post(
        "/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"message_id": 1, "text": "/help", "chat": {"id": 123}}},
    )

    assert response.status_code == 200
    assert response.json()["command"] is True
    assert "commands:" in server.telegram.messages[-1]["text"].lower()


def test_whatsapp_webhook_executes_run_and_returns_twiml(tmp_path):
    app = create_app(tmp_path, provider=FakeProvider())
    server = app.state.viki_server
    server.whatsapp = StubWhatsAppClient()
    client = TestClient(app)

    response = client.post(
        "/integrations/whatsapp/webhook",
        headers={"X-Twilio-Signature": "signed", "Content-Type": "application/x-www-form-urlencoded"},
        data={"From": "whatsapp:+15550001111", "Body": "create hello file", "ProfileName": "Laraib", "MessageSid": "SM123"},
    )

    assert response.status_code == 200
    assert "Session" in response.text
    assert server.whatsapp.messages
    assert "status: completed" in server.whatsapp.messages[-1]["text"].lower()


def test_whatsapp_status_command_returns_inline_twiml(tmp_path):
    app = create_app(tmp_path, provider=FakeProvider())
    server = app.state.viki_server
    server.whatsapp = StubWhatsAppClient()
    client = TestClient(app)

    response = client.post(
        "/integrations/whatsapp/webhook",
        headers={"X-Twilio-Signature": "signed", "Content-Type": "application/x-www-form-urlencoded"},
        data={"From": "whatsapp:+15550001111", "Body": "/approvals", "ProfileName": "Laraib", "MessageSid": "SM124"},
    )

    assert response.status_code == 200
    assert "No pending approvals" in response.text
