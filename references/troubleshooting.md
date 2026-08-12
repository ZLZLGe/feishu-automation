# Troubleshooting

## Permission denied

- Check that the relevant scope is enabled.
- Publish a new application version after changing scopes.
- Confirm the document or folder is in the application's data-access scope.
- For downloads, also check the document setting that controls copying, printing, and downloading.

## Wiki link cannot be resolved

Enable Wiki node-read permission and confirm the app can access the knowledge space. A Wiki URL token is not the underlying DocX document ID.

## Document was created but cannot be opened by recipients

Creation under an application identity does not automatically grant every user access. Share the folder/document appropriately or configure organization link permissions through an authorized workflow.

## Webhook rejected the message

- Confirm the URL is the complete custom-bot URL for the intended group.
- Check whether the robot requires a keyword and include it in the text.
- Timestamp/signature verification mode is not implemented by the bundled sender.
- A custom-bot Webhook cannot create or edit documents; those operations use the enterprise application credentials.

## MCP tools do not appear

- Confirm `.venv/bin/python` exists on macOS/Linux or `.venv\Scripts\python.exe` exists on Windows.
- Confirm `codex --version` works in the terminal used to run `configure.py`.
- Run `codex mcp get feishu_automation`.
- Restart Codex after adding or changing the MCP entry.

## Windows credential ACL error

- Run `scripts\configure.py` with the same Windows account that runs Codex.
- Do not move `config.json` to a shared or network directory after configuration.
- If the file was copied or restored, rerun `configure.py`; it will replace inherited permissions with a current-user-only ACL.
- PowerShell 5.1 or PowerShell 7 must be available so the configurator can set and verify the ACL.
