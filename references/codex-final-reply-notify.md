# Codex Final Reply Notifications

Use this workflow when the user wants each completed Codex turn's final reply sent to a Feishu group. It uses Codex's `notify` event and does not require a daemon, polling loop, or long-running process.

## Behavior

Codex invokes one external command for supported notification events. The currently supported event is `agent-turn-complete`. Its JSON payload includes `last-assistant-message`, which is the final Assistant reply for that turn.

`scripts/codex_notify_feishu.py`:

- accepts the event JSON as the final command argument;
- ignores events other than `agent-turn-complete`;
- sends only `last-assistant-message`, plus the working-directory project name;
- does not send `input-messages` or intermediary progress updates;
- truncates oversized replies with an explicit marker;
- reads the Webhook from the protected Feishu Automation config;
- writes no local log and returns success when notification delivery fails;
- can invoke a previous notifier after preserving its fixed arguments.

## Agent-managed setup

The Agent performs these steps instead of handing them to the user:

1. Confirm `~/.config/codex/feishu-automation/config.json` exists and passes the private-file permission check. Never copy the Webhook into `config.toml`.
2. Read the user-level `~/.codex/config.toml`. Project-level `.codex/config.toml` cannot configure `notify`.
3. Resolve absolute paths for the current platform's Python executable and `scripts/codex_notify_feishu.py`.
4. Inspect the existing `notify` array before changing it. If it already points to this adapter, do not add it again. If it already sends the same final reply to Feishu, replace that duplicate path rather than chaining both.
5. Back up `~/.codex/config.toml` with a timestamp.
6. If another notifier exists, serialize its complete command array as compact JSON and pass it through `--previous-notifier-json`. This preserves desktop notifications or other integrations.
7. Change only the user-level `notify` entry. Do not modify unrelated settings.
8. Run a dry run with a synthetic event. A dry run prints the outgoing payload and does not load or call the Webhook.
9. Ask for authorization before sending one real synthetic notification. Restart Codex after configuration.

## Configuration examples

With no existing notifier on macOS or Linux:

```toml
notify = [
  "/absolute/path/to/feishu-automation/.venv/bin/python",
  "/absolute/path/to/feishu-automation/scripts/codex_notify_feishu.py",
]
```

With an existing notifier:

```toml
notify = [
  "/absolute/path/to/feishu-automation/.venv/bin/python",
  "/absolute/path/to/feishu-automation/scripts/codex_notify_feishu.py",
  "--previous-notifier-json",
  "[\"/absolute/path/to/existing-notifier\",\"fixed-argument\"]",
]
```

Windows paths can use TOML literal strings to avoid escaping backslashes:

```toml
notify = [
  'C:\Users\you\feishu-automation\.venv\Scripts\python.exe',
  'C:\Users\you\feishu-automation\scripts\codex_notify_feishu.py',
]
```

The array is one command plus fixed arguments. Codex appends the event JSON as the last argument when a turn completes.

## Dry run

Use placeholder content only:

```bash
python scripts/codex_notify_feishu.py --dry-run '{"type":"agent-turn-complete","cwd":"/work/example","last-assistant-message":"Example final reply"}'
```

Expected message content:

```text
Codex 最终回复
项目：example

Example final reply
```

The adapter intentionally produces no local error log. Diagnose setup with the dry run, the private-config permission check, and a user-authorized real test rather than enabling persistent logging.
