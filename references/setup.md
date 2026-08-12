# Guided Setup

Use this reference when the user has not yet created the Feishu credentials. Do not send the entire document as one checklist. Explain one stage, open the relevant page, and wait for the user to finish before proceeding.

## What the two Feishu components are

The integration uses two independent Feishu components:

- A **Feishu enterprise custom app** is an API identity owned by the user's organization. The local MCP exchanges its App ID and App Secret for an application token, then uses that token to call document, folder, attachment, Wiki, and permission APIs. The user does not need to build a web page, mini program, or interactive bot.
- A **custom group robot** belongs to one target group and exposes a Webhook URL. It can receive outbound notifications from this project, but it cannot read or edit documents.

The user may configure document automation without a Webhook only by manually leaving `webhook_url` out of the private configuration. The bundled interactive configurator currently expects both because it supports the full feature set.

Never ask the user to paste App Secret or a complete Webhook URL into chat. Collect both through the configurator's hidden terminal prompts.

## 1. Create an enterprise custom app

Open the developer console:

```text
https://open.feishu.cn/app
```

Prefer a browser-control tool and navigate there directly. If browser control is unavailable, run:

```bash
python scripts/open_setup.py developer-console
```

Tell the user to:

1. Sign in with the organization account that will own the integration.
2. On the developer-console home page, select **创建企业自建应用**.
3. Use a descriptive name such as `Codex Feishu Automation`, add a short description, select an icon, and click **创建**.

If the creation button is missing or approval is required, an organization administrator may have restricted custom-app creation. Stop and ask the user to request access from the administrator.

Wait until the user confirms the application detail page is open.

## 2. Find Credentials & Basic Info

In the application's left sidebar, open **凭证与基础信息** (Credentials & Basic Info).

Explain that:

- App ID identifies this application and usually starts with `cli_`.
- App Secret authenticates the application and must remain private.
- The user only needs to note both values locally. Do not ask them to send either secret through chat.

Do not proceed until the user can see the credentials page.

## 3. Enable Permissions & Scopes

In the application's left sidebar, open **权限管理 > 开通权限**. Choose **应用身份权限** when the console distinguishes application and user identity.

Enable the scopes required by the features the user wants:

- `docx:document`: create, read, and edit DocX documents.
- `docx:document.block:convert`: convert Markdown into DocX blocks.
- `space:folder:create`: create Drive folders.
- `docs:document.media:upload`: upload images and attachments into documents.
- `docs:document.media:download`: download document images and attachments.
- `docs:permission.setting:write_only`: make generated report links readable inside the tenant.
- `wiki:wiki:readonly`, or the currently displayed equivalent for reading Wiki nodes: resolve Wiki links.

Permission labels can differ between console versions. Search by scope identifier first, then confirm that the Chinese description matches the intended operation. Do not add broad unrelated permissions.

Wait until the user confirms the selected permissions are enabled.

## 4. Complete Version Management & Release

Open **应用发布 > 版本管理与发布** (Version Management & Release). Tell the user to create a version, include the newly requested scopes, submit it, and complete any administrator approval required by the organization.

An application may exist while its newly selected scopes remain ineffective. Permission changes take effect only after a version containing them is published and approved.

Wait until the user confirms the version is published or identifies an administrator-approval blocker.

## 5. Add a custom robot under Group Bots

Open the official guide with a browser tool or:

```bash
python scripts/open_setup.py webhook-guide
```

In the target Feishu group, guide the user through:

1. Open **设置**.
2. Select **群机器人** (Group Bots).
3. Click **添加机器人**.
4. Select **自定义机器人**.
5. Set its name and description, then click **添加**.
6. Copy the generated Webhook URL to a local temporary clipboard or password manager. Do not paste it into chat.

If keyword verification is enabled, note the required keyword because every outgoing message must contain it. The bundled sender does not currently support timestamp/signature verification mode.

Wait until the user confirms the robot exists and the Webhook URL is available locally.

## 6. Install and configure locally on macOS/Linux

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/configure.py
```

The configurator requests App ID, hides App Secret and Webhook URL input, requests the Feishu tenant URL, writes `~/.config/codex/feishu-automation/config.json` with mode `600`, creates the download directory, and registers `feishu_automation` with Codex.

## 7. Install and configure locally on Windows

Run these commands in PowerShell from the repository root:

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$SkillRoot = Join-Path $HOME ".codex\skills"
$SkillPath = Join-Path $SkillRoot "feishu-automation"
New-Item -ItemType Directory -Force -Path $SkillRoot | Out-Null
New-Item -ItemType Junction -Path $SkillPath -Target (Get-Location).Path

& .\.venv\Scripts\python.exe .\scripts\configure.py
```

Before running the configurator, confirm `codex --version` works in the same PowerShell session. The configurator writes `%USERPROFILE%\.config\codex\feishu-automation\config.json`, limits its Windows ACL to the current user, and registers the MCP server.

Configuration schema:

```json
{
  "app_id": "cli_example",
  "app_secret": "replace-locally",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/replace-locally",
  "base_url": "https://your-tenant.feishu.cn",
  "default_folder_token": "",
  "download_dir": "~/Documents/Feishu"
}
```

## 8. Verify without external writes

Restart Codex, then run:

```bash
codex mcp get feishu_automation
```

macOS/Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/send_webhook.py --message "Feishu setup test" --dry-run
```

Windows PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe .\scripts\send_webhook.py --message "Feishu setup test" --dry-run
```

Only after explicit authorization should Codex create a real test document or send a real group message. Existing user-owned documents and folders must also be inside the application's data-access scope.
