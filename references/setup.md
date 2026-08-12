# Setup

## 1. Create the enterprise application

Create an enterprise custom application in the Feishu Open Platform. Copy its App ID and App Secret from Credentials & Basic Info.

Enable the scopes needed by the operations you intend to use:

- `docx:document`: create, read, and edit DocX documents.
- `docx:document.block:convert`: convert Markdown into DocX blocks.
- `space:folder:create`: create Drive folders.
- `docs:document.media:upload`: upload images and attachments into documents.
- `docs:document.media:download`: download document images and attachments.
- `docs:permission.setting:write_only`: make generated report links readable inside the tenant.
- `wiki:wiki:readonly` or the current node-read equivalent: resolve Wiki links when Wiki pages are used.

Permission names may be displayed in Chinese in the console. Select the permission whose description matches the operation. Publish a new application version after adding scopes.

The app can automatically use documents and folders that it created. Existing user-owned resources must also be inside the application's data-access scope.

## 2. Add a custom webhook robot

In the target group, add a custom robot and copy its Webhook URL. This Webhook is for outbound notification only and does not use the enterprise application's credentials.

If the group robot requires keyword verification, make sure every generated message contains that keyword. The bundled sender currently supports URL-based Webhooks without timestamp/signature mode.

## 3. Install and configure locally

From the skill source directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/configure.py
```

The configurator writes `~/.config/codex/feishu-automation/config.json` with mode `600` and registers the local MCP server as `feishu_automation`.

Configuration schema:

```json
{
  "app_id": "cli_example",
  "app_secret": "replace-locally",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/replace-locally",
  "base_url": "https://your-tenant.feishu.cn",
  "default_folder_token": "",
  "download_dir": "/Users/your-name/Documents/Feishu"
}
```

`base_url` is needed to form clickable links for newly created daily-report documents. Add it manually if the configurator did not receive it.

Restart Codex after MCP configuration changes.

## 4. Verify without external writes

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/send_webhook.py --message "Feishu setup test" --dry-run
```

Only after user authorization, send a real webhook test and create a test document.
