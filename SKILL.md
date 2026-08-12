---
name: feishu-automation
description: Use when configuring Feishu Open Platform for Codex, creating or editing Feishu Wiki/DocX documents, handling document attachments, or sending proactive group notifications through a Feishu custom-bot webhook.
---

# Feishu Automation

Use the bundled MCP server for document operations and the custom-bot webhook for outbound group notifications. Keep application credentials and webhook URLs in the private config, never in prompts, source files, command history, or Git.

## Select the path

- First-time setup or permission errors: read `references/setup.md`, then run `scripts/configure.py`.
- Create, read, or edit a document: use the `feishu_automation` MCP tools. Read before changing existing content.
- Upload or download a document attachment: use the attachment MCP tools; downloads default to `~/Documents/Feishu`.
- Push a fixed-group notification: use `send_feishu_webhook` or `scripts/send_webhook.py`.
- Publish a Markdown daily report: read `references/daily-ai-report.md` and use `scripts/publish_daily_report.py`.

## Document workflow

1. For a new document, call `create_feishu_document` with a title, optional Markdown, and optional application-owned folder token.
2. For an existing document, call `read_feishu_document`; call `read_feishu_blocks` when block IDs or rich structure matter.
3. Prefer `append_feishu_markdown` for additions.
4. Use `update_feishu_text_block` only with the exact text returned by the last read.
5. Use `replace_feishu_document` only after confirming the document ID and revision from the last read.
6. List attachments before downloading. Do not overwrite an existing local file unless explicitly requested.

## Notification workflow

Use a Feishu custom-bot webhook only for proactive delivery to its configured group. It is independent from the enterprise application's App ID and App Secret. Keep messages concise; put long content in a DocX and send its summary plus link.

For direct script use:

```bash
python scripts/send_webhook.py --message "Task complete"
python scripts/send_webhook.py --title "AI Daily" --message "Three highlights" --link-url "https://example.feishu.cn/docx/..."
```

Run with `--dry-run` before changing a message template. Do not send test messages unless the user authorizes external delivery.

## Configuration rules

- Private config: `~/.config/codex/feishu-automation/config.json`, mode `600`.
- Download directory: `~/Documents/Feishu`.
- Codex MCP name: `feishu_automation`.
- Store examples with placeholders only. Never commit `app_secret`, access tokens, or complete webhook URLs.
- After changing app scopes, publish a new app version before diagnosing API failures.
- An application token can access only resources in the application's data scope; share existing documents or folders with the app as needed.

Read `references/tools.md` for the exact tool set and `references/troubleshooting.md` when a call fails.
