#!/usr/bin/env python3
"""Send text or a linked summary to a Feishu custom-bot webhook."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("~/.config/codex/feishu-automation/config.json").expanduser()
WEBHOOK_HOSTS = {"open.feishu.cn", "open.larksuite.com"}
MAX_TEXT_CHARS = 20_000


class WebhookError(RuntimeError):
    pass


def config_path() -> Path:
    return Path(os.environ.get("FEISHU_AUTOMATION_CONFIG", str(DEFAULT_CONFIG))).expanduser()


def validate_webhook_url(value: str) -> str:
    url = value.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in WEBHOOK_HOSTS:
        raise WebhookError("webhook_url must be an HTTPS Feishu/Lark Open Platform URL.")
    if not parsed.path.startswith("/open-apis/bot/v2/hook/"):
        raise WebhookError("webhook_url must point to /open-apis/bot/v2/hook/<token>.")
    return url


def load_webhook_url(path: Path | None = None) -> str:
    path = (path or config_path()).expanduser()
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError as error:
        raise WebhookError(f"Feishu config does not exist: {path}") from error
    if mode & 0o077:
        raise WebhookError(f"Feishu config must have permission 600: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WebhookError(f"Unable to read Feishu config {path}: {error}") from error
    return validate_webhook_url(str(data.get("webhook_url", "")))


def build_payload(
    text: str,
    *,
    title: str = "",
    link_url: str = "",
    link_text: str = "阅读全文",
) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise WebhookError("message text must not be empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise WebhookError(f"message exceeds the {MAX_TEXT_CHARS}-character limit.")

    if not title and not link_url:
        return {"msg_type": "text", "content": {"text": text}}

    elements: list[list[dict[str, Any]]] = [[{"tag": "text", "text": text}]]
    if link_url:
        parsed = urllib.parse.urlparse(link_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise WebhookError("link_url must be an HTTP or HTTPS URL.")
        elements.append([{"tag": "a", "text": link_text or "打开链接", "href": link_url}])
    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title.strip(),
                    "content": elements,
                }
            }
        },
    }


def send_payload(webhook_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        validate_webhook_url(webhook_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise WebhookError(f"Feishu webhook returned HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise WebhookError(f"Unable to reach Feishu webhook: {error.reason}") from error
    try:
        result = json.loads(body)
    except json.JSONDecodeError as error:
        raise WebhookError("Feishu webhook returned a non-JSON response.") from error
    code = result.get("code", result.get("StatusCode", 0))
    if code != 0:
        message = result.get("msg", result.get("StatusMessage", "unknown error"))
        raise WebhookError(f"Feishu webhook rejected the message: code={code}, msg={message}")
    return result


def read_message(args: argparse.Namespace) -> str:
    if args.message is not None:
        return args.message
    if args.file is not None:
        return Path(args.file).expanduser().read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise WebhookError("Use --message, --file, or pipe message text through stdin.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message")
    parser.add_argument("--file")
    parser.add_argument("--title", default="")
    parser.add_argument("--link-url", default="")
    parser.add_argument("--link-text", default="阅读全文")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        payload = build_payload(
            read_message(args),
            title=args.title,
            link_url=args.link_url,
            link_text=args.link_text,
        )
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        result = send_payload(load_webhook_url(), payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (WebhookError, OSError) as error:
        print(f"send_webhook.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
