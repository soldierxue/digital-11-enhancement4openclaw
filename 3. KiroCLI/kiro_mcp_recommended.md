# Kiro CLI 推荐 MCP Server 安装与配置指南

> 本文档供 AI Agent（如 OpenClaw）读取并在本机自动执行，完成 Kiro CLI 推荐 MCP Server 的安装与配置。
>
> 参考:
> - [Kiro CLI MCP Examples](https://kiro.dev/docs/cli/mcp/examples/)
> - [Kiro CLI MCP 文档](https://kiro.dev/docs/cli/mcp/)
> - [AWS Documentation MCP Server](https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server)
> - [Exa MCP 文档](https://exa.ai/docs/reference/exa-mcp#kiro)

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有 Step（Step 1 ~ Step 6），理解：
- 目标：为 Kiro CLI 配置 AWS Documentation 和 Exa Search 两个 MCP Server
- 配置文件位置：`~/.kiro/settings/mcp.json`（全局）
- Exa 有两种模式（远程 URL + API Key / 远程免 Key），本地 npx 模式已过时不推荐
- 最终验收标准：Step 5 的功能测试通过

### 第二步：检查当前环境状态

通读完成后，先执行以下诊断命令，收集当前状态：

```bash
# 1. Kiro CLI 是否已安装并登录
kiro-cli version 2>&1 || echo "KIRO_CLI_NOT_FOUND"
kiro-cli auth status 2>&1 || echo "KIRO_AUTH_UNKNOWN"

# 2. uvx 是否可用（AWS Documentation Server 依赖）
uvx --version 2>&1 || echo "UVX_NOT_FOUND"

# 3. 现有 MCP 配置及 Exa 模式检测
python3 -c "
import json, os
try:
    cfg = json.load(open(os.path.expanduser('~/.kiro/settings/mcp.json')))
    servers = cfg.get('mcpServers', {})
    print(f'MCP_SERVERS: {list(servers.keys())}')
    exa = servers.get('exa', {})
    if exa:
        if 'url' in exa:
            url = exa['url']
            has_key = 'exaApiKey=' in url and 'exaApiKey=<' not in url
            has_adv = 'web_search_advanced_exa' in url
            print(f'EXA_MODE=remote key={has_key} advanced_search={has_adv}')
        elif 'command' in exa:
            print('EXA_MODE=local_npx (⚠️ 已过时，建议迁移到远程 URL 模式)')
    else:
        print('EXA_NOT_CONFIGURED')
except Exception as e:
    print(f'MCP_CONFIG_READ_FAILED: {e}')
" 2>/dev/null || echo "MCP_CONFIG_NOT_EXISTS"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：环境检查 | 前置条件 | 无 | Kiro CLI 未安装/未登录时暂停；`uvx` 未安装时暂停并提供安装命令 |
| 阶段 2：备份与配置 AWS Docs | Step 1-2 | 阶段 1 通过 | 已有 MCP 配置时先备份；若 `awslabs.aws-documentation-mcp-server` 已存在则跳过，不做任何修改 |
| 阶段 3：配置 Exa Search | Step 3 | 阶段 2 完成 | 若 `exa` 已存在则跳过，不做任何修改；若不存在，**必须询问用户**是否有 API Key；若当前为 npx 本地模式，建议迁移到远程 URL 模式 |
| 阶段 4：验证与测试 | Step 4-5 | 阶段 3 完成 | 测试失败时展示错误并等待用户决策 |
| 阶段 5：更新路由规则 | Step 6 | 阶段 4 通过 | SKILL.md 不存在时提示先完成 ACP 集成 |

### 执行原则

1. **先诊断，后执行** — 不要跳过状态检查直接修改配置文件
2. **幂等性优先** — 修改 MCP 配置前必须先检查目标 Server 是否已存在，已存在则跳过，不做任何修改
3. **Exa 模式必须用户选择** — 推荐远程 URL + API Key 模式（完整 5 个工具）；如果用户无 API Key，可先用免 Key 模式验证
4. **遇到异常立即暂停** — 任何命令返回非零退出码或意外输出时，停下来向用户说明情况
5. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
6. **已完成的步骤可跳过** — 如果诊断发现 MCP Server 已配置且内容一致，直接标记 ✅ 跳过

---

## 背景

Kiro CLI 通过 MCP（Model Context Protocol）连接外部工具和数据源，扩展 Agent 的能力边界。以下两个 MCP Server 推荐所有 Kiro CLI 用户配置：

| MCP Server | 用途 | 认证方式 |
|------------|------|----------|
| AWS Documentation | 搜索、阅读、推荐 AWS 官方文档 | 无需认证（公开 API） |
| Exa Search | 实时 Web 搜索、高级搜索（日期过滤）、公司调研、网页抓取、人物搜索 | 推荐远程 URL + [API Key](https://dashboard.exa.ai/api-keys)；免 Key 模式有频率限制 |

## 前置条件

1. Kiro CLI 已安装并登录（参见 [kiro_install_config.md](./kiro_install_config.md)）
2. `uv` 已安装（AWS Documentation Server 依赖）：
   ```bash
   command -v uvx &>/dev/null && echo "✔ uvx 已安装" || echo "✘ 需要安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
   ```

## 配置文件路径

| 范围 | 路径 | 说明 |
|------|------|------|
| 全局配置 | `~/.kiro/settings/mcp.json` | 所有 Kiro CLI 会话生效 |
| 项目级配置 | `<项目目录>/.kiro/settings/mcp.json` | 仅该项目生效，优先级高于全局 |

> 推荐将以下两个 Server 配置到全局路径，所有项目共享。

## 执行流程

---

### Step 1: 备份现有配置

```bash
MCP_CONFIG="$HOME/.kiro/settings/mcp.json"
mkdir -p "$(dirname "$MCP_CONFIG")"

if [ -f "$MCP_CONFIG" ]; then
  cp "$MCP_CONFIG" "${MCP_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
  echo "✔ 已备份现有配置"
else
  echo "{ \"mcpServers\": {} }" > "$MCP_CONFIG"
  echo "✔ 已创建空配置文件"
fi
```

### Step 2: 配置 AWS Documentation MCP Server

AWS Documentation MCP Server 通过 `uvx` 运行，无需额外安装，无需 API Key。

```bash
python3 -c "
import json, os

mcp_path = os.path.expanduser('~/.kiro/settings/mcp.json')
try:
    with open(mcp_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

server_key = 'awslabs.aws-documentation-mcp-server'
if server_key in config['mcpServers']:
    print('⏭ AWS Documentation MCP Server 已存在，跳过配置（不做任何修改）')
else:
    config['mcpServers'][server_key] = {
        'command': 'uvx',
        'args': ['awslabs.aws-documentation-mcp-server@latest'],
        'env': {
            'FASTMCP_LOG_LEVEL': 'ERROR',
            'AWS_DOCUMENTATION_PARTITION': 'aws'
        },
        'disabled': False,
        'autoApprove': []
    }

    with open(mcp_path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')

    print('✔ AWS Documentation MCP Server 已配置')
"
```

> 如需查询 AWS 中国区文档，将 `AWS_DOCUMENTATION_PARTITION` 改为 `aws-cn`。
>
> 如在企业网络环境中遇到 User-Agent 被拦截，可添加环境变量：
> ```json
> "MCP_USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
> ```

### Step 3: 配置 Exa Search MCP Server

> ⚠️ **重要变更**：`exa-mcp-server` npm 本地包（v3.1.9+）已不再支持 `--tools` 参数，仅暴露 2 个默认工具。**推荐使用远程 URL 模式**。

Exa 提供两种接入方式：

| 方式 | 依赖 | API Key | 可用工具数 | 适用场景 |
|------|------|---------|-----------|----------|
| 远程 URL + API Key（推荐） | 无 | 需要（URL 参数） | 5 个（含高级搜索） | 生产使用，完整功能 |
| 远程 URL 免 Key | 无 | 不需要 | 默认工具集 | 快速验证 |
| ~~npm 本地包~~ | ~~Node.js + npx~~ | ~~需要~~ | ~~仅 2 个~~ | ~~⚠️ 已过时，不推荐~~ |

> 获取 API Key: [https://dashboard.exa.ai/api-keys](https://dashboard.exa.ai/api-keys)

**方式 A: 远程 URL + API Key（推荐，完整 5 个工具）**

```bash
python3 -c "
import json, os

mcp_path = os.path.expanduser('~/.kiro/settings/mcp.json')
try:
    with open(mcp_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

if 'exa' in config['mcpServers']:
    print('⏭ Exa MCP Server 已存在，跳过配置（不做任何修改）')
else:
    # 需要用户提供 API Key
    import sys
    api_key = sys.argv[1] if len(sys.argv) > 1 else '<your-api-key>'
    tools = 'web_search_exa,web_search_advanced_exa,company_research_exa,crawling_exa,people_search_exa'
    config['mcpServers']['exa'] = {
        'url': f'https://mcp.exa.ai/mcp?exaApiKey={api_key}&tools={tools}'
    }

    with open(mcp_path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')

    print('✔ Exa Search MCP Server 已配置（远程 URL 模式，带 API Key）')
" "\$EXA_KEY"
```

> Agent 执行时需先询问用户获取 API Key，替换 `$EXA_KEY`。

**方式 B: 远程 URL 免 Key（快速验证）**

```bash
python3 -c "
import json, os

mcp_path = os.path.expanduser('~/.kiro/settings/mcp.json')
try:
    with open(mcp_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

if 'exa' in config['mcpServers']:
    print('⏭ Exa MCP Server 已存在，跳过配置（不做任何修改）')
else:
    config['mcpServers']['exa'] = {
        'url': 'https://mcp.exa.ai/mcp'
    }

    with open(mcp_path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')

    print('✔ Exa Search MCP Server 已配置（远程模式，无 API Key，有调用频率限制）')
"
```

> 免 Key 模式有调用频率限制，适合验证配置。如需更高调用量，切换到方式 A。

**⚠️ 不推荐 — 本地 npx 模式（已过时）**

```
# exa-mcp-server@3.1.9+ 的 npx 模式忽略 --tools 参数，
# 仅暴露 web_search_exa 和 get_code_context_exa 两个工具。
# 缺少 web_search_advanced_exa（日期过滤）、crawling_exa 等关键工具。
# 如果当前配置为 npx 模式，建议迁移到远程 URL 模式。
```

### Step 4: 验证配置

```bash
echo "=== 当前 MCP 配置 ==="
cat ~/.kiro/settings/mcp.json

echo ""
echo "=== 验证 uvx 可用性（AWS Documentation Server 依赖）==="
uvx --version 2>/dev/null && echo "✔ uvx 可用" || echo "✘ uvx 不可用，请安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
```

期望配置文件内容（远程 URL + API Key 模式）：

```json
{
  "mcpServers": {
    "awslabs.aws-documentation-mcp-server": {
      "command": "uvx",
      "args": ["awslabs.aws-documentation-mcp-server@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR",
        "AWS_DOCUMENTATION_PARTITION": "aws"
      },
      "disabled": false,
      "autoApprove": []
    },
    "exa": {
      "url": "https://mcp.exa.ai/mcp?exaApiKey=<your-api-key>&tools=web_search_exa,web_search_advanced_exa,company_research_exa,crawling_exa,people_search_exa"
    }
  }
}
```

或（远程免 Key 模式）：

```json
{
  "mcpServers": {
    "awslabs.aws-documentation-mcp-server": {
      "...": "同上"
    },
    "exa": {
      "url": "https://mcp.exa.ai/mcp"
    }
  }
}
```

### Step 5: 测试 MCP Server 功能

启动 Kiro CLI 交互会话，测试两个 MCP Server 是否正常工作：

```bash
# 测试 AWS Documentation — 搜索 S3 文档
kiro-cli -p "search AWS documentation for S3 bucket naming rules"

# 测试 Exa Search — Web 搜索
kiro-cli -p "use Exa to search for latest AWS re:Invent announcements"
```

### Step 6: 更新 SKILL.md 路由规则

MCP Server 配置成功后，`kiro-cli-acp-agent/SKILL.md` 已包含更新后的路由规则，将 Web 搜索和 AWS 文档查询优先路由到 Kiro CLI。

确认 SKILL.md 已包含 MCP 路由：

```bash
grep -q "Built-in MCP Capabilities" "$(dirname "$0")/kiro-cli-acp-agent/SKILL.md" \
  && echo "✔ SKILL.md 已包含 MCP 路由规则" \
  || echo "✘ SKILL.md 需要更新，请参考最新版本"
```

路由变更摘要：
- **新增路由到 Kiro CLI**：Web 搜索（`web_search_exa`）、高级搜索（`web_search_advanced_exa`）、AWS 文档查询、公司调研（`company_research_exa`）、网页抓取（`crawling_exa`）
- **触发关键词新增**：搜索、查资料、搜一下、Google、查文档、AWS 文档、论文、调研、search、look up、research
- **从 OpenClaw 直接处理中移除**："信息查询" — 现在优先走 Kiro CLI 的 MCP Server

---

## MCP Server 功能参考

### AWS Documentation MCP Server

| 工具 | 说明 |
|------|------|
| `read_documentation` | 获取 AWS 文档页面并转换为 Markdown |
| `search_documentation` | 通过官方搜索 API 搜索 AWS 文档 |
| `read_sections` | 按标题提取文档特定章节 |
| `recommend` | 获取相关文档推荐（同服务热门、最新、相似、用户旅程） |

典型用法：
- "查找 S3 存储桶命名规则的文档"
- "搜索 Lambda 函数 URL 的配置方法"
- "推荐与这个 ECS 文档页面相关的内容"

### Exa Search MCP Server

> 以下为远程 URL 模式的工具列表（工具名带 `_exa` 后缀）。本地 npx 模式（v3.1.9+）已过时，仅暴露 2 个工具，不推荐使用。

| 工具 | 说明 |
|------|------|
| `web_search_exa` | 通用网页搜索 |
| `web_search_advanced_exa` | 高级搜索，支持 `startPublishedDate` / `endPublishedDate` 日期过滤 |
| `company_research_exa` | 公司信息调研 |
| `crawling_exa` | 指定 URL 内容抓取 |
| `people_search_exa` | 人物搜索 |

典型用法：
- "搜索最新的 Kubernetes 安全最佳实践"（`web_search_exa`）
- "搜索过去 24 小时内关于 LLM 推理优化的文章"（`web_search_advanced_exa` + 日期过滤）
- "调研 Snowflake 公司的产品和定价"（`company_research_exa`）

---

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| AWS Docs Server 启动失败 | `uvx --version` | 安装 uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| AWS Docs 搜索无结果 | 检查 `AWS_DOCUMENTATION_PARTITION` | 确认值为 `aws`（全球）或 `aws-cn`（中国） |
| Exa 连接超时 | `curl -s https://mcp.exa.ai/mcp` | 检查网络连接，确认可访问 exa.ai |
| Exa 只有 2 个工具 | 检查配置是否为 npx 本地模式 | 本地 npx（v3.1.9+）已过时，切换到远程 URL 模式 |
| Exa 缺少日期过滤 | 检查 URL 中是否包含 `web_search_advanced_exa` | 在 URL 的 `tools=` 参数中添加该工具 |
| MCP 配置不生效 | `cat ~/.kiro/settings/mcp.json` | 确认 JSON 格式正确；重启 Kiro CLI 会话 |
| 工具调用被拒绝 | 检查 `autoApprove` 配置 | 添加常用工具名到 `autoApprove` 数组，或使用 `--trust-all-tools` |

## 参考链接

- [Kiro CLI MCP Examples](https://kiro.dev/docs/cli/mcp/examples/)
- [Kiro CLI MCP 文档](https://kiro.dev/docs/cli/mcp/)
- [AWS Documentation MCP Server（GitHub）](https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server)
- [Exa MCP 文档](https://exa.ai/docs/reference/exa-mcp)
- [AWS Open Source MCP Servers](https://awslabs.github.io/mcp/)
- [uv 安装指南](https://docs.astral.sh/uv/getting-started/installation/)
