#!/usr/bin/env python3
"""Automate Feishu Wiki/DocX documents and webhook delivery through MCP."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer


API_BASE = "https://open.feishu.cn/open-apis"
DEFAULT_CONFIG = Path("~/.config/codex/feishu-automation/config.json").expanduser()
DEFAULT_DOWNLOAD_DIR = Path("~/Documents/Feishu").expanduser()
MAX_TEXT_CHARS = 200_000
MAX_BLOCKS = 1_000
MAX_MARKDOWN_CHARS = 1_000_000
MAX_BLOCK_TEXT_CHARS = 100_000
MAX_ATTACHMENT_BYTES = 100_000_000
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SUPPORTED_HOST_SUFFIXES = (".feishu.cn", ".larksuite.com")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class FeishuAutomationError(RuntimeError):
    """Raised when a Feishu automation operation cannot be completed."""


# Keep the previous name for callers that already catch it.
FeishuReaderError = FeishuAutomationError


@dataclass(frozen=True)
class FeishuTarget:
    token: str
    resource_type: Literal["wiki", "docx", "auto"]


def config_path() -> Path:
    return Path(os.environ.get("FEISHU_AUTOMATION_CONFIG", str(DEFAULT_CONFIG))).expanduser()


def load_credentials() -> tuple[str, str]:
    path = config_path()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FeishuReaderError(f"Feishu config does not exist: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise FeishuReaderError(f"Unable to read Feishu config {path}: {error}") from error

    app_id = str(config.get("app_id", "")).strip()
    app_secret = str(config.get("app_secret", "")).strip()
    if not app_id or not app_secret:
        raise FeishuReaderError(f"Feishu config {path} is missing app_id or app_secret")
    return app_id, app_secret


def parse_target(
    value: str, resource_type: Literal["auto", "wiki", "docx"] = "auto"
) -> FeishuTarget:
    value = value.strip()
    if not value:
        raise FeishuReaderError("A Feishu Wiki/DocX URL or token is required.")

    if "://" not in value:
        if not TOKEN_PATTERN.fullmatch(value):
            raise FeishuReaderError("The supplied Feishu token contains invalid characters.")
        return FeishuTarget(token=value, resource_type=resource_type)

    parsed = urllib.parse.urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if not hostname or not any(
        hostname == suffix[1:] or hostname.endswith(suffix)
        for suffix in SUPPORTED_HOST_SUFFIXES
    ):
        raise FeishuReaderError("Only feishu.cn and larksuite.com document URLs are supported.")

    segments = [urllib.parse.unquote(segment) for segment in parsed.path.split("/") if segment]
    for document_type in ("wiki", "docx"):
        if document_type not in segments:
            continue
        index = segments.index(document_type)
        if index + 1 >= len(segments):
            break
        token = segments[index + 1]
        if not TOKEN_PATTERN.fullmatch(token):
            raise FeishuReaderError("The document URL contains an invalid token.")
        return FeishuTarget(token=token, resource_type=document_type)

    raise FeishuReaderError("The URL must contain /wiki/<token> or /docx/<token>.")


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._last_api_call = 0.0

    def _pace(self) -> None:
        delay = 0.25 - (time.monotonic() - self._last_api_call)
        if delay > 0:
            time.sleep(delay)
        self._last_api_call = time.monotonic()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        authenticated: bool = True,
        attempts: int = 4,
    ) -> dict[str, Any]:
        url = f"{API_BASE}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)

        headers = {"Content-Type": "application/json; charset=utf-8"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.tenant_access_token()}"
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")

        for attempt in range(attempts):
            self._pace()
            request = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    response_body = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as error:
                response_body = error.read().decode("utf-8", errors="replace")
                if error.code in (429, 500, 502, 503) and attempt + 1 < attempts:
                    time.sleep(2**attempt)
                    continue
                message = _api_error_message(response_body)
                raise FeishuReaderError(f"Feishu returned HTTP {error.code}: {message}") from error
            except urllib.error.URLError as error:
                if attempt + 1 < attempts:
                    time.sleep(2**attempt)
                    continue
                raise FeishuReaderError(f"Unable to reach Feishu: {error.reason}") from error

            try:
                result = json.loads(response_body)
            except json.JSONDecodeError as error:
                raise FeishuReaderError("Feishu returned a non-JSON response.") from error

            code = result.get("code", 0)
            if code == 0:
                return result
            if code in (99991400, 1061045, 1066002) and attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            raise FeishuReaderError(
                f"Feishu API rejected the request: code={code}, msg={result.get('msg', '')}"
            )

        raise FeishuReaderError("Feishu request exhausted all retry attempts.")

    def tenant_access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        result = self.request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            body={"app_id": self.app_id, "app_secret": self.app_secret},
            authenticated=False,
        )
        token = result.get("tenant_access_token")
        if not token:
            raise FeishuReaderError("Feishu did not return a tenant_access_token.")
        expires_in = max(int(result.get("expire", 7200)) - 60, 60)
        self._token = str(token)
        self._token_expires_at = time.monotonic() + expires_in
        return self._token

    def resolve_document(self, target: FeishuTarget) -> tuple[str, str]:
        if target.resource_type == "docx":
            return target.token, "docx"

        if target.resource_type == "wiki":
            return self._resolve_wiki(target.token)

        try:
            return self._resolve_wiki(target.token)
        except FeishuReaderError as wiki_error:
            try:
                self.document_metadata(target.token)
            except FeishuReaderError as docx_error:
                raise FeishuReaderError(
                    "Unable to resolve the token as Wiki or DocX. "
                    f"Wiki error: {wiki_error}; DocX error: {docx_error}"
                ) from docx_error
            return target.token, "docx"

    def _resolve_wiki(self, token: str) -> tuple[str, str]:
        data = self.request("GET", "/wiki/v2/spaces/get_node", query={"token": token}).get(
            "data", {}
        )
        node = data.get("node", {})
        obj_token = str(node.get("obj_token", ""))
        obj_type = str(node.get("obj_type", ""))
        if not obj_token or not obj_type:
            raise FeishuReaderError("Wiki resolution returned no obj_token or obj_type.")
        if obj_type != "docx":
            raise FeishuReaderError(
                f"The Wiki node contains {obj_type!r}; this reader currently supports DocX only."
            )
        return obj_token, obj_type

    def document_metadata(self, document_id: str) -> dict[str, Any]:
        return self.request("GET", f"/docx/v1/documents/{document_id}").get("data", {}).get(
            "document", {}
        )

    def create_document(self, title: str, folder_token: str = "") -> dict[str, Any]:
        body = {"title": validate_document_title(title)}
        if folder_token.strip():
            body["folder_token"] = folder_token.strip()
        document = self.request(
            "POST", "/docx/v1/documents", body=body
        ).get("data", {}).get("document", {})
        if not isinstance(document, dict) or not document.get("document_id"):
            raise FeishuAutomationError(
                "Document creation succeeded without returning document_id."
            )
        return document

    def create_folder(self, name: str, parent_folder_token: str = "") -> dict[str, Any]:
        folder_name = name.strip()
        if not folder_name:
            raise FeishuAutomationError("folder name must not be empty.")
        data = self.request(
            "POST",
            "/drive/v1/files/create_folder",
            body={
                "name": folder_name,
                "folder_token": parent_folder_token.strip(),
            },
        ).get("data", {})
        if not isinstance(data, dict) or not data.get("token"):
            raise FeishuAutomationError(
                "Folder creation succeeded without returning a folder token."
            )
        return data

    def set_tenant_link_readable(self, document_id: str) -> None:
        self.request(
            "PATCH",
            f"/drive/v2/permissions/{document_id}/public",
            query={"type": "docx"},
            body={
                "external_access": False,
                "security_entity": "anyone_can_view",
                "comment_entity": "anyone_can_view",
                "share_entity": "only_full_access",
                "link_share_entity": "tenant_readable",
                "invite_external": False,
            },
        )

    def create_file_block(
        self,
        document_id: str,
        parent_block_id: str,
        index: int,
    ) -> tuple[str, int]:
        data = self.request(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{parent_block_id}/children",
            query={"document_revision_id": -1, "client_token": uuid.uuid4().hex},
            body={
                "index": index,
                "children": [{"block_type": 23, "file": {"token": ""}}],
            },
        ).get("data", {})
        children = data.get("children", [])
        try:
            file_block_id = children[0]["children"][0]
        except (IndexError, KeyError, TypeError) as error:
            raise FeishuAutomationError(
                "File block creation returned no nested file block ID."
            ) from error
        return str(file_block_id), int(data.get("document_revision_id", -1))

    def upload_media(
        self,
        file_path: Path,
        parent_node: str,
        document_id: str,
    ) -> str:
        size = file_path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise FeishuAutomationError(
                f"Attachment is {size} bytes; single-part upload supports {MAX_UPLOAD_BYTES}."
            )
        boundary = f"----FeishuAutomation{uuid.uuid4().hex}"
        fields = {
            "file_name": file_path.name,
            "parent_type": "docx_file",
            "parent_node": parent_node,
            "size": str(size),
            "extra": json.dumps({"drive_route_token": document_id}),
        }
        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            )
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
        )
        body.extend(file_path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        request = urllib.request.Request(
            f"{API_BASE}/drive/v1/medias/upload_all",
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self.tenant_access_token()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace")
            raise FeishuAutomationError(
                f"Feishu returned HTTP {error.code}: {_api_error_message(response_body)}"
            ) from error
        except urllib.error.URLError as error:
            raise FeishuAutomationError(
                f"Unable to upload Feishu attachment: {error.reason}"
            ) from error
        try:
            result = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise FeishuAutomationError("Feishu returned a non-JSON upload response.") from error
        if result.get("code", 0) != 0:
            raise FeishuAutomationError(
                f"Feishu rejected the upload: code={result.get('code')}, msg={result.get('msg', '')}"
            )
        token = result.get("data", {}).get("file_token")
        if not token:
            raise FeishuAutomationError("Attachment upload returned no file_token.")
        return str(token)

    def replace_file(
        self,
        document_id: str,
        block_id: str,
        file_token: str,
        revision_id: int,
    ) -> int:
        data = self.request(
            "PATCH",
            f"/docx/v1/documents/{document_id}/blocks/{block_id}",
            query={"document_revision_id": revision_id, "client_token": uuid.uuid4().hex},
            body={"replace_file": {"token": file_token}},
        ).get("data", {})
        return int(data.get("document_revision_id", revision_id))

    def attach_file(
        self,
        document_id: str,
        file_path: Path,
        parent_block_id: str,
        index: int,
    ) -> dict[str, Any]:
        block_id, revision_id = self.create_file_block(
            document_id, parent_block_id, index
        )
        file_token = self.upload_media(file_path, block_id, document_id)
        revision_id = self.replace_file(
            document_id, block_id, file_token, revision_id
        )
        return {
            "document_id": document_id,
            "block_id": block_id,
            "file_token": file_token,
            "file_name": file_path.name,
            "bytes": file_path.stat().st_size,
            "document_revision_id": revision_id,
        }

    def raw_content(self, document_id: str) -> str:
        data = self.request(
            "GET", f"/docx/v1/documents/{document_id}/raw_content"
        ).get("data", {})
        return str(data.get("content", ""))

    def blocks(self, document_id: str, max_blocks: int) -> tuple[list[dict[str, Any]], bool]:
        items: list[dict[str, Any]] = []
        page_token = ""
        has_more = False

        while len(items) < max_blocks:
            query: dict[str, Any] = {
                "document_revision_id": -1,
                "page_size": min(500, max_blocks - len(items)),
            }
            if page_token:
                query["page_token"] = page_token
            data = self.request(
                "GET", f"/docx/v1/documents/{document_id}/blocks", query=query
            ).get("data", {})
            page_items = data.get("items", [])
            if not isinstance(page_items, list):
                raise FeishuReaderError("Feishu returned an invalid block list.")
            items.extend(page_items)
            has_more = bool(data.get("has_more"))
            page_token = str(data.get("page_token", ""))
            if not has_more or not page_token:
                break

        return items[:max_blocks], has_more or len(items) > max_blocks

    def block(self, document_id: str, block_id: str) -> dict[str, Any]:
        data = self.request(
            "GET",
            f"/docx/v1/documents/{document_id}/blocks/{block_id}",
            query={"document_revision_id": -1},
        ).get("data", {})
        block = data.get("block", {})
        if not isinstance(block, dict) or not block:
            raise FeishuReaderError(f"Feishu returned no block for {block_id}.")
        return block

    def convert_markdown(self, markdown: str) -> tuple[list[str], list[dict[str, Any]]]:
        data = self.request(
            "POST",
            "/docx/v1/documents/blocks/convert",
            body={"content_type": "markdown", "content": markdown},
        ).get("data", {})
        first_level_ids = data.get("first_level_block_ids", [])
        blocks = data.get("blocks", [])
        if not isinstance(first_level_ids, list) or not first_level_ids:
            raise FeishuReaderError("Markdown conversion returned no first-level blocks.")
        if not isinstance(blocks, list) or not blocks:
            raise FeishuReaderError("Markdown conversion returned no document blocks.")
        if len(blocks) > MAX_BLOCKS:
            raise FeishuReaderError(
                f"Markdown converted to {len(blocks)} blocks; the limit is {MAX_BLOCKS}."
            )
        strip_read_only_fields(blocks)
        return [str(block_id) for block_id in first_level_ids], blocks

    def insert_descendants(
        self,
        document_id: str,
        first_level_ids: list[str],
        blocks: list[dict[str, Any]],
        *,
        index: int = -1,
        revision_id: int = -1,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{document_id}/descendant",
            query={
                "document_revision_id": revision_id,
                "client_token": uuid.uuid4().hex,
            },
            body={
                "index": index,
                "children_id": first_level_ids,
                "descendants": blocks,
            },
        ).get("data", {})

    def update_text_block(
        self, document_id: str, block_id: str, text: str, *, revision_id: int = -1
    ) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/docx/v1/documents/{document_id}/blocks/batch_update",
            query={
                "document_revision_id": revision_id,
                "client_token": uuid.uuid4().hex,
            },
            body={
                "requests": [
                    {
                        "block_id": block_id,
                        "update_text_elements": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": text,
                                        "text_element_style": {},
                                    }
                                }
                            ]
                        },
                    }
                ]
            },
        ).get("data", {})

    def delete_children(
        self,
        document_id: str,
        parent_block_id: str,
        start_index: int,
        end_index: int,
        *,
        revision_id: int = -1,
    ) -> dict[str, Any]:
        return self.request(
            "DELETE",
            (
                f"/docx/v1/documents/{document_id}/blocks/{parent_block_id}"
                "/children/batch_delete"
            ),
            query={
                "document_revision_id": revision_id,
                "client_token": uuid.uuid4().hex,
            },
            body={"start_index": start_index, "end_index": end_index},
        ).get("data", {})

    def download_media(
        self,
        file_token: str,
        destination: Path,
        *,
        max_bytes: int,
        overwrite: bool,
        attempts: int = 3,
    ) -> dict[str, Any]:
        if destination.exists() and not overwrite:
            raise FeishuReaderError(
                f"Destination already exists: {destination}. Set overwrite=true to replace it."
            )

        url = f"{API_BASE}/drive/v1/medias/{file_token}/download"
        headers = {"Authorization": f"Bearer {self.tenant_access_token()}"}

        for attempt in range(attempts):
            self._pace()
            request = urllib.request.Request(url, headers=headers, method="GET")
            temp_path = destination.with_name(
                f".{destination.name}.{uuid.uuid4().hex}.download"
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > max_bytes:
                        raise FeishuReaderError(
                            f"Attachment is {content_length} bytes; max_bytes is {max_bytes}."
                        )

                    total = 0
                    with temp_path.open("xb") as output:
                        while True:
                            chunk = response.read(64 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > max_bytes:
                                raise FeishuReaderError(
                                    f"Attachment exceeds max_bytes={max_bytes}."
                                )
                            output.write(chunk)

                    if destination.exists() and not overwrite:
                        raise FeishuReaderError(
                            f"Destination was created during download: {destination}."
                        )
                    temp_path.replace(destination)
                    return {
                        "bytes": total,
                        "content_type": response.headers.get("Content-Type", ""),
                        "content_disposition": response.headers.get(
                            "Content-Disposition", ""
                        ),
                    }
            except urllib.error.HTTPError as error:
                response_body = error.read().decode("utf-8", errors="replace")
                if error.code in (429, 500, 502, 503) and attempt + 1 < attempts:
                    time.sleep(2**attempt)
                    continue
                message = _api_error_message(response_body)
                raise FeishuReaderError(f"Feishu returned HTTP {error.code}: {message}") from error
            except urllib.error.URLError as error:
                if attempt + 1 < attempts:
                    time.sleep(2**attempt)
                    continue
                raise FeishuReaderError(f"Unable to download Feishu attachment: {error.reason}") from error
            finally:
                if temp_path.exists():
                    temp_path.unlink()

        raise FeishuReaderError("Feishu attachment download exhausted all retry attempts.")


def _api_error_message(response_body: str) -> str:
    try:
        result = json.loads(response_body)
    except json.JSONDecodeError:
        return "non-JSON error response"
    return f"code={result.get('code', 'unknown')}, msg={result.get('msg', '')}"


def validate_document_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise FeishuAutomationError("title must not be empty.")
    if len(title) > 800:
        raise FeishuAutomationError("title exceeds Feishu's 800-character limit.")
    return title


def strip_read_only_fields(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("merge_info", None)
        for child in value.values():
            strip_read_only_fields(child)
    elif isinstance(value, list):
        for child in value:
            strip_read_only_fields(child)


def extract_block_text(block: dict[str, Any]) -> str:
    for key in (
        "page",
        "text",
        "heading1",
        "heading2",
        "heading3",
        "heading4",
        "heading5",
        "heading6",
        "heading7",
        "heading8",
        "heading9",
        "bullet",
        "ordered",
        "code",
        "quote",
        "todo",
    ):
        block_data = block.get(key)
        if not isinstance(block_data, dict):
            continue
        elements = block_data.get("elements", [])
        if not isinstance(elements, list):
            continue
        parts: list[str] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            text_run = element.get("text_run")
            if isinstance(text_run, dict):
                parts.append(str(text_run.get("content", "")))
        return "".join(parts)
    raise FeishuReaderError("The selected block is not an editable text block.")


def collect_attachments(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    for block in blocks:
        file_data = block.get("file")
        if not isinstance(file_data, dict):
            continue
        token = str(file_data.get("token", ""))
        name = str(file_data.get("name", ""))
        if not token or not name:
            continue
        attachments.append(
            {
                "name": name,
                "file_token": token,
                "block_id": str(block.get("block_id", "")),
                "parent_id": str(block.get("parent_id", "")),
            }
        )
    return attachments


def safe_download_directory(value: str) -> Path:
    raw_path = Path(value).expanduser()
    if not raw_path.is_absolute():
        raw_path = Path.home() / raw_path
    directory = raw_path.resolve()
    home = Path.home().resolve()
    if directory != home and home not in directory.parents:
        raise FeishuReaderError("The download directory must be inside the current user's home.")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def safe_attachment_name(value: str) -> str:
    name = Path(value).name.strip()
    if (
        not name
        or name in (".", "..")
        or "\x00" in name
        or "/" in value
        or "\\" in value
    ):
        raise FeishuReaderError("The attachment name is invalid.")
    if len(name.encode("utf-8")) > 240:
        raise FeishuReaderError("The attachment name is too long.")
    return name


def new_client() -> FeishuClient:
    app_id, app_secret = load_credentials()
    return FeishuClient(app_id, app_secret)


def _resolve(
    url_or_token: str, resource_type: Literal["auto", "wiki", "docx"]
) -> tuple[FeishuClient, FeishuTarget, str]:
    target = parse_target(url_or_token, resource_type)
    client = new_client()
    document_id, _ = client.resolve_document(target)
    return client, target, document_id


mcp = MCPServer(
    name="feishu-automation",
    title="Feishu Automation",
    description=(
        "Create, read, and edit Feishu Wiki/DocX documents, download attachments, "
        "and send messages through a custom-bot webhook."
    ),
    instructions=(
        "Use read tools before editing. Updating a block requires its exact current text. "
        "Replacing a document requires its document ID and revision ID from a prior read. "
        "Downloads never overwrite files unless overwrite=true. Access remains limited by the "
        "configured Feishu app's scopes and each document's permissions."
    ),
)


@mcp.tool(structured_output=True)
def create_feishu_document(
    title: str,
    markdown: str = "",
    folder_token: str = "",
) -> dict[str, Any]:
    """Create a Feishu DocX, optionally write Markdown content, and return its identifiers."""
    if len(markdown) > MAX_MARKDOWN_CHARS:
        raise FeishuAutomationError(
            f"markdown exceeds the {MAX_MARKDOWN_CHARS}-character limit."
        )

    client = new_client()
    document = client.create_document(title, folder_token)
    document_id = str(document["document_id"])
    added_top_level = 0
    added_total = 0
    revision_id = document.get("revision_id")
    if markdown.strip():
        first_level_ids, blocks = client.convert_markdown(markdown)
        data = client.insert_descendants(document_id, first_level_ids, blocks, index=0)
        added_top_level = len(first_level_ids)
        added_total = len(blocks)
        revision_id = data.get("document_revision_id", revision_id)

    return {
        "document_id": document_id,
        "title": str(document.get("title", title.strip())),
        "folder_token": folder_token.strip(),
        "added_top_level_blocks": added_top_level,
        "added_total_blocks": added_total,
        "document_revision_id": revision_id,
    }


@mcp.tool(structured_output=True)
def create_feishu_folder(
    name: str,
    parent_folder_token: str = "",
) -> dict[str, Any]:
    """Create a Feishu Drive folder owned by the configured application."""
    folder = new_client().create_folder(name, parent_folder_token)
    return {
        "folder_token": str(folder.get("token", "")),
        "folder_url": str(folder.get("url", "")),
        "name": name.strip(),
    }


@mcp.tool(structured_output=True)
def upload_feishu_attachment(
    url_or_token: str,
    local_path: str,
    parent_block_id: str = "",
    index: int = -1,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
) -> dict[str, Any]:
    """Upload a local file of at most 20 MB and insert it as a Feishu document attachment."""
    path = Path(local_path).expanduser().resolve()
    if not path.is_file():
        raise FeishuAutomationError(f"Attachment file does not exist: {path}")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise FeishuAutomationError(
            f"Attachment exceeds the {MAX_UPLOAD_BYTES}-byte single-upload limit."
        )
    client, _, document_id = _resolve(url_or_token, resource_type)
    parent = parent_block_id.strip() or document_id
    if not TOKEN_PATTERN.fullmatch(parent):
        raise FeishuAutomationError("parent_block_id is invalid.")
    return client.attach_file(document_id, path, parent, index)


@mcp.tool(structured_output=True)
def send_feishu_webhook(
    text: str,
    title: str = "",
    link_url: str = "",
    link_text: str = "阅读全文",
) -> dict[str, Any]:
    """Send text and an optional document link through the configured Feishu custom-bot webhook."""
    from send_webhook import build_payload, load_webhook_url, send_payload

    payload = build_payload(text, title=title, link_url=link_url, link_text=link_text)
    result = send_payload(load_webhook_url(config_path()), payload)
    return {
        "delivered": True,
        "code": result.get("code", result.get("StatusCode", 0)),
        "message": result.get("msg", result.get("StatusMessage", "success")),
    }


@mcp.tool(structured_output=True)
def read_feishu_document(
    url_or_token: str,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
    max_chars: int = 100_000,
) -> dict[str, Any]:
    """Read a Feishu Wiki/DocX document as plain text, including its title and identifiers."""
    if not 1 <= max_chars <= MAX_TEXT_CHARS:
        raise FeishuReaderError(f"max_chars must be between 1 and {MAX_TEXT_CHARS}.")

    client, target, document_id = _resolve(url_or_token, resource_type)
    metadata = client.document_metadata(document_id)
    content = client.raw_content(document_id)
    truncated = len(content) > max_chars
    return {
        "source_type": target.resource_type,
        "source_token": target.token,
        "document_id": document_id,
        "title": str(metadata.get("title", "")),
        "revision_id": metadata.get("revision_id"),
        "content": content[:max_chars],
        "character_count": len(content),
        "truncated": truncated,
    }


@mcp.tool(structured_output=True)
def read_feishu_blocks(
    url_or_token: str,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
    max_blocks: int = 300,
) -> dict[str, Any]:
    """Read structured Feishu DocX blocks for headings, lists, tables, and rich content."""
    if not 1 <= max_blocks <= MAX_BLOCKS:
        raise FeishuReaderError(f"max_blocks must be between 1 and {MAX_BLOCKS}.")

    client, target, document_id = _resolve(url_or_token, resource_type)
    metadata = client.document_metadata(document_id)
    blocks, truncated = client.blocks(document_id, max_blocks)
    return {
        "source_type": target.resource_type,
        "source_token": target.token,
        "document_id": document_id,
        "title": str(metadata.get("title", "")),
        "revision_id": metadata.get("revision_id"),
        "blocks": blocks,
        "block_count": len(blocks),
        "truncated": truncated,
    }


@mcp.tool(structured_output=True)
def append_feishu_markdown(
    url_or_token: str,
    markdown: str,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
) -> dict[str, Any]:
    """Append Markdown to the end of a Feishu Wiki/DocX document."""
    if not markdown.strip():
        raise FeishuReaderError("markdown must not be empty.")
    if len(markdown) > MAX_MARKDOWN_CHARS:
        raise FeishuReaderError(
            f"markdown exceeds the {MAX_MARKDOWN_CHARS}-character limit."
        )

    client, target, document_id = _resolve(url_or_token, resource_type)
    first_level_ids, blocks = client.convert_markdown(markdown)
    data = client.insert_descendants(document_id, first_level_ids, blocks, index=-1)
    return {
        "source_type": target.resource_type,
        "document_id": document_id,
        "added_top_level_blocks": len(first_level_ids),
        "added_total_blocks": len(blocks),
        "document_revision_id": data.get("document_revision_id"),
    }


@mcp.tool(structured_output=True)
def update_feishu_text_block(
    url_or_token: str,
    block_id: str,
    expected_current_text: str,
    new_text: str,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
) -> dict[str, Any]:
    """Replace one text block after verifying its current text has not changed."""
    if not TOKEN_PATTERN.fullmatch(block_id.strip()):
        raise FeishuReaderError("block_id is invalid.")
    if len(new_text) > MAX_BLOCK_TEXT_CHARS:
        raise FeishuReaderError(
            f"new_text exceeds the {MAX_BLOCK_TEXT_CHARS}-character limit."
        )

    client, target, document_id = _resolve(url_or_token, resource_type)
    if block_id == document_id:
        raise FeishuReaderError("The document root block cannot be updated with this tool.")
    block = client.block(document_id, block_id)
    current_text = extract_block_text(block)
    if current_text != expected_current_text:
        raise FeishuReaderError(
            "The block changed or the wrong block was selected. "
            f"Current text is {current_text!r}; no update was made."
        )

    data = client.update_text_block(document_id, block_id, new_text)
    return {
        "source_type": target.resource_type,
        "document_id": document_id,
        "block_id": block_id,
        "previous_text": current_text,
        "new_text": new_text,
        "document_revision_id": data.get("document_revision_id"),
    }


@mcp.tool(structured_output=True)
def replace_feishu_document(
    url_or_token: str,
    markdown: str,
    confirmation_document_id: str,
    expected_revision_id: int,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
) -> dict[str, Any]:
    """Replace the whole document body after confirming its ID and current revision."""
    if not markdown.strip():
        raise FeishuReaderError("markdown must not be empty.")
    if len(markdown) > MAX_MARKDOWN_CHARS:
        raise FeishuReaderError(
            f"markdown exceeds the {MAX_MARKDOWN_CHARS}-character limit."
        )

    client, target, document_id = _resolve(url_or_token, resource_type)
    if confirmation_document_id != document_id:
        raise FeishuReaderError(
            "confirmation_document_id does not match the resolved document; no changes were made."
        )

    metadata = client.document_metadata(document_id)
    current_revision = metadata.get("revision_id")
    if current_revision != expected_revision_id:
        raise FeishuReaderError(
            f"Document revision changed from {expected_revision_id} to {current_revision}; "
            "read it again before replacing."
        )

    root_block = client.block(document_id, document_id)
    old_children = root_block.get("children", [])
    if not isinstance(old_children, list):
        raise FeishuReaderError("Feishu returned an invalid root child list.")

    first_level_ids, blocks = client.convert_markdown(markdown)
    inserted = client.insert_descendants(
        document_id,
        first_level_ids,
        blocks,
        index=-1,
        revision_id=expected_revision_id,
    )
    inserted_revision = int(inserted.get("document_revision_id", -1))

    final_revision = inserted_revision
    if old_children:
        try:
            deleted = client.delete_children(
                document_id,
                document_id,
                0,
                len(old_children),
                revision_id=inserted_revision,
            )
        except FeishuReaderError as error:
            raise FeishuReaderError(
                "New content was appended, but the old content could not be deleted. "
                "The document still contains both versions; inspect it before retrying. "
                f"Feishu error: {error}"
            ) from error
        final_revision = int(deleted.get("document_revision_id", inserted_revision))

    return {
        "source_type": target.resource_type,
        "document_id": document_id,
        "removed_top_level_blocks": len(old_children),
        "added_top_level_blocks": len(first_level_ids),
        "added_total_blocks": len(blocks),
        "document_revision_id": final_revision,
    }


@mcp.tool(structured_output=True)
def list_feishu_attachments(
    url_or_token: str,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
) -> dict[str, Any]:
    """List file attachments embedded in a Feishu Wiki/DocX document."""
    client, target, document_id = _resolve(url_or_token, resource_type)
    blocks, truncated = client.blocks(document_id, MAX_BLOCKS)
    if truncated:
        raise FeishuReaderError(
            f"The document exceeds {MAX_BLOCKS} blocks; attachment listing is incomplete."
        )
    attachments = collect_attachments(blocks)
    return {
        "source_type": target.resource_type,
        "document_id": document_id,
        "attachments": attachments,
        "attachment_count": len(attachments),
    }


@mcp.tool(structured_output=True)
def download_feishu_attachment(
    url_or_token: str,
    attachment_name_or_token: str,
    download_directory: str = str(DEFAULT_DOWNLOAD_DIR),
    overwrite: bool = False,
    max_bytes: int = 50_000_000,
    resource_type: Literal["auto", "wiki", "docx"] = "auto",
) -> dict[str, Any]:
    """Download one embedded file attachment, defaulting to the user's Documents directory."""
    if not 1 <= max_bytes <= MAX_ATTACHMENT_BYTES:
        raise FeishuReaderError(f"max_bytes must be between 1 and {MAX_ATTACHMENT_BYTES}.")

    client, target, document_id = _resolve(url_or_token, resource_type)
    blocks, truncated = client.blocks(document_id, MAX_BLOCKS)
    if truncated:
        raise FeishuReaderError(
            f"The document exceeds {MAX_BLOCKS} blocks; attachment lookup is incomplete."
        )
    attachments = collect_attachments(blocks)
    matches = [
        attachment
        for attachment in attachments
        if attachment_name_or_token
        in (attachment["name"], attachment["file_token"])
    ]
    if not matches:
        available = ", ".join(attachment["name"] for attachment in attachments) or "none"
        raise FeishuReaderError(
            f"Attachment {attachment_name_or_token!r} was not found. Available: {available}."
        )
    if len(matches) > 1:
        raise FeishuReaderError(
            "Multiple attachments have that name; call the tool again with the file_token."
        )

    attachment = matches[0]
    directory = safe_download_directory(download_directory)
    destination = directory / safe_attachment_name(attachment["name"])
    download = client.download_media(
        attachment["file_token"],
        destination,
        max_bytes=max_bytes,
        overwrite=overwrite,
    )
    return {
        "source_type": target.resource_type,
        "document_id": document_id,
        "attachment_name": attachment["name"],
        "file_token": attachment["file_token"],
        "local_path": str(destination),
        "bytes": download["bytes"],
        "content_type": download["content_type"],
    }


if __name__ == "__main__":
    mcp.run()
