# OpenClaw 核心增强 — 配置安全 · Skill 审查 · 记忆搜索

> 本文档供 OpenClaw Agent 读取并在宿主机上执行，覆盖三个关键场景：防止配置错误、第三方 Skill 安全审查、基于 Bedrock Embeddings 的记忆搜索。
>
> 幂等性原则：本文档中的所有操作均为幂等设计 — 执行前先检查当前状态，已存在的配置只验证不重复写入，重复执行不会产生副作用。
>
> 参考: [OpenClaw 文档](https://docs.openclaw.ai) | [Kiro CLI 安装与配置](../3.%20KiroCLI/kiro_install_config.md)

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有章节（第 1 ~ 4 节），理解：
- 第 1 节：配置安全防护 — 在 MEMORY.md 和 HEARTBEAT.md 中写入约束规则；通过 `skill-registry.json` 注册 Skill 来源并定期检查更新
- 第 2 节：Skill 安全审查 — skill-vetter 的审查维度和流程（本节为知识参考，无需执行命令）
- 第 3 节：Memory Search — 通过 LiteLLM 代理接入 Bedrock Embeddings
- 第 4 节：常用 Skill 安装 — 从 Anthropic 官方仓库安装 xlsx/pptx/pdf/docx/frontend-design 等常用 Skill
- 最终验收标准：第 1 节的规则已写入记忆、`skill-registry.json` 已创建、HEARTBEAT 更新检查已配置（注册表模式）、第 3 节的 `memory_search` API 可正常返回结果、第 4 节的常用 Skill 已安装并注册

### 第二步：检查当前环境状态

通读完成后，先执行以下诊断命令，收集当前状态：

```bash
# 1. MEMORY.md 中是否已有配置安全约束
grep -c "配置安全约束" ~/.openclaw/MEMORY.md 2>/dev/null || echo "MEMORY_RULE_NOT_FOUND"

# 2. MEMORY.md 中是否已有 Skill 安装安全约束
grep -c "Skill 安装安全约束" ~/.openclaw/MEMORY.md 2>/dev/null || echo "SKILL_VETTER_RULE_NOT_FOUND"

# 3. HEARTBEAT.md 中是否已有 Skill 更新检查任务（注册表模式）
grep -c "Skill 更新检查（注册表模式）" ~/.openclaw/HEARTBEAT.md 2>/dev/null || echo "HEARTBEAT_RULE_NOT_FOUND"
# 检查是否存在旧版（引用不存在的 skill-update-checker）
grep -c "skill-update-checker" ~/.openclaw/HEARTBEAT.md 2>/dev/null && echo "⚠️ HEARTBEAT_HAS_OLD_SKILL_UPDATE_CHECKER_REF" || true

# 3b. skill-registry.json 是否存在
python3 -c "
import json, os
p = os.path.expanduser('~/.openclaw/skill-registry.json')
d = json.load(open(p))
skills = d.get('skills', {})
git_skills = [k for k,v in skills.items() if v.get('gitRemote')]
print(f'REGISTRY_OK skills={len(skills)} git_trackable={len(git_skills)} lastCheck={d.get(\"_meta\",{}).get(\"lastFullCheck\",0)}')
" 2>/dev/null || echo "SKILL_REGISTRY_NOT_FOUND"

# 4. openclaw.json 中 memorySearch 是否已配置
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.openclaw/openclaw.json')))
ms = cfg.get('memorySearch', {})
print(f'memorySearch.enabled={ms.get(\"enabled\", False)}, model={ms.get(\"model\", \"NOT_SET\")}')
" 2>/dev/null || echo "OPENCLAW_CONFIG_READ_FAILED"

# 5. LiteLLM Proxy 是否已在运行
curl -s http://localhost:4000/health >/dev/null 2>&1 && echo "LITELLM_RUNNING" || echo "LITELLM_NOT_RUNNING"

# 6. pip 中 litellm 是否已安装
python3 -c "import litellm; print(f'litellm={litellm.__version__}')" 2>/dev/null || echo "LITELLM_NOT_INSTALLED"

# 7. AWS Credentials 是否可用
aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "AWS_CREDENTIALS_UNAVAILABLE"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：写入配置安全规则 | 第 1 节 | 无 | MEMORY.md / HEARTBEAT.md 已有对应规则时跳过，仅验证内容 |
| 阶段 2：Skill 审查知识 | 第 2 节 | 无 | 本节为知识参考，将审查规则写入 MEMORY.md 即可，无需执行其他命令 |
| 阶段 2b：Skill 注册表初始化 | 第 1 节 §3a-3c | 无 | `skill-registry.json` 已存在时跳过创建，仅验证；旧版 HEARTBEAT 引用 `skill-update-checker` 时自动替换 |
| 阶段 3：安装 LiteLLM | 第 3 节 Step 1-2 | AWS Credentials 可用 | AWS Credentials 不可用时暂停；LiteLLM 已安装且运行中时跳过 |
| 阶段 4：配置 memorySearch | 第 3 节 Step 3-5 | 阶段 3 完成 | `memorySearch` 已配置且 `enabled=true` 时跳过，仅验证 |
| 阶段 5：验证 | 第 3 节验证 | 阶段 4 完成 | 验证失败时展示错误并等待用户决策 |
| 阶段 6：安装常用 Skill | 第 4 节 | 无 | Skill 已存在时跳过；安装后注册到 `skill-registry.json` |

### 执行原则

1. **先诊断，后执行** — 不要跳过状态检查直接修改文件
2. **幂等性优先** — 每个写入操作前必须先检查目标内容是否已存在，已存在则跳过，不做任何修改
3. **遇到异常立即暂停** — 任何命令返回非零退出码或意外输出时，停下来向用户说明情况
4. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
5. **已完成的步骤可跳过** — 如果诊断发现某项配置已存在且内容正确，直接标记 ✅ 跳过
6. **修改 openclaw.json 前必须备份** — `cp openclaw.json openclaw.json.bak.$(date +%s)`

---

## 1. 配置安全：OpenClaw-Skill 防止配置错误

OpenClaw 的强大功能需要额外配置 Tools / Skills 才能完整体验，很多都需要修改配置文件 `openclaw.json`。配错一个字段，Gateway 可能起不来。OpenClaw 有 exec 权限可以修改配置，更需要防护。

### 问题场景

| 风险 | 后果 |
|------|------|
| JSON 字段名拼错 | Gateway 启动失败，所有 Agent 断连 |
| 配置值类型错误（如字符串写成数字） | 运行时异常，难以定位 |
| 删除了必要的配置项 | 功能静默失效 |
| Agent 静默重启 Gateway | 正在进行的对话中断，用户无感知 |

### 推荐做法

#### 1. 安装 OpenClaw-Skill 参考文档

OpenClaw-Skill 是一份覆盖安装、配置、通道、安全、多 Agent、故障排查等全部场景的结构化文档，8800+ 行。

安装方式：读取 [OpenClaw-Skill 配置手册](https://github.com/win4r/OpenClaw-Skill) 并将其内容纳入长期记忆。

安装后的约束：
- 修改 `openclaw.json` 前必须先查阅手册确认字段名、类型、取值范围
- 新增 Skill / Tool 时参考手册中的配置模板
- 遇到配置问题时按手册的故障排查流程处理

#### 2. 在记忆中写入硬规则

在 `MEMORY.md`（或等效的持久记忆文件）中写入以下约束：

```markdown
## 配置安全约束

- **修改 gateway 配置前必须先查 OpenClaw 手册**，确认配置项正确再改
- **重启 gateway 前必须先告知用户**，不要静默重启
- 修改 `openclaw.json` 后必须执行 JSON 合法性验证：
  ```bash
  python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
  ```
- 如果验证失败，立即回滚到修改前的版本，不要尝试重启
```

写入方式（幂等）：先检查 `~/.openclaw/MEMORY.md` 中是否已包含该约束，不存在时才追加：

```bash
MEMORY_FILE="$HOME/.openclaw/MEMORY.md"
if ! grep -q "配置安全约束" "$MEMORY_FILE" 2>/dev/null; then
  cat >> "$MEMORY_FILE" << 'EOF'

## 配置安全约束

- **修改 gateway 配置前必须先查 OpenClaw 手册**，确认配置项正确再改
- **重启 gateway 前必须先告知用户**，不要静默重启
- 修改 `openclaw.json` 后必须执行 JSON 合法性验证
- 如果验证失败，立即回滚到修改前的版本，不要尝试重启
EOF
  echo "✔ 配置安全约束已写入 $MEMORY_FILE"
else
  echo "✔ 配置安全约束已存在，跳过写入"
fi
```

#### 3. Skill 来源注册与定时更新检查

> ⚠️ **设计变更 (v1.1)**：原方案引用了不存在的 `skill-update-checker` Skill。新方案改为 Agent 原生逻辑 — 通过 `skill-registry.json` 记录每个 Skill 的安装来源，HEARTBEAT 心跳时直接执行 `git fetch` 比对，无需额外 Skill。

##### 3a. 初始化 Skill 注册表

`skill-registry.json` 是所有已安装 Skill 的来源登记簿，记录安装方式、git 远程地址、安装时的 commit hash。

先检查注册表是否已存在，不存在时创建初始版本：

```bash
REGISTRY_FILE="$HOME/.openclaw/skill-registry.json"
if [ -f "$REGISTRY_FILE" ]; then
  echo "✔ skill-registry.json 已存在，跳过创建"
  python3 -m json.tool "$REGISTRY_FILE" > /dev/null && echo "  JSON 格式合法" || echo "  ⚠️ JSON 格式异常，请检查"
else
  cat > "$REGISTRY_FILE" << 'REGISTRY_EOF'
{
  "_meta": {
    "description": "OpenClaw Skill 来源注册表 — 记录每个 Skill 的安装方式和 git 来源，供心跳更新检查使用",
    "version": "1.0",
    "lastFullCheck": 0
  },
  "skills": {
    "openclaw-guide": {
      "installMethod": "git-clone",
      "gitRemote": "https://github.com/win4r/OpenClaw-Skill.git",
      "installedCommit": "",
      "installedAt": "",
      "note": "OpenClaw 官方 Skill 手册，git clone 安装"
    },
    "skill-vetter": {
      "installMethod": "manual-copy",
      "gitRemote": "",
      "installedCommit": "",
      "installedAt": "",
      "note": "手动复制安装，无远程来源"
    },
    "tech-updates-collector": {
      "installMethod": "manual-copy",
      "gitRemote": "https://github.com/soldierxue/digital-11-enhancement4openclaw.git",
      "gitSubPath": "5. F1-TechUpdate/tech-updates-collector",
      "installedCommit": "",
      "installedAt": "",
      "note": "手动复制安装，来源为 digital-11 仓库子目录，可添加 git remote 实现更新检查"
    },
    "tech-updates-writer": {
      "installMethod": "manual-copy",
      "gitRemote": "https://github.com/soldierxue/digital-11-enhancement4openclaw.git",
      "gitSubPath": "6. F2-TechWriter/tech-updates-writer",
      "installedCommit": "",
      "installedAt": "",
      "note": "手动复制安装，来源为 digital-11 仓库子目录"
    },
    "web-article-saver": {
      "installMethod": "local-built",
      "gitRemote": "",
      "installedCommit": "",
      "installedAt": "",
      "note": "本地自建 Skill，无远程来源"
    },
    "kiro-cli": {
      "installMethod": "local-built",
      "gitRemote": "",
      "installedCommit": "",
      "installedAt": "",
      "note": "本地自建 Skill（ACP 集成），无远程来源"
    }
  }
}
REGISTRY_EOF
  echo "✔ skill-registry.json 已创建: $REGISTRY_FILE"
fi
```

**注册表字段说明**：

| 字段 | 说明 | 示例 |
|------|------|------|
| `installMethod` | 安装方式 | `git-clone`（可自动更新）/ `manual-copy`（需手动加 remote）/ `local-built`（跳过检查） |
| `gitRemote` | Git 远程仓库 URL | `https://github.com/win4r/OpenClaw-Skill.git` |
| `gitSubPath` | 仓库内子目录路径（仅 monorepo 场景） | `5. F1-TechUpdate/tech-updates-collector` |
| `installedCommit` | 安装时的 commit hash | `a1b2c3d`（首次注册时为空，首次检查后自动填充） |
| `installedAt` | 安装时间 | ISO 8601 格式 |
| `note` | 备注 | 人类可读的安装说明 |

##### 3b. 新 Skill 安装时注册来源

安装任何新 Skill 时，必须同步更新注册表。以下是注册脚本模板（幂等）：

```bash
REGISTRY_FILE="$HOME/.openclaw/skill-registry.json"
SKILL_NAME="<skill-name>"          # 替换为实际 Skill 名
INSTALL_METHOD="<method>"          # git-clone / manual-copy / local-built
GIT_REMOTE="<url-or-empty>"        # Git 远程 URL，无则留空

python3 -c "
import json, os, datetime
registry_path = os.path.expanduser('$REGISTRY_FILE')
with open(registry_path) as f:
    reg = json.load(f)

skill_name = '$SKILL_NAME'
if skill_name in reg['skills']:
    print(f'✔ {skill_name} 已在注册表中，跳过注册')
else:
    reg['skills'][skill_name] = {
        'installMethod': '$INSTALL_METHOD',
        'gitRemote': '$GIT_REMOTE',
        'installedCommit': '',
        'installedAt': datetime.datetime.utcnow().isoformat() + 'Z',
        'note': ''
    }
    with open(registry_path, 'w') as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    print(f'✔ {skill_name} 已注册到 skill-registry.json')
"
```

##### 3c. HEARTBEAT.md 写入更新检查任务

替换原来引用 `skill-update-checker/state.json` 的段落，改为基于注册表的 Agent 原生检查逻辑：

```bash
HEARTBEAT_FILE="$HOME/.openclaw/HEARTBEAT.md"

# 先清理旧版本（如果存在引用 skill-update-checker 的段落）
if grep -q "skill-update-checker/state.json" "$HEARTBEAT_FILE" 2>/dev/null; then
  echo "⚠️ 发现旧版 Skill 更新检查段落（引用不存在的 skill-update-checker），正在替换..."
  # 使用 python3 精确删除旧段落
  python3 -c "
import re, os
hb_path = os.path.expanduser('$HEARTBEAT_FILE')
with open(hb_path) as f:
    content = f.read()
# 删除从 '## Skill 更新检查' 到下一个 '##' 或文件末尾的段落
content = re.sub(r'\n## Skill 更新检查[^\n]*\n(?:(?!## ).+\n)*', '\n', content)
with open(hb_path, 'w') as f:
    f.write(content)
print('✔ 旧版段落已清理')
"
fi

# 写入新版本（幂等）
if grep -q "Skill 更新检查（注册表模式）" "$HEARTBEAT_FILE" 2>/dev/null; then
  echo "✔ Skill 更新检查（注册表模式）任务已存在，跳过写入"
else
  cat >> "$HEARTBEAT_FILE" << 'EOF'

## Skill 更新检查（注册表模式）🔄 (daily)
If 24+ hours since last check (see `skill-registry.json` → `_meta.lastFullCheck`):
1. 读取 `~/.openclaw/skill-registry.json`
2. 遍历 `skills` 中 `installMethod` 为 `git-clone` 的条目：
   - 进入 Skill 目录，执行 `git fetch origin`
   - 比较 `HEAD` 与 `origin/main`（或 `origin/master`）
   - 如有新 commit，记录变更摘要（`git log HEAD..origin/main --oneline`）
3. 遍历 `installMethod` 为 `manual-copy` 且 `gitRemote` 非空的条目：
   - 使用 `git ls-remote <gitRemote> HEAD` 获取远程最新 commit
   - 与 `installedCommit` 比较，不同则标记为"有更新可用"
4. `installMethod` 为 `local-built` 或 `gitRemote` 为空的条目 → 跳过
5. 更新 `_meta.lastFullCheck` 为当前 Unix 时间戳
6. 如果发现任何更新，通知用户并列出变更摘要
7. **不要自动更新，等待用户确认**
EOF
  echo "✔ Skill 更新检查（注册表模式）任务已写入 $HEARTBEAT_FILE"
fi
```

##### 3d. 为已有 Skill 补充 git remote（可选）

对于 `installMethod` 为 `manual-copy` 但有 `gitRemote` 的 Skill（如 `tech-updates-collector`），可以在 Skill 目录中初始化 git 追踪，使其支持 `git fetch` 比对：

```bash
# 示例：为 tech-updates-collector 添加 git 追踪
SKILL_DIR="$HOME/.openclaw/skills/tech-updates-collector"
if [ -d "$SKILL_DIR/.git" ]; then
  echo "✔ $SKILL_DIR 已有 git 仓库，跳过初始化"
else
  echo "为 tech-updates-collector 初始化 git 追踪..."
  # 注意：这里不做 git clone 覆盖，只是添加 remote 以便 fetch 比对
  # 实际文件保持不变，仅用于版本比较
  echo "⚠️ manual-copy 的 Skill 无法直接 git fetch（不是 git clone 的目录）"
  echo "  → 更新检查将使用 git ls-remote 比对远程 HEAD commit"
  echo "  → 如需完整 git 追踪，建议重新以 git clone 方式安装"
fi
```

> 对于 monorepo 来源的 Skill（如 `tech-updates-collector` 来自 `digital-11-enhancement4openclaw` 仓库的子目录），`git ls-remote` 只能检测仓库级别的更新，无法精确到子目录。这是可接受的 — 仓库有更新时提示用户检查即可。

### 效果

配置了以上三层防护后：

```
Agent 需要改配置
  → 先查 OpenClaw-Skill 手册（确认字段正确）
  → 告知用户即将修改的内容
  → 修改后验证 JSON 合法性
  → 验证通过 → 告知用户并重启 Gateway
  → 验证失败 → 回滚，不重启

安装新 Skill 时
  → skill-vetter 审查通过
  → 复制 Skill 文件到 skills/ 目录
  → 在 skill-registry.json 中注册来源信息
  → HEARTBEAT 心跳时自动检查更新

HEARTBEAT 心跳更新检查
  → 读取 skill-registry.json
  → git-clone 的 Skill → git fetch + 比对
  → manual-copy 有 gitRemote 的 → git ls-remote 比对
  → local-built 的 → 跳过
  → 有更新 → 通知用户，不自动更新
```

后续增加其它功能时，Agent 会更智能地提出有哪些可行的配置方式，而不是盲目修改。

---

## 2. Skill 安全审查：skill-vetter

从 ClawHub 或 GitHub 安装第三方 Skill 之前，必须先用 skill-vetter 审查，防止恶意或低质量的 Skill 进入运行环境。

### 审查维度

| 检查项 | 说明 | 风险等级 |
|--------|------|----------|
| System Prompt Override | 检查是否有可疑的 system-prompt-override，试图覆盖 Agent 的核心指令 | 🔴 高危 |
| 权限范围 | 检查读写了哪些文件，是否超出 Skill 声明的功能范围 | 🟡 中危 |
| 数据外传 | 检查是否有外传数据的行为（HTTP 请求、WebSocket 连接等） | 🔴 高危 |
| 危险命令 | 检查脚本中的危险命令（`rm -rf`、`curl | bash`、`eval` 等） | 🔴 高危 |

### 审查流程

```
需要安装第三方 Skill
  → skill-vetter 自动触发（或手动调用）
  → 扫描 SKILL.md：检查 system-prompt-override
  → 扫描 scripts/：检查文件读写范围、网络请求、危险命令
  → 生成审查报告（通过/警告/拒绝）
  → 通过 → 允许安装
  → 警告 → 提示用户风险点，由用户决定
  → 拒绝 → 阻止安装，说明原因
```

### 检查规则详解

#### 1. System Prompt Override 检查

扫描 `SKILL.md` 中是否包含试图覆盖 Agent 核心行为的指令：

```bash
# 可疑模式示例
grep -iE "ignore previous|forget all|you are now|override system|disregard instructions" SKILL.md
```

标记为 🔴 高危的模式：
- `ignore previous instructions`
- `you are now a different AI`
- `override system prompt`
- `forget all previous context`
- 任何试图重新定义 Agent 身份或行为的指令

#### 2. 权限范围检查

扫描 `scripts/` 目录下所有脚本文件，分析文件系统访问：

```bash
# 检查文件读写操作
grep -rn "open(\|read(\|write(\|os\.path\|shutil\|pathlib" scripts/

# 检查是否访问了敏感路径
grep -rn "\.ssh\|\.aws\|\.env\|/etc/passwd\|\.openclaw/openclaw\.json" scripts/
```

合理的权限范围：
- ✅ 读写 Skill 自身目录下的文件（`skills/<skill-name>/`）
- ✅ 读写 Skill 声明的输出目录
- ⚠️ 读取 OpenClaw 配置文件（需说明原因）
- 🔴 写入 OpenClaw 配置文件
- 🔴 访问 `.ssh`、`.aws`、`.env` 等敏感文件

#### 3. 数据外传检查

扫描是否有未声明的网络请求：

```bash
# 检查网络请求
grep -rn "requests\.\|urllib\|http\.client\|fetch(\|axios\|curl\|wget" scripts/

# 检查 WebSocket
grep -rn "websocket\|ws://" scripts/

# 检查 DNS / IP
grep -rn "socket\.connect\|socket\.create_connection" scripts/
```

合理的网络行为：
- ✅ 连接 Skill 声明的 API（如 Exa Search API）
- ✅ 连接本地服务（`localhost`、`127.0.0.1`）
- ⚠️ 连接未在 SKILL.md 中声明的外部服务
- 🔴 向未知服务器发送本地文件内容

#### 4. 危险命令检查

```bash
# 检查危险 shell 命令
grep -rn "rm -rf\|mkfs\|dd if=\|chmod 777\|curl.*|.*bash\|wget.*|.*sh" scripts/

# 检查代码注入风险
grep -rn "eval(\|exec(\|subprocess\.call.*shell=True\|os\.system(" scripts/

# 检查环境变量泄露
grep -rn "os\.environ\|process\.env" scripts/
```

### 审查报告格式

```
╔══════════════════════════════════════════╗
║  skill-vetter 审查报告                    ║
╠══════════════════════════════════════════╣
║  Skill:    awesome-translator            ║
║  来源:     github.com/user/skill-repo    ║
║  版本:     v1.2.0                        ║
╠══════════════════════════════════════════╣
║  ✅ System Prompt Override: 未发现       ║
║  ✅ 权限范围: 仅读写 Skill 目录          ║
║  ⚠️  数据外传: 连接 api.deepl.com        ║
║     → SKILL.md 中已声明翻译 API 依赖     ║
║  ✅ 危险命令: 未发现                      ║
╠══════════════════════════════════════════╣
║  结论: ⚠️ 警告 — 存在外部 API 调用       ║
║  建议: 确认 api.deepl.com 为预期的翻译   ║
║        服务后可安装                       ║
╚══════════════════════════════════════════╝
```

### 在 MEMORY.md 中添加审查规则

先检查是否已存在，不存在时才追加：

```bash
MEMORY_FILE="$HOME/.openclaw/MEMORY.md"
if ! grep -q "Skill 安装安全约束" "$MEMORY_FILE" 2>/dev/null; then
  cat >> "$MEMORY_FILE" << 'EOF'

## Skill 安装安全约束

- **安装任何第三方 Skill 前必须先运行 skill-vetter 审查**
- 审查结果为 🔴 拒绝的 Skill，不得安装
- 审查结果为 ⚠️ 警告的 Skill，必须告知用户风险点并等待确认
- 仅从 ClawHub 官方市场或用户明确指定的 GitHub 仓库安装 Skill
EOF
  echo "✔ Skill 安装安全约束已写入 $MEMORY_FILE"
else
  echo "✔ Skill 安装安全约束已存在，跳过写入"
fi
```

---

## 3. Memory Search — Bedrock Embeddings — Covered by AWS Credits

OpenClaw 的 `memory_search` 功能需要一个 Embedding 模型来实现语义搜索。Amazon Nova Multimodal Embeddings 成本约 $0.00014 / 1K tokens，每次查询不到一分钱，且可用 AWS Credits 抵扣。

### 当前状态

OpenClaw 原生的 Bedrock Provider 尚未完整支持 Embeddings 接入 — [PR #24892](https://github.com/openclaw/openclaw/pull/24892) 正在等待合并（之前的 [PR #20191](https://github.com/openclaw/openclaw/pull/20191) 有个新手错误）。

在 PR 合并之前，需要在 Bedrock 前面放一个 OpenAI 兼容的本地代理。两个方案：

### Option A: LiteLLM（推荐）

#### Step 1: 创建 LiteLLM 配置文件

先检查配置文件是否已存在：

```bash
LITELLM_CONFIG="$HOME/litellm_config.yaml"
if [ -f "$LITELLM_CONFIG" ]; then
  echo "✔ LiteLLM 配置文件已存在: $LITELLM_CONFIG，跳过创建"
  cat "$LITELLM_CONFIG"
else
  cat > "$LITELLM_CONFIG" << 'EOF'
# litellm_config.yaml
model_list:
  - model_name: nova-2-multimodal-embeddings-v1.0
    litellm_params:
      model: bedrock/amazon.nova-2-multimodal-embeddings-v1:0
      aws_region_name: us-east-1

litellm_settings:
  drop_params: true
  master_key: "local-only"
EOF
  echo "✔ LiteLLM 配置文件已创建: $LITELLM_CONFIG"
fi
```

#### Step 2: 安装并启动 LiteLLM Proxy

先检查是否已安装：

```bash
if python3 -c "import litellm" 2>/dev/null; then
  echo "✔ litellm 已安装: $(pip show litellm 2>/dev/null | grep Version)"
else
  echo "安装 litellm..."
  pip install 'litellm[proxy]'
fi

# 检查是否已在运行
if curl -s http://localhost:4000/health >/dev/null 2>&1; then
  echo "✔ LiteLLM Proxy 已在端口 4000 运行"
else
  echo "启动 LiteLLM Proxy..."
  litellm --config ~/litellm_config.yaml --port 4000 &
fi
```

> LiteLLM 会在 `http://localhost:4000` 启动一个 OpenAI 兼容的 API 代理，将请求转发到 Bedrock。

#### Step 3: 验证 LiteLLM Proxy

```bash
curl -s http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer local-only" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nova-2-multimodal-embeddings-v1.0",
    "input": "测试文本"
  }' | python3 -m json.tool
```

期望返回包含 `embedding` 数组的 JSON 响应。

#### Step 4: 配置 OpenClaw memory_search

先检查 `~/.openclaw/openclaw.json` 中是否已配置 `memorySearch`，已存在则仅验证，不存在才写入：

```bash
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

# 检查 memorySearch 是否已配置
if python3 -c "
import json, sys
with open('$OPENCLAW_CONFIG') as f:
    cfg = json.load(f)
ms = cfg.get('memorySearch', {})
if ms.get('enabled') == True and ms.get('model'):
    print(f'✔ memorySearch 已配置: provider={ms.get(\"provider\")}, model={ms.get(\"model\")}')
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
  echo "跳过写入，仅验证现有配置"
else
  echo "写入 memorySearch 配置..."
  # 备份
  cp "$OPENCLAW_CONFIG" "${OPENCLAW_CONFIG}.bak.$(date +%s)"
  # 使用 python3 合并写入（保留现有配置）
  python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f:
    cfg = json.load(f)
cfg['memorySearch'] = {
    'enabled': True,
    'provider': 'openai',
    'remote': {'baseUrl': 'http://localhost:4000', 'apiKey': 'local-only'},
    'model': 'nova-2-multimodal-embeddings-v1.0'
}
with open('$OPENCLAW_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
print('✔ memorySearch 配置已写入')
"
fi
```

目标配置：

```json
{
  "memorySearch": {
    "enabled": true,
    "provider": "openai",
    "remote": {
      "baseUrl": "http://localhost:4000",
      "apiKey": "local-only"
    },
    "model": "nova-2-multimodal-embeddings-v1.0"
  }
}
```

> ⚠️ 修改 `openclaw.json` 前请遵循第 1 节的配置安全约束：先备份、改后验证 JSON、告知用户再重启。

#### Step 5: 重启 Gateway

验证 JSON 合法性后，仅在配置有变更时重启：

```bash
# 验证 JSON 合法性
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
if [ $? -ne 0 ]; then
  echo "🔴 JSON 验证失败，回滚到备份"
  LATEST_BAK=$(ls -t ~/.openclaw/openclaw.json.bak.* 2>/dev/null | head -1)
  [ -n "$LATEST_BAK" ] && cp "$LATEST_BAK" ~/.openclaw/openclaw.json
  exit 1
fi

# 检查 Gateway 是否已在运行且 memorySearch 已生效
if openclaw gateway status 2>&1 | grep -q "running"; then
  # 如果 Step 4 中实际写入了新配置，才需要重启
  echo "Gateway 正在运行，重启以加载新配置..."
  openclaw gateway restart
else
  echo "Gateway 未运行，启动..."
  openclaw gateway restart
fi
```

> 基于 Amazon Nova Multimodal Embeddings 定价 ~$0.00014 / 1K tokens，平均每次查询 ~200 tokens。实际成本取决于查询文本长度和频率。

### LiteLLM 作为 systemd 服务（生产环境推荐）

如果需要 LiteLLM 持久运行，建议配置为 systemd 用户服务。先检查是否已存在：

```bash
SERVICE_FILE="$HOME/.config/systemd/user/litellm-proxy.service"

if [ -f "$SERVICE_FILE" ]; then
  echo "✔ litellm-proxy.service 已存在，检查运行状态..."
  systemctl --user status litellm-proxy.service --no-pager || true
else
  echo "创建 litellm-proxy.service..."
  mkdir -p ~/.config/systemd/user

  cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=LiteLLM Proxy for Bedrock Embeddings
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=%h/.local/bin/litellm --config %h/litellm_config.yaml --port 4000
Restart=always
RestartSec=5
Environment=HOME=%h
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF

  # 确保配置文件在 home 目录
  [ -f ~/litellm_config.yaml ] || cp litellm_config.yaml ~/litellm_config.yaml

  systemctl --user daemon-reload
  systemctl --user enable --now litellm-proxy.service
  echo "✔ litellm-proxy.service 已创建并启动"
fi

# 验证
systemctl --user is-active litellm-proxy.service
curl -s http://localhost:4000/health
```

### 验证 Memory Search 功能

配置完成后，通过 API 验证：

```bash
curl -s http://127.0.0.1:18789/api/memory/search \
  -H "Authorization: Bearer <gateway-token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "Bedrock embeddings"}' | python3 -m json.tool
```

### 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| LiteLLM 启动失败 | `litellm --config litellm_config.yaml --port 4000 --detailed_debug` | 检查 YAML 格式和 Bedrock 权限 |
| Bedrock 权限不足 | `aws bedrock list-foundation-models --region us-east-1` | 确认 IAM Role/User 有 `bedrock:InvokeModel` 权限 |
| Embeddings 返回空 | `curl localhost:4000/v1/embeddings ...` | 确认模型 ID 正确：`amazon.nova-2-multimodal-embeddings-v1:0` |
| memory_search 无结果 | `openclaw gateway status` | 确认 `memorySearch.enabled = true` 且 Gateway 已重启 |
| 端口 4000 被占用 | `ss -tlnp \| grep 4000` | 换用其它端口，同步更新 `openclaw.json` 中的 `baseUrl` |
| AWS Credentials 过期 | `aws sts get-caller-identity` | 刷新 credentials 或检查 Instance Profile |

### PR 合并后的迁移

当 [PR #24892](https://github.com/openclaw/openclaw/pull/24892) 合并后，可以直接使用 OpenClaw 原生 Bedrock Provider，无需 LiteLLM 代理：

```json
{
  "memorySearch": {
    "enabled": true,
    "provider": "bedrock",
    "model": "amazon.nova-2-multimodal-embeddings-v1:0",
    "region": "us-east-1"
  }
}
```

届时可以停用 LiteLLM 服务：

```bash
systemctl --user disable --now litellm-proxy.service
```

---

## 参考

- [OpenClaw 文档](https://docs.openclaw.ai)
- [Amazon Nova Embeddings 定价](https://aws.amazon.com/bedrock/pricing/)
- [LiteLLM Proxy 文档](https://docs.litellm.ai/docs/simple_proxy)
- [Bedrock Access Gateway](https://github.com/aws-samples/bedrock-access-gateway)
- [Kiro CLI 安装与配置](../3.%20KiroCLI/kiro_install_config.md)

---

## 4. 常用 Skill 安装：Anthropic 官方 Skills

以下是来自 [Anthropic Skills 仓库](https://github.com/anthropics/skills) 的常用 Skill，建议在初始化环境时一并安装，提升 Agent 处理文档、表格、演示文稿和前端设计的能力。

### Skill 列表

| Skill | 用途 | 来源 |
|-------|------|------|
| **xlsx** | 电子表格处理 — 创建、读取、编辑 `.xlsx/.xlsm/.csv/.tsv` 文件，支持公式、格式化、图表、数据清洗 | [skills/xlsx](https://github.com/anthropics/skills/tree/main/skills/xlsx) |
| **pptx** | 演示文稿处理 — 创建、读取、编辑 `.pptx` 文件，支持模板编辑、从零创建幻灯片、提取内容 | [skills/pptx](https://github.com/anthropics/skills/tree/main/skills/pptx) |
| **pdf** | PDF 处理 — 读取/提取文本和表格、合并/拆分、旋转、水印、表单填写、OCR、加密解密 | [skills/pdf](https://github.com/anthropics/skills/tree/main/skills/pdf) |
| **docx** | Word 文档处理 — 创建、读取、编辑 `.docx` 文件，支持目录、页眉页脚、表格、图片、批注、修订 | [skills/docx](https://github.com/anthropics/skills/tree/main/skills/docx) |
| **frontend-design** | 前端界面设计 — 生成高质量、有设计感的前端代码（HTML/CSS/JS、React、Vue 等），避免千篇一律的 AI 风格 | [skills/frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) |

### 安装方式

#### 方式一：Git Clone 整个仓库后复制（推荐）

```bash
SKILLS_DIR="$HOME/.openclaw/skills"
TEMP_DIR="/tmp/anthropic-skills-$(date +%s)"

# 1. Clone 仓库
git clone --depth 1 https://github.com/anthropics/skills.git "$TEMP_DIR"

# 2. 复制目标 Skill（幂等：已存在则跳过）
for SKILL in xlsx pptx pdf docx frontend-design; do
  if [ -d "$SKILLS_DIR/$SKILL" ]; then
    echo "✔ $SKILL 已存在，跳过"
  else
    cp -r "$TEMP_DIR/skills/$SKILL" "$SKILLS_DIR/$SKILL"
    echo "✔ $SKILL 已安装到 $SKILLS_DIR/$SKILL"
  fi
done

# 3. 清理临时目录
rm -rf "$TEMP_DIR"
```

#### 方式二：逐个下载 SKILL.md（轻量）

如果只需要核心指令文件，不需要附带的脚本：

```bash
SKILLS_DIR="$HOME/.openclaw/skills"
BASE_URL="https://raw.githubusercontent.com/anthropics/skills/main/skills"

for SKILL in xlsx pptx pdf docx frontend-design; do
  mkdir -p "$SKILLS_DIR/$SKILL"
  if [ -f "$SKILLS_DIR/$SKILL/SKILL.md" ]; then
    echo "✔ $SKILL/SKILL.md 已存在，跳过"
  else
    curl -sL "$BASE_URL/$SKILL/SKILL.md" -o "$SKILLS_DIR/$SKILL/SKILL.md"
    echo "✔ $SKILL/SKILL.md 已下载"
  fi
done
```

> ⚠️ 方式二只下载 `SKILL.md`，部分 Skill（如 pptx、pdf、docx）包含额外的参考文档和脚本，完整功能建议用方式一。

### 安装后注册到 skill-registry.json

安装完成后，将这些 Skill 注册到来源注册表（参见第 1 节 §3b）：

```bash
REGISTRY_FILE="$HOME/.openclaw/skill-registry.json"

python3 -c "
import json, os, datetime
registry_path = os.path.expanduser('$REGISTRY_FILE')
with open(registry_path) as f:
    reg = json.load(f)

skills_to_register = {
    'xlsx':             'Anthropic 官方 Skill — 电子表格处理',
    'pptx':             'Anthropic 官方 Skill — 演示文稿处理',
    'pdf':              'Anthropic 官方 Skill — PDF 处理',
    'docx':             'Anthropic 官方 Skill — Word 文档处理',
    'frontend-design':  'Anthropic 官方 Skill — 前端界面设计',
}

now = datetime.datetime.utcnow().isoformat() + 'Z'
added = []
for name, note in skills_to_register.items():
    if name not in reg['skills']:
        reg['skills'][name] = {
            'installMethod': 'git-clone',
            'gitRemote': 'https://github.com/anthropics/skills.git',
            'gitSubPath': f'skills/{name}',
            'installedCommit': '',
            'installedAt': now,
            'note': note
        }
        added.append(name)

if added:
    with open(registry_path, 'w') as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    print('已注册: ' + ', '.join(added))
else:
    print('所有 Skill 已在注册表中，跳过')
"
```

### 依赖说明

各 Skill 可能需要额外的系统依赖，按需安装：

| Skill | 主要依赖 | 安装命令 |
|-------|----------|----------|
| xlsx | openpyxl, pandas | `pip install openpyxl pandas` |
| pptx | pptxgenjs, markitdown, sharp | `npm install -g pptxgenjs` / `pip install "markitdown[pptx]"` |
| pdf | pypdf, pdfplumber, reportlab | `pip install pypdf pdfplumber reportlab` |
| docx | docx (npm), pandoc | `npm install -g docx` / `brew install pandoc` |
| frontend-design | 无额外依赖 | — |

> 💡 LibreOffice 是 pptx/docx/xlsx 多个 Skill 共用的可选依赖（用于 PDF 转换、公式重算等），建议提前安装：`brew install --cask libreoffice`

### 验证安装

```bash
# 检查所有 Skill 是否已就位
for SKILL in xlsx pptx pdf docx frontend-design; do
  if [ -f "$HOME/.openclaw/skills/$SKILL/SKILL.md" ]; then
    echo "✅ $SKILL"
  else
    echo "❌ $SKILL — 未找到 SKILL.md"
  fi
done
```

---

## 参考

- [OpenClaw 文档](https://docs.openclaw.ai)
- [Anthropic Skills 仓库](https://github.com/anthropics/skills)
- [Amazon Nova Embeddings 定价](https://aws.amazon.com/bedrock/pricing/)
- [LiteLLM Proxy 文档](https://docs.litellm.ai/docs/simple_proxy)
- [Bedrock Access Gateway](https://github.com/aws-samples/bedrock-access-gateway)
- [Kiro CLI 安装与配置](../3.%20KiroCLI/kiro_install_config.md)

---

**版本**: v1.2
**更新时间**: 2026-03-30
**变更**: 新增第 4 节 — Anthropic 官方常用 Skill（xlsx/pptx/pdf/docx/frontend-design）安装指引
