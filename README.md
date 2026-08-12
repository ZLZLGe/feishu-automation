# Feishu Automation

让本地 Codex 通过 MCP 操作飞书文档、文件夹和附件，并通过飞书自定义机器人 Webhook 主动推送消息。

仓库同时包含：

- 可被 Codex 自动加载的 Skill。
- 本地 `feishu_automation` MCP Server。
- 飞书企业自建应用配置脚本。
- 自定义机器人 Webhook 发送器。
- “每日 AI 日报”完整示例。

## 功能

| 能力 | 说明 |
| --- | --- |
| 创建文档 | 创建飞书 DocX，可直接写入 Markdown 内容 |
| 读取文档 | 读取 Wiki/DocX 的标题、正文、版本及结构化 Block |
| 编辑文档 | 追加 Markdown、修改指定文本 Block、替换整篇正文 |
| 文件夹 | 创建由飞书应用管理的云空间文件夹 |
| 附件 | 列出、上传和下载文档附件 |
| Webhook 通知 | 向自定义机器人所在群发送文本、摘要和文档链接 |
| 日报发布 | 将 Markdown 发布为 DocX，再把三条摘要和全文链接发到群里 |

## 工作方式

```text
Codex
  -> feishu_automation MCP
  -> 飞书企业自建应用 API
  -> 创建、读取和编辑 DocX / 附件

日报或任务结果
  -> 飞书自定义机器人 Webhook
  -> 固定飞书群通知
```

企业应用的 `App ID`、`App Secret` 用于文档 API；自定义机器人的 `webhook_url` 只用于群消息推送，两者互不替代。

## 前置条件

- macOS 或 Linux。
- Python 3.11 及以上版本。
- Codex Desktop 或 Codex CLI。
- 一个飞书企业自建应用。
- 一个已加入目标群的飞书自定义机器人。

飞书应用按需开通以下权限，并在修改权限后发布新的应用版本：

- `docx:document`
- `docx:document.block:convert`
- `space:folder:create`
- 上传和下载云文档图片、附件的权限
- 修改云文档权限设置的权限
- 需要访问 Wiki 时，开通知识空间节点读取权限

权限名称和配置细节见 [`references/setup.md`](references/setup.md)。已有文档或文件夹还必须位于应用可访问的数据范围内。

## 安装

```bash
git clone https://github.com/ZLZLGe/feishu-automation.git
cd feishu-automation

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

将仓库注册为本地 Codex Skill：

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD" ~/.codex/skills/feishu-automation
```

如果该路径已经存在，不要覆盖；确认它是否已经指向当前仓库：

```bash
readlink ~/.codex/skills/feishu-automation
```

## 配置

运行交互式配置：

```bash
.venv/bin/python scripts/configure.py
```

依次输入：

1. 飞书应用 `App ID`。
2. 飞书应用 `App Secret`。
3. 自定义机器人完整 Webhook URL。
4. 飞书租户地址，例如 `https://example.feishu.cn`。

配置脚本会：

- 将凭据保存到 `~/.config/codex/feishu-automation/config.json`。
- 将配置文件权限设置为 `600`。
- 创建默认下载目录 `~/Documents/Feishu`。
- 将 MCP Server 注册为 `feishu_automation`。

完成后重启 Codex，并检查 MCP：

```bash
codex mcp get feishu_automation
```

## 在 Codex 中使用

可以直接描述任务，例如：

```text
使用 $feishu-automation 创建一篇名为“项目周报”的飞书文档，并写入这个 Markdown 文件。
```

```text
读取这篇飞书文档，修改“实验结论”这一段，其他内容不要动：https://example.feishu.cn/docx/...
```

```text
列出这篇文档的附件，把 result.csv 下载到默认目录。
```

```text
通过飞书 Webhook 发一条任务完成通知，并附上这篇文档的链接。
```

## MCP 工具

| 工具 | 用途 |
| --- | --- |
| `create_feishu_folder` | 创建飞书云空间文件夹 |
| `create_feishu_document` | 创建 DocX 并可选写入 Markdown |
| `read_feishu_document` | 读取文档纯文本和元数据 |
| `read_feishu_blocks` | 读取结构化 DocX Block |
| `append_feishu_markdown` | 在文档末尾追加 Markdown |
| `update_feishu_text_block` | 校验原文本后修改单个文本 Block |
| `replace_feishu_document` | 校验文档 ID 和版本后替换正文 |
| `list_feishu_attachments` | 列出文档附件 |
| `upload_feishu_attachment` | 上传不超过 20 MB 的附件 |
| `download_feishu_attachment` | 下载附件到本地 |
| `send_feishu_webhook` | 通过自定义机器人发送消息或文档链接 |

详细行为见 [`references/tools.md`](references/tools.md)。

## 每日 AI 日报

日报 Markdown 中加入以下结构，脚本会提取前三条作为群通知摘要：

```markdown
## 今日速览

- 第一条重点。
- 第二条重点。
- 第三条重点。
```

发布日报：

```bash
.venv/bin/python scripts/publish_daily_report.py \
  --title "AI 前沿热点日报 2026-08-12" \
  --file examples/daily-ai-report/report-template.md
```

执行顺序是：创建 DocX、写入完整 Markdown、设置组织内链接可读、提取三条摘要、通过 Webhook 推送摘要和全文链接。该命令会产生真实的飞书写入和群消息。

更多说明见 [`references/daily-ai-report.md`](references/daily-ai-report.md)。

## 单独发送 Webhook

先检查消息结构，不实际发送：

```bash
.venv/bin/python scripts/send_webhook.py \
  --message "任务已完成" \
  --dry-run
```

实际发送文本和链接：

```bash
.venv/bin/python scripts/send_webhook.py \
  --title "任务完成" \
  --message "结果文档已经生成。" \
  --link-url "https://example.feishu.cn/docx/..." \
  --link-text "查看结果"
```

当前发送器支持 URL 型自定义机器人 Webhook，不支持时间戳/签名校验模式。如果机器人启用了关键词校验，消息中必须包含配置的关键词。

## 本地数据与密钥

| 路径 | 内容 |
| --- | --- |
| `~/.config/codex/feishu-automation/config.json` | App ID、App Secret、Webhook 和默认目录配置 |
| `~/Documents/Feishu` | 默认附件下载目录 |
| `~/.codex/skills/feishu-automation` | 指向本仓库的 Skill 软链接 |
| `~/.codex/config.toml` | Codex MCP 注册信息，不保存飞书密钥 |

不要将真实配置文件、访问令牌或完整 Webhook URL提交到 Git。仓库中的 [`assets/config.example.json`](assets/config.example.json) 只有占位值。

## 验证

运行离线测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

验证 Skill 结构：

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

当前测试覆盖配置文件权限、DocX 创建、文件夹、附件流程、文档权限、Webhook 载荷、日报组合流程和 MCP 工具清单。

遇到权限、Wiki 解析、文档链接或 MCP 加载问题时，查看 [`references/troubleshooting.md`](references/troubleshooting.md)。

## 目录

```text
feishu-automation/
├── README.md
├── SKILL.md
├── agents/openai.yaml
├── assets/config.example.json
├── examples/daily-ai-report/
├── references/
├── scripts/
│   ├── configure.py
│   ├── feishu_mcp_server.py
│   ├── publish_daily_report.py
│   └── send_webhook.py
└── tests/test_feishu_automation.py
```

## License

本仓库目前未声明开源许可证。如需复用、分发或集成到其他项目，请先联系仓库所有者。
