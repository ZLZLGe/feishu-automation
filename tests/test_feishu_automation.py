from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return {
            "code": 0,
            "data": {
                "document": {
                    "document_id": "docx-created",
                    "revision_id": 1,
                    "title": "Daily report",
                }
            },
        }


class PlatformSupportTests(unittest.TestCase):
    def setUp(self) -> None:
        support_path = ROOT / "scripts" / "platform_support.py"
        self.assertTrue(
            support_path.exists(),
            "Windows support requires scripts/platform_support.py",
        )
        self.platform = load_module(
            "feishu_platform_support_for_test", "scripts/platform_support.py"
        )

    def test_selects_platform_specific_virtualenv_python(self) -> None:
        root = Path("/work/feishu-automation")
        self.assertEqual(
            self.platform.venv_python_path(root, platform_name="nt"),
            root / ".venv" / "Scripts" / "python.exe",
        )
        self.assertEqual(
            self.platform.venv_python_path(root, platform_name="posix"),
            root / ".venv" / "bin" / "python",
        )

    def test_posix_private_file_rejects_group_or_world_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{}", encoding="utf-8")
            os.chmod(path, 0o644)
            with self.assertRaises(self.platform.PrivateFileError):
                self.platform.require_private_file(path, platform_name="posix")

    @unittest.skipUnless(os.name == "nt", "Windows ACL test")
    def test_windows_private_file_acl_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(self.platform.PrivateFileError):
                self.platform.require_private_file(path, platform_name="nt")
            self.platform.secure_private_file(path, platform_name="nt")
            self.platform.require_private_file(path, platform_name="nt")


class DocumentClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = load_module("feishu_server_for_test", "scripts/feishu_mcp_server.py")

    def test_create_document_builds_docx_request(self) -> None:
        client = RecordingClient()
        document = client_module(self.server, client).create_document(
            "Daily report", "folder-token"
        )
        self.assertEqual(document["document_id"], "docx-created")
        method, path, kwargs = client.calls[0]
        self.assertEqual((method, path), ("POST", "/docx/v1/documents"))
        self.assertEqual(
            kwargs["body"],
            {"title": "Daily report", "folder_token": "folder-token"},
        )

    def test_create_document_rejects_blank_title(self) -> None:
        with self.assertRaises(self.server.FeishuAutomationError):
            self.server.validate_document_title("  ")

    def test_default_paths_are_portable(self) -> None:
        self.assertEqual(
            self.server.DEFAULT_CONFIG,
            Path("~/.config/codex/feishu-automation/config.json").expanduser(),
        )
        self.assertEqual(
            self.server.DEFAULT_DOWNLOAD_DIR,
            Path("~/Documents/Feishu").expanduser(),
        )

    def test_create_folder_builds_drive_request(self) -> None:
        class FolderClient(self.server.FeishuClient):
            def __init__(self) -> None:
                pass

            def request(self, method: str, path: str, **kwargs: object):
                self.recorded = (method, path, kwargs)
                return {"code": 0, "data": {"token": "folder-created", "url": "https://example.feishu.cn/drive/folder-created"}}

        client = FolderClient()
        folder = client.create_folder("AI Daily", "parent-folder")
        self.assertEqual(folder["token"], "folder-created")
        self.assertEqual(client.recorded[0:2], ("POST", "/drive/v1/files/create_folder"))
        self.assertEqual(
            client.recorded[2]["body"],
            {"name": "AI Daily", "folder_token": "parent-folder"},
        )

    def test_upload_attachment_runs_block_upload_replace_sequence(self) -> None:
        class AttachmentClient(self.server.FeishuClient):
            def __init__(self) -> None:
                pass

            def create_file_block(self, document_id: str, parent_block_id: str, index: int):
                self.created = (document_id, parent_block_id, index)
                return "file-block", 4

            def upload_media(self, file_path: Path, parent_node: str, document_id: str):
                self.uploaded = (file_path, parent_node, document_id)
                return "file-token"

            def replace_file(self, document_id: str, block_id: str, file_token: str, revision_id: int):
                self.replaced = (document_id, block_id, file_token, revision_id)
                return 5

        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "report.csv"
            file_path.write_text("a,b\n1,2\n", encoding="utf-8")
            client = AttachmentClient()
            result = client.attach_file("document-id", file_path, "document-id", -1)

        self.assertEqual(result["file_token"], "file-token")
        self.assertEqual(client.created, ("document-id", "document-id", -1))
        self.assertEqual(client.uploaded[1:], ("file-block", "document-id"))
        self.assertEqual(client.replaced, ("document-id", "file-block", "file-token", 4))

    def test_sets_tenant_link_read_permission(self) -> None:
        class PermissionClient(self.server.FeishuClient):
            def __init__(self) -> None:
                pass

            def request(self, method: str, path: str, **kwargs: object):
                self.recorded = (method, path, kwargs)
                return {"code": 0, "data": {}}

        client = PermissionClient()
        client.set_tenant_link_readable("document-id")
        self.assertEqual(
            client.recorded[0:2],
            ("PATCH", "/drive/v2/permissions/document-id/public"),
        )
        self.assertEqual(client.recorded[2]["query"], {"type": "docx"})
        self.assertEqual(
            client.recorded[2]["body"]["link_share_entity"],
            "tenant_readable",
        )


def client_module(module, client):
    class BoundClient(module.FeishuClient):
        def __init__(self) -> None:
            pass

        def request(self, method: str, path: str, **kwargs: object):
            return client.request(method, path, **kwargs)

    return BoundClient()


class WebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.webhook = load_module("feishu_webhook_for_test", "scripts/send_webhook.py")
        self.platform = load_module(
            "feishu_platform_support_webhook_test", "scripts/platform_support.py"
        )

    def test_loads_webhook_from_private_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps({"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test"}),
                encoding="utf-8",
            )
            self.platform.secure_private_file(config_path)
            self.assertEqual(
                self.webhook.load_webhook_url(config_path),
                "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            )

    def test_rejects_world_readable_secret_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps({"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test"}),
                encoding="utf-8",
            )
            if os.name != "nt":
                os.chmod(config_path, 0o644)
                mode = stat.S_IMODE(config_path.stat().st_mode)
                self.assertEqual(mode, 0o644)
            with self.assertRaises(self.webhook.WebhookError):
                self.webhook.load_webhook_url(config_path)

    def test_builds_text_message(self) -> None:
        self.assertEqual(
            self.webhook.build_payload("hello"),
            {"msg_type": "text", "content": {"text": "hello"}},
        )

    def test_sends_post_and_checks_feishu_code(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"code":0,"msg":"success"}'

        with patch.object(self.webhook.urllib.request, "urlopen", return_value=Response()) as call:
            result = self.webhook.send_payload(
                "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                {"msg_type": "text", "content": {"text": "hello"}},
            )
        self.assertEqual(result["code"], 0)
        request = call.call_args.args[0]
        self.assertEqual(request.method, "POST")


class ConfigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.configure = load_module("feishu_configure_for_test", "scripts/configure.py")
        self.platform = load_module(
            "feishu_platform_support_configure_test", "scripts/platform_support.py"
        )

    def test_save_config_uses_owner_only_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.configure.save_config(
                path,
                {
                    "app_id": "cli_test",
                    "app_secret": "secret",
                    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                    "download_dir": str(Path.home() / "Documents" / "Feishu"),
                },
            )
            self.platform.require_private_file(path)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_validates_tenant_base_url(self) -> None:
        self.assertEqual(
            self.configure.validate_base_url("https://example.feishu.cn/"),
            "https://example.feishu.cn",
        )
        with self.assertRaises(self.configure.ConfigureError):
            self.configure.validate_base_url("https://example.com")

    def test_registers_mcp_with_windows_virtualenv_python(self) -> None:
        register_mcp = getattr(self.configure, "register_mcp", None)
        self.assertIsNotNone(register_mcp)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / ".venv" / "Scripts" / "python.exe"
            server = root / "scripts" / "feishu_mcp_server.py"
            codex = root / "codex.exe"
            python.parent.mkdir(parents=True)
            server.parent.mkdir(parents=True)
            python.touch()
            server.touch()
            codex.touch()
            with patch.object(self.configure.subprocess, "run") as run:
                register_mcp(
                    root=root,
                    platform_name="nt",
                    codex_executable=codex,
                )

        add_call = run.call_args_list[1]
        self.assertEqual(
            add_call.args[0],
            [
                str(codex),
                "mcp",
                "add",
                "feishu_automation",
                "--",
                str(python),
                str(server),
            ],
        )


class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_complete_tool_set(self) -> None:
        server = load_module("feishu_server_protocol_test", "scripts/feishu_mcp_server.py")
        from mcp import Client

        async with Client(server.mcp) as client:
            result = await client.list_tools()
        self.assertEqual(
            [tool.name for tool in result.tools],
            [
                "create_feishu_document",
                "create_feishu_folder",
                "upload_feishu_attachment",
                "send_feishu_webhook",
                "read_feishu_document",
                "read_feishu_blocks",
                "append_feishu_markdown",
                "update_feishu_text_block",
                "replace_feishu_document",
                "list_feishu_attachments",
                "download_feishu_attachment",
            ],
        )


class DailyReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.daily = load_module(
            "feishu_daily_for_test", "scripts/publish_daily_report.py"
        )

    def test_extracts_three_daily_highlights(self) -> None:
        markdown = """# Daily

## 今日速览

- First
- Second
- Third
- Fourth

## Details
"""
        self.assertEqual(
            self.daily.extract_highlights(markdown),
            ["First", "Second", "Third"],
        )

    def test_builds_document_link_and_webhook_summary(self) -> None:
        class Client:
            def create_document(self, title: str, folder_token: str):
                self.created = (title, folder_token)
                return {"document_id": "doc-created", "title": title, "revision_id": 1}

            def convert_markdown(self, markdown: str):
                self.markdown = markdown
                return ["top"], [{"block_id": "top", "block_type": 2}]

            def insert_descendants(self, *args: object, **kwargs: object):
                self.inserted = (args, kwargs)
                return {"document_revision_id": 2}

            def set_tenant_link_readable(self, document_id: str):
                self.permission_document_id = document_id

        delivered: dict[str, object] = {}

        def sender(url: str, payload: dict[str, object]):
            delivered["url"] = url
            delivered["payload"] = payload
            return {"code": 0, "msg": "success"}

        client = Client()
        result = self.daily.publish_report(
            {
                "base_url": "https://example.feishu.cn",
                "default_folder_token": "folder-token",
                "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            },
            "AI Daily",
            "## 今日速览\n\n- First\n- Second\n- Third\n",
            client=client,
            webhook_sender=sender,
        )
        self.assertEqual(result["document_url"], "https://example.feishu.cn/docx/doc-created")
        self.assertEqual(client.permission_document_id, "doc-created")
        self.assertEqual(delivered["url"], "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        self.assertIn("doc-created", json.dumps(delivered["payload"]))

    def test_rejects_insecure_private_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "app_id": "cli_test",
                        "app_secret": "secret",
                        "base_url": "https://example.feishu.cn",
                        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(path, 0o644)
            with patch.dict(
                os.environ,
                {"FEISHU_AUTOMATION_CONFIG": str(path)},
                clear=False,
            ):
                with self.assertRaises(self.daily.DailyReportError):
                    self.daily.load_config()


if __name__ == "__main__":
    unittest.main()
