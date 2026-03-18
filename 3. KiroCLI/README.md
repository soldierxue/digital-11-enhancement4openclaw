# Kiro CLI 一站式配置指南 — 安装 · ACP · MCP

> 本文档供 OpenClaw Agent 读取并在宿主机上一次性完成 Kiro CLI 的核心能力配置。
>
> 执行顺序：安装登录（必须）→ ACP 集成（必须）→ MCP 扩展（可选，增强搜索能力）。
>
> 幂等性原则：所有操作执行前先检查当前状态，已存在的配置只验证不重复写入，重复执行不会产生副作用。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档以及以下三份详细文档，理解：
- **能力 A**（必须）：[kiro_install_config.md](./kiro_install_config.md) — Kiro CLI 安装/升级、Device Flow 登录认证、全局配置
- **能力 B**（必须）：[kiro_acp_integrate.md](./kiro_acp_integrate.md) — ACP 协议集成（Kiro 作为 OpenClaw 的 Peer Agent）
- **能力 C**（可选）：[kiro_mcp_recommended.md](./kiro_mcp_recommended.md) — Exa Search + AWS Documentation MCP Server 配置（增强搜索能力）

依赖关系：

```
能力 A（安装登录）  ← 必须
  │  Kiro CLI 可用 + 已认证
  ▼
能力 B（ACP 集成）  ← 必须，核心价值：编码任务路由到 Kiro，降低 Claude API 成本
  │
  ▼
能力 C（MCP 扩展）  ← 可选，增强：Exa 搜索 + AWS 文档查询
     F1 采集、Web 搜索等场景需要时再配置
```

> 能力 C 不阻塞能力 B。ACP 集成只依赖 Kiro CLI 已安装并登录，不依赖 MCP 配置。
> Exa MCP 主要服务于 F1 资讯采集（`web_search_advanced_exa` 日期过滤）等增强场景。

### 第二步：检查当前环境状态

通读完成后，执行以下综合诊断，一次性收集三项能力的状态：

```bash
echo "====== 能力 A：Kiro CLI 安装与登录 ======"
# A1. Kiro CLI 是否已安装
kiro-cli version 2>&1 || echo "KIRO_CLI_NOT_FOUND"

# A2. 是否已登录
kiro-cli auth status 2>&1 || echo "KIRO_AUTH_UNKNOWN"

# A3. PATH 是否包含 ~/.local/bin
echo $PATH | tr ':' '\n' | grep -q "$HOME/.local/bin" && echo "PATH_OK" || echo "PATH_MISSING_LOCAL_BIN"

# A4. 全局设置是否已配置
cat ~/.kiro/settings/settings.json 2>/dev/null || echo "SETTINGS_JSON_NOT_FOUND"

echo ""
echo "====== 能力 B：ACP 集成 ======"
# B1. Python 版本
python3 --version 2>&1 || echo "PYTHON3_NOT_FOUND"

# B2. 技能目录是否已存在
ls -la ~/.openclaw/skills/kiro-cli/SKILL.md 2>/dev/null && echo "ACP_SKILL_INSTALLED" || echo "ACP_SKILL_NOT_INSTALLED"

# B3. ACP 脚本文件完整性
for f in acp_client.py kiro_bridge.py usage_tracker.py test_acp.py; do
  ls ~/.openclaw/skills/kiro-cli/scripts/$f 2>/dev/null && echo "  $f ✔" || echo "  $f ✘"
done

# B4. 环境变量
grep -E "^KIRO_|^USAGE_STATS" ~/.openclaw/.env 2>/dev/null || echo "ACP_ENV_NOT_CONFIGURED"

# B5. OpenClaw Gateway 状态
openclaw gateway status 2>&1 || echo "GATEWAY_STATUS_UNKNOWN"

echo ""
echo "====== 能力 C：MCP Server 配置（可选） ======"
# C1. uvx 是否可用
uvx --version 2>&1 || echo "UVX_NOT_FOUND"

# C2. MCP 配置及 Exa 模式检测
python3 -c "
import json, os
try:
    cfg = json.load(open(os.path.expanduser('~/.kiro/settings/mcp.json')))
    servers = cfg.get('mcpServers', {})
    print(f'MCP_SERVERS: {list(servers.keys())}')
    # AWS Docs
    if 'awslabs.aws-documentation-mcp-server' in servers:
        print('AWS_DOCS=configured')
    else:
        print('AWS_DOCS=missing')
    # Exa
    exa = servers.get('exa', {})
    if exa:
        if 'url' in exa:
            url = exa['url']
            has_key = 'exaApiKey=' in url and 'exaApiKey=<' not in url
            has_adv = 'web_search_advanced_exa' in url
            print(f'EXA_MODE=remote key={has_key} advanced_search={has_adv}')
        elif 'command' in exa:
            print('EXA_MODE=local_npx (⚠️ 已过时)')
    else:
        print('EXA_NOT_CONFIGURED')
except Exception as e:
    print(f'MCP_CONFIG_READ_FAILED: {e}')
" 2>/dev/null || echo "MCP_CONFIG_NOT_EXISTS"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应能力 | 详细文档 | 前置条件 | 跳过条件 |
|------|----------|----------|----------|----------|
| 阶段 1：安装 Kiro CLI | 能力 A Part 1 | [kiro_install_config.md](./kiro_install_config.md) Step 1-3 | 无 | `kiro-cli version` 返回 ≥ 1.20.0 |
| 阶段 2：Device Flow 登录 | 能力 A Part 2 | [kiro_install_config.md](./kiro_install_config.md) Step 4-6 | 阶段 1 通过 | `kiro-cli auth status` 显示已认证 |
| 阶段 3：全局配置 | 能力 A Part 3 | [kiro_install_config.md](./kiro_install_config.md) Step 7-11 | 阶段 2 通过 | `settings.json` 已存在且 `defaultModel` 已设置 |
| 阶段 4：部署 ACP 文件 | 能力 B Part 2 | [kiro_acp_integrate.md](./kiro_acp_integrate.md) Step 3-7 | 阶段 3 完成 | `~/.openclaw/skills/kiro-cli/` 已存在且文件完整 |
| 阶段 5：ACP 端到端测试 | 能力 B Part 4 | [kiro_acp_integrate.md](./kiro_acp_integrate.md) Step 8-9 | 阶段 4 完成 | — |
| 阶段 6：OpenClaw 集成 | 能力 B Part 5 | [kiro_acp_integrate.md](./kiro_acp_integrate.md) Step 10-12 | 阶段 5 通过 | `.env` 中已有正确的 `KIRO_CLI_PATH` |
| 阶段 7：配置 AWS Docs MCP | 能力 C（可选） | [kiro_mcp_recommended.md](./kiro_mcp_recommended.md) Step 1-2 | 阶段 3 完成 + `uvx` 可用 | `mcp.json` 中已有 `awslabs.aws-documentation-mcp-server` |
| 阶段 8：配置 Exa MCP | 能力 C（可选） | [kiro_mcp_recommended.md](./kiro_mcp_recommended.md) Step 3 | 阶段 7 完成 | `mcp.json` 中已有 `exa` 且为远程 URL 模式 |
| 阶段 9：验证 MCP | 能力 C（可选） | [kiro_mcp_recommended.md](./kiro_mcp_recommended.md) Step 4-5 | 阶段 8 完成 | — |

> 阶段 7-9（能力 C）为可选。如果当前不需要 Exa 搜索或 AWS 文档查询能力，可跳过整个能力 C，后续需要时再单独执行。

### 执行原则

| 原则 | 说明 |
|------|------|
| 先诊断，后执行 | 不要跳过第二步的综合诊断直接开始配置 |
| 幂等性优先 | 每个文件/配置写入前先检查是否已存在且内容一致，已存在则跳过 |
| 依赖顺序：A → B 必须 | 能力 B（ACP）依赖能力 A（安装登录）完成 |
| 能力 C 可选 | MCP 扩展不阻塞 ACP 集成，可在能力 B 完成后按需配置 |
| 用户交互最小化 | 仅在 Device Flow 登录（阶段 2）和 Exa API Key 获取（阶段 8，如执行）时需要用户参与 |
| 遇到异常立即暂停 | 任何命令返回非零退出码或意外输出时，停下来向用户说明情况 |
| 每阶段汇报 | 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续 |
| 已完成的阶段可跳过 | 如果诊断发现某阶段已完成，直接标记 ✅ 跳过 |

---

## 能力 A：Kiro CLI 安装、登录与全局配置

> 📄 详细文档：[kiro_install_config.md](./kiro_install_config.md)

完成以下三件事：

1. **安装/升级 Kiro CLI** — 通过 `curl -fsSL https://cli.kiro.dev/install | bash` 安装到 `~/.local/bin/kiro-cli`
2. **Device Flow 登录** — 执行 `kiro-cli login --license free --use-device-flow`，用户在浏览器完成设备码验证（⚠️ 需要用户交互）
3. **全局配置** — 写入 `~/.kiro/settings/settings.json`（默认模型 `claude-opus-4-6`、`trustAllTools: true`）

### 验收标准

```bash
kiro-cli version          # ≥ 1.20.0
kiro-cli auth status      # 显示已认证
cat ~/.kiro/settings/settings.json  # defaultModel = claude-opus-4-6
```

---

## 能力 B：ACP 协议集成（Kiro 作为 Peer Agent）

> 📄 详细文档：[kiro_acp_integrate.md](./kiro_acp_integrate.md)
>
> 📄 ACP 脚本源文件：[kiro-cli-acp-agent/](./kiro-cli-acp-agent/)

通过 ACP（Agent Communication Protocol）将编码任务从 OpenClaw 路由到 Kiro CLI：

- OpenClaw（Claude API）仅负责意图识别和结果摘要，每次编码任务仅消耗 ~600–2,000 Token
- Kiro CLI 使用独立的 Kiro Credits 计费，自主完成代码生成 → 文件写入 → 测试执行 → 错误修复
- Claude API Token 使用量降低 60–80%

### 部署文件

```
~/.openclaw/skills/kiro-cli/
├── SKILL.md                # 任务路由规则
└── scripts/
    ├── acp_client.py       # ACP JSON-RPC 客户端（零依赖）
    ├── kiro_bridge.py      # 生产级封装（会话管理 + 进度回调）
    ├── usage_tracker.py    # 双轨计费追踪
    └── test_acp.py         # 端到端测试
```

### 验收标准

```bash
# 文件完整性
ls ~/.openclaw/skills/kiro-cli/SKILL.md
ls ~/.openclaw/skills/kiro-cli/scripts/{acp_client,kiro_bridge,usage_tracker,test_acp}.py

# 端到端测试
python3 ~/.openclaw/skills/kiro-cli/scripts/test_acp.py

# 环境变量
grep -E "^KIRO_CLI_PATH|^KIRO_WORKING_DIR|^USAGE_STATS_FILE" ~/.openclaw/.env
```

---

## 能力 C（可选）：MCP Server 配置（Exa Search + AWS Docs）

> 📄 详细文档：[kiro_mcp_recommended.md](./kiro_mcp_recommended.md)
>
> ⚠️ 本能力为可选增强。ACP 集成（能力 B）不依赖 MCP 配置。以下场景需要配置：
> - 使用 F1 资讯采集 Skill（依赖 `web_search_advanced_exa` 日期过滤）
> - 需要 Kiro CLI 在编码时查阅 AWS 官方文档
> - 需要 Web 搜索、公司调研、网页抓取等能力

为 Kiro CLI 配置两个推荐 MCP Server，扩展 Agent 的信息获取能力：

| MCP Server | 用途 | 认证 |
|------------|------|------|
| AWS Documentation | 搜索、阅读 AWS 官方文档 | 无需认证 |
| Exa Search | Web 搜索、高级搜索（日期过滤）、公司调研、网页抓取 | 推荐 API Key |

配置写入 `~/.kiro/settings/mcp.json`（全局生效）。

> ⚠️ Exa 远程 URL 模式为当前标准，工具名带 `_exa` 后缀。本地 npx 模式已过时，不推荐。

### 验收标准

```bash
# AWS Docs Server 依赖
uvx --version

# 配置文件包含两个 Server
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.kiro/settings/mcp.json')))
servers = list(cfg.get('mcpServers', {}).keys())
assert 'awslabs.aws-documentation-mcp-server' in servers, 'AWS Docs missing'
assert 'exa' in servers, 'Exa missing'
print('✔ MCP 配置验证通过:', servers)
"
```

---

## 综合验证清单

全部能力配置完成后，执行以下综合验证：

```bash
echo "=== 1. Kiro CLI（能力 A） ==="
kiro-cli version
kiro-cli auth status

echo ""
echo "=== 2. 全局配置（能力 A） ==="
python3 -c "
import json, os
s = json.load(open(os.path.expanduser('~/.kiro/settings/settings.json')))
print(f'  defaultModel: {s.get(\"defaultModel\", \"NOT_SET\")}')
print(f'  trustAllTools: {s.get(\"trustAllTools\", \"NOT_SET\")}')
"

echo ""
echo "=== 3. ACP 技能（能力 B） ==="
for f in SKILL.md scripts/acp_client.py scripts/kiro_bridge.py scripts/usage_tracker.py scripts/test_acp.py; do
  [ -f "$HOME/.openclaw/skills/kiro-cli/$f" ] && echo "  ✔ $f" || echo "  ✘ $f"
done

echo ""
echo "=== 4. 环境变量（能力 B） ==="
grep -E "^KIRO_|^USAGE_STATS" ~/.openclaw/.env 2>/dev/null || echo "  ✘ 未配置"

echo ""
echo "=== 5. Gateway（能力 B） ==="
openclaw gateway status 2>/dev/null || echo "  Gateway 状态未知"

echo ""
echo "=== 6. MCP Servers（能力 C，可选） ==="
python3 -c "
import json, os
try:
    cfg = json.load(open(os.path.expanduser('~/.kiro/settings/mcp.json')))
    for name in cfg.get('mcpServers', {}):
        print(f'  ✔ {name}')
except:
    print('  未配置（可选，不影响 ACP 核心功能）')
"
```

期望输出：能力 A + B 所有项目均为 ✔。能力 C 项目如未配置，显示为可选提示。

---

## 故障排查

| 症状 | 所属能力 | 排查方式 | 处理 |
|------|----------|----------|------|
| `kiro-cli` 命令不存在 | A | `ls ~/.local/bin/kiro-cli` | 重新安装；确认 PATH 包含 `~/.local/bin` |
| Device Flow 超时 | A | 重新执行 `kiro-cli login` | 设备码有效期有限，超时后重新获取 |
| ACP 握手失败 | B | `kiro-cli auth status` | 确认已登录；重新 `kiro-cli login` |
| `test_acp.py` 失败 | B | 检查网络 + Kiro CLI 版本 | 版本需 ≥ 1.20.0 |
| 子进程残留 | B | `ps aux \| grep kiro` | `bridge.stop()` 或手动 `kill` |
| 用户收到倒序消息 | B | 检查 MEMORY.md 单通道原则 | 参见 [kiro_acp_integrate.md](./kiro_acp_integrate.md) Part 6 |
| `uvx` 不可用 | C | `uvx --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Exa 只有 2 个工具 | C | 检查 `mcp.json` 中 Exa 配置 | 从 npx 本地模式迁移到远程 URL 模式 |
| Exa 缺少日期过滤 | C | 检查 URL 中是否含 `web_search_advanced_exa` | 在 `tools=` 参数中添加 |

> 各能力的完整故障排查表请参见对应详细文档。

---

## 参考链接

- [Kiro 官方网站](https://kiro.dev/)
- [Kiro CLI 安装指南](https://kiro.dev/docs/getting-started/installation/)
- [Kiro CLI MCP 文档](https://kiro.dev/docs/cli/mcp/)
- [Kiro CLI ACP 文档](https://kiro.dev/docs/cli/acp/)
- [ACP 协议规范](https://agentclientprotocol.org/)
- [Exa MCP 文档](https://exa.ai/docs/reference/exa-mcp)
- [AWS Documentation MCP Server](https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server)
- [uv 安装指南](https://docs.astral.sh/uv/getting-started/installation/)

---

**版本**: v1.0  
**更新时间**: 2026-03-18  
**依赖文档版本**: kiro_install_config.md / kiro_mcp_recommended.md / kiro_acp_integrate.md
