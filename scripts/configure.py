#!/usr/bin/env python3
"""Create the private Feishu Automation config and optionally register its MCP server."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("~/.config/codex/feishu-automation/config.json").expanduser()
DEFAULT_DOWNLOAD_DIR = Path("~/Documents/Feishu").expanduser()
ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
SERVER = ROOT / "scripts" / "feishu_mcp_server.py"


class ConfigureError(RuntimeError):
    pass


def save_config(path: Path, config: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    old_umask = os.umask(0o077)
    try:
        temporary.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        os.umask(old_umask)


def validate_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise ConfigureError("Feishu tenant URL must be HTTPS.")
    if hostname != "feishu.cn" and hostname != "larksuite.com" and not hostname.endswith(
        (".feishu.cn", ".larksuite.com")
    ):
        raise ConfigureError("Feishu tenant URL must use feishu.cn or larksuite.com.")
    return url


def register_mcp() -> None:
    app_codex = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    codex = str(app_codex) if app_codex.exists() else shutil.which("codex")
    if not codex:
        raise ConfigureError("Codex executable was not found.")
    if not VENV_PYTHON.exists():
        raise ConfigureError("Install dependencies first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt")
    subprocess.run([codex, "mcp", "remove", "feishu_automation"], check=False)
    subprocess.run(
        [
            codex,
            "mcp",
            "add",
            "feishu_automation",
            "--",
            str(VENV_PYTHON),
            str(SERVER),
        ],
        cwd=ROOT,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id")
    parser.add_argument("--webhook-url")
    parser.add_argument("--base-url")
    parser.add_argument("--download-dir", default=str(DEFAULT_DOWNLOAD_DIR))
    parser.add_argument("--folder-token", default="")
    parser.add_argument("--skip-mcp", action="store_true")
    args = parser.parse_args()
    try:
        app_id = (args.app_id or input("Feishu App ID: ")).strip()
        app_secret = getpass.getpass("Feishu App Secret: ").strip()
        webhook_url = (args.webhook_url or getpass.getpass("Feishu Webhook URL: ")).strip()
        base_url = (args.base_url or input("Feishu tenant URL (for example https://example.feishu.cn): ")).strip()
        if not app_id or not app_secret:
            raise ConfigureError("App ID and App Secret are required.")
        from send_webhook import validate_webhook_url

        config = {
            "app_id": app_id,
            "app_secret": app_secret,
            "webhook_url": validate_webhook_url(webhook_url),
            "base_url": validate_base_url(base_url),
            "default_folder_token": args.folder_token.strip(),
            "download_dir": str(Path(args.download_dir).expanduser().resolve()),
        }
        Path(config["download_dir"]).mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG, config)
        if not args.skip_mcp:
            register_mcp()
        print(f"Configuration written to {DEFAULT_CONFIG}")
        return 0
    except (ConfigureError, OSError, subprocess.CalledProcessError) as error:
        print(f"configure.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
