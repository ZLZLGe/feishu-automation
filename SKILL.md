---
name: feishu-automation
description: Use when doing first-time Feishu setup, explaining or creating an enterprise custom app or group Webhook, configuring Feishu Open Platform for Codex, working with Feishu Wiki/DocX documents or attachments, or sending proactive group notifications.
---

# Feishu Automation

Use the bundled MCP server for document operations and the custom-bot webhook for outbound group notifications. Keep application credentials and webhook URLs in the private config, never in source files, command history, logs, or Git.

## Select the path

- First-time setup, missing credentials, or questions such as "what is a Feishu custom app?": follow **Guided first-time setup** below. Do not jump directly to `scripts/configure.py`.
- Permission errors after setup: read `references/setup.md` and `references/troubleshooting.md`.
- Create, read, or edit a document: use the `feishu_automation` MCP tools. Read before changing existing content.
- Upload or download a document attachment: use the attachment MCP tools; downloads default to `~/Documents/Feishu`.
- Push a fixed-group notification: use `send_feishu_webhook` or `scripts/send_webhook.py`.
- Publish a Markdown daily report: read `references/daily-ai-report.md` and use `scripts/publish_daily_report.py`.

## Guided first-time setup

Do not merely give the user a static checklist. Explain each concept, proactively open the relevant official page, state the exact clicks to make, and Wait for the user to confirm completion before advancing to the next stage. Login, secret viewing, permission approval, and publishing remain user-controlled actions.

Resolve all `scripts/...` and `references/...` paths relative to this Skill directory, not the user's current working directory.

1. Explain the two independent identities before asking for any value:
   - A **Feishu enterprise custom app** is the local MCP server's API identity. Its App ID and App Secret let the MCP request document, folder, permission, and attachment APIs. The user does not need to build a web app or mini program.
   - A **custom group robot Webhook** can only push messages into the one group where it was added. It cannot read or edit documents and does not replace the enterprise app.
2. Open the developer console immediately at `https://open.feishu.cn/app`. Prefer a connected browser-control tool and actually open the page rather than only returning a link. If browser control is unavailable, run `python scripts/open_setup.py developer-console`. Tell the user to sign in, click **创建企业自建应用**, enter a name such as `Codex Feishu Automation`, and click **创建**. Wait for the user to say the application exists.
3. Tell the user to open **凭证与基础信息** in the new application's sidebar. Explain where App ID and App Secret are located and ask the user to provide them so the Agent can configure the integration. Treat App Secret as sensitive: do not repeat it in a response, log it, place it in a command line, or commit it.
4. Tell the user to open **权限管理 > 开通权限**, select **应用身份权限**, and enable the scopes listed in `references/setup.md`. Explain that document creation, Markdown conversion, folders, attachments, sharing, and Wiki access require different scopes. Wait for the user to confirm the required scopes are enabled.
5. Tell the user to open **版本管理与发布**, create a version, submit it, and complete any administrator approval. Explain that newly added scopes do not become effective until a version containing them is published. Wait for publication confirmation.
6. Open the official custom-robot guide with a browser tool or `python scripts/open_setup.py webhook-guide`. Guide the user in the target group through **设置 > 群机器人 > 添加机器人 > 自定义机器人**. Ask for the generated Webhook URL and any keyword rule. Treat the full URL as sensitive and never repeat, log, place it in a command line, or commit it. Wait for confirmation.
7. Ask the user for any Feishu document URL from the same organization, such as `https://example.feishu.cn/wiki/...`. Derive the tenant base URL from its scheme and host; never ask the user to identify or enter a separate tenant URL.
8. Only after all values are ready, the Agent must run the configurator itself using the platform-specific Python from `references/setup.md`. Do not ask the user to run `scripts/configure.py`. Start the credential-free command in an interactive PTY, then answer each prompt separately. Never embed credentials in command arguments, environment variables, `printf`, pipes, here-documents, or generated script files. The configurator writes the private config and registers the MCP.
9. Ask the user to restart Codex, check `codex mcp get feishu_automation`, run a Webhook dry run, and request authorization before creating a real document or sending a real group message.

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

- Private config: `~/.config/codex/feishu-automation/config.json`; use mode `600` on macOS/Linux and a current-user-only ACL on Windows.
- Download directory: `~/Documents/Feishu`.
- Codex MCP name: `feishu_automation`.
- Store examples with placeholders only. Never commit `app_secret`, access tokens, or complete webhook URLs.
- After changing app scopes, publish a new app version before diagnosing API failures.
- An application token can access only resources in the application's data scope; share existing documents or folders with the app as needed.

Read `references/tools.md` for the exact tool set and `references/troubleshooting.md` when a call fails.
