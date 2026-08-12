#!/usr/bin/env python3
"""Publish a Markdown daily report to Feishu DocX and notify a webhook group."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

from feishu_mcp_server import FeishuClient
from platform_support import PrivateFileError, require_private_file
from send_webhook import build_payload, send_payload, validate_webhook_url


DEFAULT_CONFIG = Path("~/.config/codex/feishu-automation/config.json").expanduser()


class DailyReportError(RuntimeError):
    pass


def config_path() -> Path:
    return Path(os.environ.get("FEISHU_AUTOMATION_CONFIG", str(DEFAULT_CONFIG))).expanduser()


def load_config() -> dict[str, Any]:
    path = config_path()
    try:
        require_private_file(path)
    except PrivateFileError as error:
        raise DailyReportError(str(error)) from error
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DailyReportError(f"Unable to read Feishu config {path}: {error}") from error
    required = ("app_id", "app_secret", "base_url", "webhook_url")
    missing = [key for key in required if not str(config.get(key, "")).strip()]
    if missing:
        raise DailyReportError(f"Feishu config is missing: {', '.join(missing)}")
    return config


def extract_highlights(markdown: str) -> list[str]:
    in_overview = False
    highlights: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if re.match(r"^#{2,3}\s+今日(?:速览|摘要|三条)", stripped):
            in_overview = True
            continue
        if in_overview and stripped.startswith("#"):
            break
        if in_overview:
            match = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", stripped)
            if match:
                highlights.append(match.group(1).strip())
                if len(highlights) == 3:
                    break
    return highlights


def publish_report(
    config: dict[str, Any],
    title: str,
    markdown: str,
    *,
    client: Any | None = None,
    webhook_sender: Callable[[str, dict[str, Any]], dict[str, Any]] = send_payload,
) -> dict[str, Any]:
    markdown = markdown.strip()
    if not markdown:
        raise DailyReportError("The report is empty.")
    client = client or FeishuClient(config["app_id"], config["app_secret"])
    document = client.create_document(
        title, str(config.get("default_folder_token", ""))
    )
    document_id = str(document["document_id"])
    first_level_ids, blocks = client.convert_markdown(markdown)
    inserted = client.insert_descendants(document_id, first_level_ids, blocks, index=0)
    client.set_tenant_link_readable(document_id)
    base_url = str(config["base_url"]).rstrip("/")
    document_url = f"{base_url}/docx/{document_id}"
    highlights = extract_highlights(markdown)
    summary = "\n".join(
        f"{index}. {item}" for index, item in enumerate(highlights, start=1)
    ) or "完整日报已生成。"
    payload = build_payload(
        summary,
        title=title,
        link_url=document_url,
        link_text="阅读完整日报",
    )
    webhook_result = webhook_sender(
        validate_webhook_url(str(config["webhook_url"])), payload
    )
    return {
        "document_id": document_id,
        "document_url": document_url,
        "document_revision_id": inserted.get("document_revision_id"),
        "highlight_count": len(highlights),
        "webhook_code": webhook_result.get("code", webhook_result.get("StatusCode", 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    try:
        markdown = Path(args.file).expanduser().read_text(encoding="utf-8")
        result = publish_report(load_config(), args.title, markdown)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (DailyReportError, OSError, RuntimeError) as error:
        print(f"publish_daily_report.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
