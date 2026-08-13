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

from platform_support import PrivateFileError, secure_private_file, venv_python_path


DEFAULT_CONFIG = Path("~/.config/codex/feishu-automation/config.json").expanduser()
DEFAULT_DOWNLOAD_DIR = Path("~/Documents/Feishu").expanduser()
ROOT = Path(__file__).resolve().parents[1]
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
        secure_private_file(temporary)
        temporary.replace(path)
        secure_private_file(path)
    finally:
        os.umask(old_umask)


def validate_base_url(value: str) -> str:
    url = value.strip()
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise ConfigureError("Feishu tenant URL must be HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigureError("Feishu tenant URL must not contain credentials.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ConfigureError("Feishu tenant URL contains an invalid port.") from error
    if port not in (None, 443):
        raise ConfigureError("Feishu tenant URL must use the default HTTPS port.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ConfigureError("Feishu tenant URL must contain only its HTTPS origin.")
    if hostname != "feishu.cn" and hostname != "larksuite.com" and not hostname.endswith(
        (".feishu.cn", ".larksuite.com")
    ):
        raise ConfigureError("Feishu tenant URL must use feishu.cn or larksuite.com.")
    return f"https://{hostname}"


def derive_base_url_from_document_url(value: str) -> str:
    """Extract the tenant origin from a Feishu or Lark document URL."""
    url = value.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise ConfigureError("Feishu document URL must not contain credentials.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not any(
        resource in segments and segments.index(resource) + 1 < len(segments)
        for resource in ("wiki", "docx")
    ):
        raise ConfigureError(
            "Provide a complete Feishu Wiki or DocX URL containing /wiki/<token> "
            "or /docx/<token>."
        )
    try:
        port = parsed.port
    except ValueError as error:
        raise ConfigureError("Feishu document URL contains an invalid port.") from error
    authority = parsed.hostname or ""
    if port is not None:
        authority = f"{authority}:{port}"
    return validate_base_url(f"{parsed.scheme}://{authority}")


def register_mcp(
    *,
    root: Path = ROOT,
    platform_name: str | None = None,
    codex_executable: Path | str | None = None,
) -> None:
    platform_name = platform_name or os.name
    app_codex = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if codex_executable is not None:
        codex = str(codex_executable)
    elif platform_name != "nt" and app_codex.exists():
        codex = str(app_codex)
    else:
        codex = shutil.which("codex.exe") or shutil.which("codex")
    if not codex:
        raise ConfigureError(
            "Codex executable was not found. Install Codex CLI and ensure codex is on PATH."
        )
    venv_python = venv_python_path(root, platform_name)
    server = root / "scripts" / "feishu_mcp_server.py"
    if not venv_python.exists():
        raise ConfigureError(
            f"Virtual environment Python was not found: {venv_python}. "
            "Create .venv and install requirements first."
        )
    if not server.exists():
        raise ConfigureError(f"MCP server was not found: {server}")
    subprocess.run([codex, "mcp", "remove", "feishu_automation"], check=False)
    subprocess.run(
        [
            codex,
            "mcp",
            "add",
            "feishu_automation",
            "--",
            str(venv_python),
            str(server),
        ],
        cwd=root,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--download-dir", default=str(DEFAULT_DOWNLOAD_DIR))
    parser.add_argument("--folder-token", default="")
    parser.add_argument("--skip-mcp", action="store_true")
    args = parser.parse_args()
    try:
        app_id = input("Feishu App ID: ").strip()
        app_secret = getpass.getpass("Feishu App Secret: ").strip()
        webhook_url = getpass.getpass("Feishu Webhook URL: ").strip()
        document_url = ""
        if not args.base_url:
            document_url = input(
                "Any Feishu document URL from this organization: "
            ).strip()
        base_url = (
            validate_base_url(args.base_url)
            if args.base_url
            else derive_base_url_from_document_url(document_url)
        )
        if not app_id or not app_secret:
            raise ConfigureError("App ID and App Secret are required.")
        from send_webhook import validate_webhook_url

        config = {
            "app_id": app_id,
            "app_secret": app_secret,
            "webhook_url": validate_webhook_url(webhook_url),
            "base_url": base_url,
            "default_folder_token": args.folder_token.strip(),
            "download_dir": str(Path(args.download_dir).expanduser().resolve()),
        }
        Path(config["download_dir"]).mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG, config)
        if not args.skip_mcp:
            register_mcp()
        print(f"Configuration written to {DEFAULT_CONFIG}")
        return 0
    except (
        ConfigureError,
        PrivateFileError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"configure.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
