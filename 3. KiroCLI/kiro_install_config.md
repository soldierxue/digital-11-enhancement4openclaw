# Kiro CLI 自动安装与配置指南 — Ubuntu

> 本文档供 AI Agent（如 OpenClaw）读取并在本机自动执行，完成 Kiro CLI 的安装/升级、Device Flow 登录认证及全局配置。
>
> 参考: [Kiro 官方网站](https://kiro.dev/)

## 前置条件（需用户提前完成）

1. 当前系统为 Ubuntu 20.04 / 22.04 / 24.04 LTS
2. 用户具有 `sudo` 权限
3. 网络可正常访问 `cli.kiro.dev`
4. 用户已拥有以下任一账号（用于登录认证）：
   - **Free（免费版）**：AWS Builder ID、Google 账号 或 GitHub 账号
   - **Pro（专业版）**：AWS IAM Identity Center 账号

## 执行流程

Agent 按以下步骤依次执行。Part 1 全程自动化；Part 2 需要用户在手机或电脑浏览器上完成设备码验证；Part 3 全程自动化。

---

## Part 1: 安装或升级 Kiro CLI

### Step 1: 检测当前 Kiro CLI 安装状态

```bash
if command -v kiro-cli &>/dev/null; then
  echo "✔ Kiro CLI 已安装"
  echo "  当前版本: $(kiro-cli version 2>/dev/null || echo '版本未知')"
  echo "  安装路径: $(which kiro-cli)"
else
  echo "✘ Kiro CLI 未安装"
fi
```

### Step 2: 安装或升级 Kiro CLI

**如果未安装 Kiro CLI：**

```bash
curl -fsSL https://cli.kiro.dev/install | bash
```

> 安装脚本会自动下载最新版本并安装到 `~/.local/bin/kiro-cli`，同时将路径添加到 `$PATH`。

安装完成后刷新环境变量：

```bash
source ~/.bashrc
```

**如果已安装 Kiro CLI：**

重新执行安装脚本即可升级到最新版本：

```bash
curl -fsSL https://cli.kiro.dev/install | bash
source ~/.bashrc
```

### Step 3: 验证安装结果

```bash
kiro-cli version
```

期望输出类似：`kiro-cli 1.x.x`。如果命令不存在，检查 `~/.local/bin` 是否在 `$PATH` 中：

```bash
echo $PATH | tr ':' '\n' | grep -q "$HOME/.local/bin" && echo "✔ PATH 已包含" || echo "✘ 需要添加 PATH"
```

如果 PATH 未包含，手动添加：

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Part 2: 通过 Device Flow 登录认证

在服务器环境（无本地浏览器）中，Kiro CLI 支持 Device Flow 模式完成认证。Agent 执行登录命令后，会输出一个设备码和 URL，用户需要在手机或电脑浏览器上打开链接并输入设备码完成验证。

### Step 4: 检查当前登录状态

在执行登录之前，先检查 Kiro CLI 是否已经登录：

```bash
if kiro-cli auth status 2>&1 | grep -qi "authenticated\|logged in\|active"; then
  echo "✔ Kiro CLI 已登录，跳过认证步骤"
  kiro-cli auth status
else
  echo "✘ Kiro CLI 未登录，需要执行 Device Flow 认证"
fi
```

> 如果已登录，直接跳到 Part 3。如果未登录，继续 Step 5。

### Step 5: 选择登录类型并执行

**Free（免费版）— 使用 Builder ID / Google / GitHub 登录：**

```bash
kiro-cli login --license free --use-device-flow
```

执行后终端会输出类似信息：

```
To sign in, open the following URL in a browser:
  https://device.sso.us-east-1.amazonaws.com/
Enter the code: XXXX-XXXX
Waiting for authentication...
```

> 请将上述 URL 和设备码告知用户，指导用户在手机或电脑浏览器上：
> 1. 打开显示的 URL
> 2. 输入终端中显示的设备码（如 `XXXX-XXXX`）
> 3. 选择 Builder ID、Google 或 GitHub 登录方式完成认证
> 4. 认证成功后终端会自动继续

**Pro（专业版）— 使用 AWS IAM Identity Center 登录：**

```bash
kiro-cli login --license pro --use-device-flow
```

执行后同样会输出设备码和 URL。用户需要：

1. 打开显示的 URL
2. 输入设备码
3. 使用 AWS IAM Identity Center 凭证登录
4. 认证成功后终端会自动继续

> Pro 版本需要组织管理员已在 AWS IAM Identity Center 中配置了 Kiro 的访问权限。
>
> 参考：[AWS Builder ID 注册](https://profile.aws.amazon.com/) | [AWS IAM Identity Center](https://aws.amazon.com/iam/identity-center/)

### Step 6: 验证登录状态

```bash
kiro-cli auth status 2>/dev/null || kiro-cli version
```

如果已登录，输出中应包含当前用户信息或不报认证错误。

---

## Part 3: 全局配置

设置 Kiro CLI 的全局默认配置，使每个新 Session 自动遵循这套配置。

### Step 7: 创建全局配置目录

```bash
mkdir -p ~/.kiro/settings
```

### Step 8: 配置默认模型与全局设置

将全局设置写入 `~/.kiro/settings/settings.json`：

```bash
python3 -c "
import json, os

settings_path = os.path.expanduser('~/.kiro/settings/settings.json')

# 读取现有配置
try:
    with open(settings_path, 'r') as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

# 设置默认模型为 Claude Opus 4.6
settings['defaultModel'] = 'claude-opus-4-6'

# 信任所有工具（跳过工具执行确认）
settings['trustAllTools'] = True

# 写回配置
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')

print('✔ 全局设置已写入:', settings_path)
print(json.dumps(settings, indent=2))
"
```

> 可用模型列表：
>
> | 模型 | 标识 | 说明 |
> |------|------|------|
> | Auto | `auto` | 自动选择最佳模型 |
> | Claude Opus 4.6 | `claude-opus-4-6` | 最强推理能力（推荐） |
> | Claude Opus 4.5 | `claude-opus-4-5` | 高级推理 |
> | Claude Sonnet 4.5 | `claude-sonnet-4-5` | 平衡性能与速度 |
> | Claude Sonnet 4 | `claude-sonnet-4` | 快速响应 |
> | Claude Haiku 4.5 | `claude-haiku-4-5` | 最快速度 |

### Step 9: 配置全局上下文（可选）

如果需要为所有 Kiro CLI 会话提供全局上下文信息（如项目约定、编码规范等），可以创建全局上下文文件：

```bash
cat > ~/.kiro/context.md << 'EOF'
# 全局上下文

- 默认使用中文回复
- 代码注释使用英文
- 遵循项目现有的代码风格
EOF

echo "✔ 全局上下文已写入: ~/.kiro/context.md"
```

> 此文件内容会自动注入到每个 Kiro CLI 会话中，Agent 可根据用户需求自定义内容。

### Step 10: 配置 MCP 服务器（可选）

如果需要为 Kiro CLI 配置全局 MCP 服务器，编辑 `~/.kiro/settings/mcp.json`：

```bash
python3 -c "
import json, os

mcp_path = os.path.expanduser('~/.kiro/settings/mcp.json')

try:
    with open(mcp_path, 'r') as f:
        mcp_config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    mcp_config = {}

if 'mcpServers' not in mcp_config:
    mcp_config['mcpServers'] = {}

# 示例：添加 AWS 文档 MCP 服务器
mcp_config['mcpServers']['aws-docs'] = {
    'command': 'uvx',
    'args': ['awslabs.aws-documentation-mcp-server@latest'],
    'env': {
        'FASTMCP_LOG_LEVEL': 'ERROR'
    },
    'disabled': False,
    'autoApprove': []
}

with open(mcp_path, 'w') as f:
    json.dump(mcp_config, f, indent=2)
    f.write('\n')

print('✔ MCP 配置已写入:', mcp_path)
print(json.dumps(mcp_config, indent=2))
"
```

> MCP 配置说明：
> - 全局 MCP 配置路径：`~/.kiro/settings/mcp.json`
> - 项目级 MCP 配置路径：`<项目目录>/.kiro/settings/mcp.json`
> - 项目级配置优先级高于全局配置
> - `uvx` 命令需要先安装 `uv`（Python 包管理器）：`curl -LsSf https://astral.sh/uv/install.sh | sh`

### Step 11: 验证全局配置

```bash
echo "=== Kiro CLI 版本 ==="
kiro-cli version

echo ""
echo "=== 全局设置 ==="
cat ~/.kiro/settings/settings.json 2>/dev/null || echo "未找到 settings.json"

echo ""
echo "=== 全局上下文 ==="
cat ~/.kiro/context.md 2>/dev/null || echo "未找到 context.md"

echo ""
echo "=== MCP 配置 ==="
cat ~/.kiro/settings/mcp.json 2>/dev/null || echo "未找到 mcp.json"
```

---

## 完整一键脚本

将 Part 1 和 Part 3 整合为可直接执行的脚本（Part 2 登录认证需要用户交互，脚本会暂停等待）：

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "  Kiro CLI 安装与配置一键脚本"
echo "=========================================="

# ---- Part 1: 安装/升级 Kiro CLI ----
echo ""
echo "=== Part 1: 安装/升级 Kiro CLI ==="

if command -v kiro-cli &>/dev/null; then
  echo "Kiro CLI 已安装，当前版本: $(kiro-cli version 2>/dev/null || echo '未知')"
  echo "尝试升级到最新版本..."
else
  echo "Kiro CLI 未安装，开始安装..."
fi

curl -fsSL https://cli.kiro.dev/install | bash
export PATH="$HOME/.local/bin:$PATH"

echo ""
echo "=== 当前 Kiro CLI 版本 ==="
kiro-cli version

# ---- Part 2: Device Flow 登录 ----
echo ""
echo "=== Part 2: 登录认证 ==="

# 检查是否已登录
if kiro-cli auth status 2>&1 | grep -qi "authenticated\|logged in\|active"; then
  echo "✔ Kiro CLI 已登录，跳过认证步骤"
  kiro-cli auth status
else
  echo "Kiro CLI 未登录，需要执行 Device Flow 认证"
  echo ""
  echo "请选择登录类型："
  echo "  1) Free（免费版）— Builder ID / Google / GitHub"
  echo "  2) Pro（专业版）— AWS IAM Identity Center"
  echo "  3) 跳过登录（稍后手动执行）"
  echo ""
  read -rp "请输入选项 [1/2/3]: " LOGIN_CHOICE

  case "$LOGIN_CHOICE" in
    1)
      echo "启动 Free 版 Device Flow 登录..."
      echo "⚠ 请在手机或电脑浏览器上完成设备码验证"
      kiro-cli login --license free --use-device-flow
      ;;
    2)
      echo "启动 Pro 版 Device Flow 登录..."
      echo "⚠ 请在手机或电脑浏览器上完成设备码验证"
      kiro-cli login --license pro --use-device-flow
      ;;
    3)
      echo "跳过登录。稍后可手动执行："
      echo "  Free: kiro-cli login --license free --use-device-flow"
      echo "  Pro:  kiro-cli login --license pro --use-device-flow"
      ;;
    *)
      echo "无效选项，跳过登录。"
      ;;
  esac
fi

# ---- Part 3: 全局配置 ----
echo ""
echo "=== Part 3: 全局配置 ==="

# 创建配置目录
mkdir -p ~/.kiro/settings

# 写入全局设置
python3 -c "
import json, os

settings_path = os.path.expanduser('~/.kiro/settings/settings.json')
try:
    with open(settings_path, 'r') as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

settings['defaultModel'] = 'claude-opus-4-6'
settings['trustAllTools'] = True

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')

print('✔ 全局设置已写入')
print(json.dumps(settings, indent=2))
"

# 写入全局上下文
cat > ~/.kiro/context.md << 'EOF'
# 全局上下文

- 默认使用中文回复
- 代码注释使用英文
- 遵循项目现有的代码风格
EOF
echo "✔ 全局上下文已写入"

# 写入 MCP 配置
python3 -c "
import json, os

mcp_path = os.path.expanduser('~/.kiro/settings/mcp.json')
try:
    with open(mcp_path, 'r') as f:
        mcp_config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    mcp_config = {}

if 'mcpServers' not in mcp_config:
    mcp_config['mcpServers'] = {}

mcp_config['mcpServers']['aws-docs'] = {
    'command': 'uvx',
    'args': ['awslabs.aws-documentation-mcp-server@latest'],
    'env': {'FASTMCP_LOG_LEVEL': 'ERROR'},
    'disabled': False,
    'autoApprove': []
}

with open(mcp_path, 'w') as f:
    json.dump(mcp_config, f, indent=2)
    f.write('\n')

print('✔ MCP 配置已写入')
"

# ---- 验证 ----
echo ""
echo "=========================================="
echo "  安装配置完成"
echo "=========================================="
echo ""
echo "Kiro CLI 版本: $(kiro-cli version 2>/dev/null || echo '未知')"
echo "默认模型: Claude Opus 4.6"
echo "Trust All Tools: 已启用"
echo "全局上下文: ~/.kiro/context.md"
echo "全局设置: ~/.kiro/settings/settings.json"
echo "MCP 配置: ~/.kiro/settings/mcp.json"
echo ""
echo "使用方式："
echo "  启动交互会话: kiro-cli"
echo "  单次提问:     kiro-cli -p \"你的问题\""
echo "  查看帮助:     kiro-cli --help"
```

Agent 可将此脚本保存为 `setup-kiro-cli.sh` 并执行：

```bash
bash setup-kiro-cli.sh
```

---

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| `kiro-cli` 命令不存在 | `ls ~/.local/bin/kiro-cli` | 确认安装成功；执行 `source ~/.bashrc` 或手动添加 PATH |
| 安装脚本下载失败 | `curl -I https://cli.kiro.dev/install` | 检查网络连接或 DNS 配置 |
| Device Flow 超时 | 重新执行 `kiro-cli login` 命令 | 设备码有效期有限，超时后需重新获取 |
| 登录后仍提示未认证 | `kiro-cli auth status` | 确认 token 未过期；重新执行 `kiro-cli login` |
| Pro 登录失败 | 确认 IAM Identity Center 配置 | 联系组织管理员确认 Kiro 访问权限已配置 |
| `settings.json` 不生效 | `cat ~/.kiro/settings/settings.json` | 确认 JSON 格式正确，无语法错误 |
| 模型选择无效 | `kiro-cli version` | 确认 Kiro CLI 版本支持所选模型 |
| MCP 服务器启动失败 | `uvx --version` | 确认 `uv` 已安装：`curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `context.md` 未生效 | `cat ~/.kiro/context.md` | 确认文件路径正确，内容为有效 Markdown |
| PATH 环境变量丢失 | `echo $PATH \| tr ':' '\n'` | 将 `export PATH="$HOME/.local/bin:$PATH"` 添加到 `~/.bashrc` |

## Kiro CLI 常用命令参考

| 命令 | 说明 |
|------|------|
| `kiro-cli` | 启动交互式会话 |
| `kiro-cli -p "问题"` | 单次提问模式 |
| `kiro-cli version` | 查看当前版本 |
| `kiro-cli login --license free --use-device-flow` | Free 版 Device Flow 登录 |
| `kiro-cli login --license pro --use-device-flow` | Pro 版 Device Flow 登录 |
| `kiro-cli auth status` | 查看登录状态 |
| `kiro-cli --help` | 查看帮助信息 |

## 配置文件路径参考

| 文件 | 路径 | 说明 |
|------|------|------|
| 全局设置 | `~/.kiro/settings/settings.json` | 默认模型、工具信任等 |
| 全局上下文 | `~/.kiro/context.md` | 注入到每个会话的上下文 |
| 全局 MCP 配置 | `~/.kiro/settings/mcp.json` | 全局 MCP 服务器配置 |
| 项目级 MCP 配置 | `<项目>/.kiro/settings/mcp.json` | 项目级 MCP 配置（优先级更高） |

## 参考链接

- [Kiro 官方网站](https://kiro.dev/)
- [Kiro CLI 安装指南](https://kiro.dev/docs/getting-started/installation/)
- [AWS Builder ID 注册](https://profile.aws.amazon.com/)
- [AWS IAM Identity Center](https://aws.amazon.com/iam/identity-center/)
- [uv 安装指南（MCP 依赖）](https://docs.astral.sh/uv/getting-started/installation/)
- [MCP 协议文档](https://modelcontextprotocol.io/)
