#!/usr/bin/env python3
"""Forward each completed Codex turn's final assistant reply to Feishu."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from send_webhook import load_webhook_url, send_payload


DEFAULT_CONFIG = Path("~/.config/codex/feishu-automation/config.json").expanduser()
MAX_NOTIFICATION_CHARS = 20_000
TRUNCATION_MARKER = "\n\n[消息过长，已截断]"
PREVIOUS_NOTIFIER_TIMEOUT_SECONDS = 15


def build_notification_payload(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "agent-turn-complete":
        return None

    reply = str(event.get("last-assistant-message") or "").strip()
    if not reply:
        return None

    cwd = str(event.get("cwd") or "").strip()
    project = os.path.basename(os.path.normpath(cwd)) if cwd else "未知项目"
    prefix = f"Codex 最终回复\n项目：{project}\n\n"
    if len(prefix) + len(reply) > MAX_NOTIFICATION_CHARS:
        available = max(
            0,
            MAX_NOTIFICATION_CHARS - len(prefix) - len(TRUNCATION_MARKER),
        )
        reply = reply[:available] + TRUNCATION_MARKER

    return {
        "msg_type": "text",
        "content": {"text": prefix + reply},
    }


def dispatch_event(
    raw_event: str,
    *,
    webhook_loader: Callable[[], str] | None = None,
    sender: Callable[[str, dict[str, Any]], Any] = send_payload,
) -> bool:
    try:
        event = json.loads(raw_event)
    except json.JSONDecodeError:
        return False
    if not isinstance(event, dict):
        return False

    payload = build_notification_payload(event)
    if payload is None:
        return False

    loader = webhook_loader or (lambda: load_webhook_url(DEFAULT_CONFIG))
    sender(loader(), payload)
    return True


def parse_previous_notifier(value: str) -> list[str]:
    if not value:
        return []
    try:
        command = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(command, list) or not command:
        return []
    if not all(isinstance(item, str) and item for item in command):
        return []
    return command


def forward_previous_notifier(
    command: Sequence[str],
    raw_event: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    if not command:
        return
    try:
        runner(
            [*command, raw_event],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PREVIOUS_NOTIFIER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-notifier-json", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("event_json")
    args = parser.parse_args(argv)

    raw_event = args.event_json
    previous_notifier = parse_previous_notifier(args.previous_notifier_json)
    if args.dry_run:
        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            return 0
        if not isinstance(event, dict):
            return 0
        payload = build_notification_payload(event)
        if payload is not None:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    forward_previous_notifier(previous_notifier, raw_event)

    try:
        dispatch_event(raw_event)
    except Exception:
        # Notification delivery must never fail the completed Codex turn.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
