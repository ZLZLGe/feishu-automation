# MCP Tools

## Create and organize

- `create_feishu_folder`: create an application-owned Drive folder.
- `create_feishu_document`: create a DocX and optionally populate it from Markdown.

## Read and edit

- `read_feishu_document`: read title, identifiers, revision, and plain text.
- `read_feishu_blocks`: read structured DocX blocks.
- `append_feishu_markdown`: append converted Markdown.
- `update_feishu_text_block`: update one text block after exact-text comparison.
- `replace_feishu_document`: replace the body after document-ID and revision confirmation.

Before using a write tool on an existing user-owned document, confirm that the enterprise application is a collaborator with **可编辑** permission. **可阅读** permission supports reads only. API scopes and document-level collaborator permissions are separate requirements.

## Attachments

- `list_feishu_attachments`: list embedded file blocks and tokens.
- `download_feishu_attachment`: download one listed attachment.
- `upload_feishu_attachment`: insert a local file of at most 20 MB into a DocX. Larger files require Feishu's multipart upload flow and are not handled by this tool.

## Notifications

- `send_feishu_webhook`: send text or a titled summary with an optional link to the configured custom-robot group.

Wiki URLs are resolved to their underlying DocX token before document operations.
