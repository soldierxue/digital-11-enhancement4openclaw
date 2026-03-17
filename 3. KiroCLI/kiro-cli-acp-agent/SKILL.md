---
name: kiro-cli-acp-agent
description: >
  Route coding tasks and knowledge queries to Kiro CLI via ACP (Agent Communication Protocol),
  offloading code generation, file operations, multi-step development, web search, and AWS documentation
  lookups from Claude API to Kiro's independent credit system.
  Kiro CLI has MCP servers for AWS Documentation and Exa Search built-in — all search/doc queries
  should be routed to Kiro first to save Claude API tokens.
  Supports multi-project concurrency with isolated contexts.
  Activate when user asks to: write code, create a project, refactor, fix bugs, write tests,
  写代码, 编程, 开发, 创建项目, 重构, 修复 bug, 写测试, 并行创建, 同时开发, 新项目,
  process PDF/images, scaffold a project, search the web, look up AWS docs, research a topic,
  搜索, 查文档, AWS 文档, 查资料, 搜一下, Google, 论文, 调研,
  or any coding/file-operation/search task.
---

# Kiro CLI Coding Agent

Route coding tasks and knowledge queries from OpenClaw to Kiro CLI via ACP JSON-RPC, reducing
Claude API token usage by 60–80%. Kiro autonomously handles code generation → file write → test → fix
loops, and leverages built-in MCP servers (AWS Documentation, Exa Search) for all search and
documentation lookups.

## Prerequisites

- Kiro CLI ≥ 1.20.0 installed and logged in (`kiro-cli auth status`)
- Python 3.10+
- Working directory: `~/kiro-projects/` (configurable via `KIRO_WORKING_DIR`)
- MCP Servers configured (see [kiro_mcp_recommended.md](../kiro_mcp_recommended.md)):
  - AWS Documentation MCP Server — AWS 文档搜索与阅读
  - Exa Search MCP Server — Web 搜索、论文搜索、公司调研

## Quick Use

```bash
# 一次性任务（无需 ACP，直接调用）
kiro-cli chat --no-interactive --trust-all-tools "创建一个 Flask API"

# 通过 ACP 客户端测试连接
python3 scripts/test_acp.py
```

## Task Routing

### → Send to Kiro CLI (priority)

- Write any code (scripts, APIs, tools, tests)
- Create or modify files
- System configuration, install dependencies
- Multi-step tasks requiring command execution + verification
- Code refactoring, performance optimization
- Project scaffolding
- Process images and PDFs
- Develop multiple projects in parallel
- **Web search** — 搜索、查资料、Google、调研、论文搜索、竞品分析（via Exa MCP）
- **AWS documentation** — 查 AWS 文档、搜索 AWS 服务用法、读取文档章节（via AWS Docs MCP）
- **Company/topic research** — 公司调研、技术调研、Twitter 搜索（via Exa MCP）

### → Handle directly by OpenClaw

- Conversational replies, casual chat
- Send messages (Feishu, Slack, email)
- Simple one-liner commands (< 3 lines, one-shot)
- Non-coding, non-search tasks
- Read paywalled articles (WeChat, Medium, SemiAnalysis, etc.) — 需要浏览器上下文，走 web-article-saver
- Any task not explicitly defined for Kiro CLI

## Workflow

1. Detect intent from user message:
   - Coding keywords: kiro, 写代码, 编程, 开发, coding, 创建项目, 重构, 修复 bug, 写测试, etc.
   - Search keywords: 搜索, 查资料, 搜一下, Google, 查文档, AWS 文档, 论文, 调研, search, look up, research, etc.
2. Extract project name if mentioned; call `bridge.is_same_project(name)` to check reuse
3. If existing project → reuse (same `project` param, shared context)
4. If new project → create new process (new `project` param, isolated context)
5. Send task via `scripts/kiro_bridge.py`:
   ```bash
   # Coding task
   python3 -c "
   import sys; sys.path.insert(0, 'SKILL_DIR/scripts')
   from kiro_bridge import KiroBridge
   with KiroBridge() as bridge:
       result = bridge.prompt('添加数据库连接', project='my-api')
       print(result['text'])
   "

   # Search / doc lookup (Kiro will use its MCP servers automatically)
   kiro-cli chat --no-interactive --trust-all-tools "search AWS docs for S3 lifecycle policies"
   kiro-cli chat --no-interactive --trust-all-tools "search the web for latest Kubernetes security best practices"
   ```
6. Report results to user: `result["text"]`, tool calls, usage stats

## API Reference

### KiroBridge (scripts/kiro_bridge.py)

| Method | Description |
|--------|-------------|
| `prompt(text, project=None, cwd=None, timeout=300)` | Send a coding task; returns structured result dict |
| `prompt_parallel(tasks, max_workers=3)` | Run multiple project prompts concurrently |
| `is_same_project(name)` | Check if a project with this name already exists |
| `list_projects()` | List all active projects and their status |
| `stop_project(name)` | Stop a single project's kiro-cli process |
| `stop()` | Stop all kiro-cli processes |

### ACPClient (scripts/acp_client.py)

| Method | Description |
|--------|-------------|
| `start(cwd=None)` | Launch kiro-cli in ACP mode, complete JSON-RPC handshake |
| `session_new(cwd)` | Create a new coding session |
| `session_load(session_id, cwd)` | Resume an existing session (preserves context) |
| `session_prompt(session_id, text, images=None, timeout=300)` | Send prompt, block until complete |
| `on_permission_request(handler)` | Register permission decision callback |
| `stop()` | Graceful shutdown with child process cleanup |

### Result Structure

```python
{
    "success": True,
    "project": "my-api",
    "text": "Created Flask API with ...",
    "tool_calls": [
        {"kind": "file_write", "title": "app.py", "status": "completed"}
    ],
    "usage": {
        "kiro_credits": 8.0,
        "kiro_context_pct": 23.5,
        "kiro_tool_calls": 3
    }
}
```

## Multi-Project Concurrency

| Scenario | Behavior |
|----------|----------|
| Same project name | Reuse process & session (shared context) |
| New project name | New kiro-cli process (isolated context) |
| No project param | Default single-project mode (backward compatible) |
| Context > 80% | Auto-rotate to new session, no impact on other projects |

Parallel tasks via `scripts/kiro_bridge.py` — use `prompt_parallel(tasks, max_workers=3)`, each task dict contains `project` and `text` keys.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| ACP handshake fails | `kiro-cli auth status` — re-login if needed |
| `session/new` no response | `KIRO_LOG_LEVEL=debug kiro-cli acp` to check logs |
| Task timeout | Increase `timeout` param; split large tasks |
| Permission request unhandled | Ensure `on_permission_request` callback is registered |
| Context overflow | Auto-managed at 80%; or call `reset_session()` manually |
| Orphan kiro-cli processes | `bridge.stop()` or `ps aux | grep kiro` then `kill` |
| Credits exhausted | Check Kiro subscription status; upgrade to Pro |
| Search/doc query not routed | Check MCP config: `cat ~/.kiro/settings/mcp.json` |
| Exa search fails | Verify network access to `mcp.exa.ai`; or check API Key if using local mode |
| AWS docs returns empty | Confirm `AWS_DOCUMENTATION_PARTITION` is `aws` (global) or `aws-cn` (China) |

## Built-in MCP Capabilities

Kiro CLI 已配置以下 MCP Server，搜索和文档查询应优先路由到 Kiro，避免消耗 Claude API Token。

| MCP Server | 触发场景 | 示例 prompt |
|------------|----------|-------------|
| AWS Documentation | 查 AWS 文档、服务用法、最佳实践 | "search AWS docs for Lambda cold start optimization" |
| Exa Web Search | 通用搜索、技术调研、最新资讯 | "search the web for React Server Components best practices" |
| Exa Research Papers | 学术论文搜索 | "find research papers on LLM inference optimization" |
| Exa Company Research | 公司调研、产品分析 | "research Snowflake's product offerings and pricing" |
| Exa Twitter Search | Twitter/X 内容搜索 | "search Twitter for AWS re:Invent 2025 announcements" |
| Exa Competitor Finder | 竞品发现 | "find competitors of Datadog in the observability space" |

> 配置详情参见 [kiro_mcp_recommended.md](../kiro_mcp_recommended.md)
