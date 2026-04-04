from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        description: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.description = description
        self.retry_after = retry_after


@dataclass(slots=True)
class TelegramUpdate:
    update_id: int
    chat_id: int
    text: str
    first_name: str | None
    message_id: int | None = None
    callback_query_id: str | None = None
    callback_data: str | None = None


class TelegramClient:
    def __init__(self, bot_token: str, timeout_seconds: int = 30) -> None:
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.timeout_seconds = timeout_seconds
        self.allowed_updates = json.dumps(["message", "edited_message", "callback_query"])

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[TelegramUpdate]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": self.allowed_updates}
        if offset is not None:
            payload["offset"] = offset

        raw_updates = self._request_json("getUpdates", payload=payload)
        result = raw_updates.get("result", [])
        updates: list[TelegramUpdate] = []
        for item in result:
            update = self.parse_update_payload(item)
            if update is not None:
                updates.append(update)
        return updates

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup, separators=(",", ":"))

        self._request_json("sendMessage", payload=payload)

    def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        filename: str = "alert-card.png",
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        fields: dict[str, str] = {"chat_id": str(chat_id)}
        if caption:
            fields["caption"] = caption
        if parse_mode:
            fields["parse_mode"] = parse_mode
        if reply_markup:
            fields["reply_markup"] = json.dumps(reply_markup, separators=(",", ":"))

        self._request_multipart_json(
            "sendPhoto",
            fields=fields,
            files=[("photo", filename, "image/png", photo_bytes)],
        )

    def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup, separators=(",", ":"))

        self._request_json("editMessageText", payload=payload)

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._request_json("answerCallbackQuery", payload=payload)

    def set_webhook(self, url: str, secret_token: str | None = None) -> None:
        payload: dict[str, Any] = {
            "url": url,
            "allowed_updates": self.allowed_updates,
            "drop_pending_updates": "false",
        }
        if secret_token:
            payload["secret_token"] = secret_token
        self._request_json("setWebhook", payload=payload)

    def delete_webhook(self, drop_pending_updates: bool = False) -> None:
        self._request_json(
            "deleteWebhook",
            payload={"drop_pending_updates": "true" if drop_pending_updates else "false"},
        )

    def clear_my_commands(self) -> None:
        self._request_json("deleteMyCommands", payload={})

    @staticmethod
    def parse_update_payload(item: dict[str, Any]) -> TelegramUpdate | None:
        callback_query = item.get("callback_query")
        if isinstance(callback_query, dict):
            message = callback_query.get("message") or {}
            chat = message.get("chat") or {}
            data = callback_query.get("data")
            if data and "id" in chat:
                user = callback_query.get("from") or {}
                return TelegramUpdate(
                    update_id=int(item["update_id"]),
                    chat_id=int(chat["id"]),
                    text="",
                    first_name=user.get("first_name"),
                    message_id=message.get("message_id"),
                    callback_query_id=str(callback_query.get("id", "")),
                    callback_data=str(data),
                )
            return None

        message = item.get("message") or item.get("edited_message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat") or {}
        text = message.get("text")
        if not text or "id" not in chat:
            return None
        user = message.get("from") or {}
        return TelegramUpdate(
            update_id=int(item["update_id"]),
            chat_id=int(chat["id"]),
            text=str(text),
            first_name=user.get("first_name"),
            message_id=message.get("message_id"),
        )

    def _request_multipart_json(
        self,
        method: str,
        fields: dict[str, str],
        files: list[tuple[str, str, str, bytes]],
    ) -> dict[str, Any]:
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body = bytearray()

        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        for field_name, filename, content_type, content in files:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8")
            )
            body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
            body.extend(content)
            body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        request = Request(
            f"{self.base_url}/{method}",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        return self._perform_request(method, request)

    def _request_json(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = urlencode(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/{method}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._perform_request(method, request)

    def _perform_request(self, method: str, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                raise TelegramApiError(f"Telegram request failed with HTTP {exc.code} for {method}") from exc

            description = data.get("description", f"HTTP {exc.code}")
            parameters = data.get("parameters") or {}
            retry_after = parameters.get("retry_after")
            parsed_retry_after: int | None = None
            if retry_after not in (None, ""):
                try:
                    parsed_retry_after = int(retry_after)
                except (TypeError, ValueError):
                    parsed_retry_after = None
            raise TelegramApiError(
                f"Telegram API error for {method}: {description}",
                error_code=data.get("error_code", exc.code),
                description=str(description),
                retry_after=parsed_retry_after,
            ) from exc
        except URLError as exc:
            raise TelegramApiError(f"Telegram request failed for {method}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise TelegramApiError(f"Telegram returned invalid JSON for {method}") from exc

        if not data.get("ok"):
            description = data.get("description", "Unknown Telegram API error")
            parameters = data.get("parameters") or {}
            retry_after = parameters.get("retry_after")
            parsed_retry_after: int | None = None
            if retry_after not in (None, ""):
                try:
                    parsed_retry_after = int(retry_after)
                except (TypeError, ValueError):
                    parsed_retry_after = None
            raise TelegramApiError(
                f"Telegram API error for {method}: {description}",
                error_code=data.get("error_code"),
                description=str(description),
                retry_after=parsed_retry_after,
            )
        return data
