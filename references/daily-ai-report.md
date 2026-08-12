# Daily AI Report Example

The example demonstrates one composition:

```text
Markdown report
  -> enterprise application creates Feishu DocX
  -> Markdown converts to document blocks
  -> custom-bot Webhook receives three highlights and the DocX link
```

Use a report containing this section so the publisher can extract the summary:

```markdown
## 今日速览

- First important development.
- Second important development.
- Third important development.
```

Publish an existing Markdown file:

```bash
.venv/bin/python scripts/publish_daily_report.py \
  --title "AI 前沿热点日报 2026-08-12" \
  --file examples/daily-ai-report/report-template.md
```

On Windows PowerShell:

```powershell
& .\.venv\Scripts\python.exe .\scripts\publish_daily_report.py `
  --title "AI 前沿热点日报 2026-08-12" `
  --file .\examples\daily-ai-report\report-template.md
```

The script creates a new document, writes the complete Markdown, extracts up to three entries from `今日速览`, and sends those entries plus the document link through the configured Webhook.

Use Codex automation, `launchd`, or cron only when scheduling is requested. Scheduling is separate from this Skill's Feishu integration.
