# Google Chrome 自动安装与配置指南 — Ubuntu

> 本文档供 AI Agent（如 OpenClaw）读取并在本机自动执行，完成 Google Chrome 浏览器的检测、安装/升级及默认浏览器设置。

---

## Step 0: 环境自动检测（Agent 首先执行）

> **重要**: Agent 在执行任何安装或配置操作之前，必须先运行环境检测脚本，判断当前系统是「无显示器的服务器环境」还是「有 DCV / 远程桌面的图形环境」，然后根据结果选择对应的配置路径。

### 运行环境检测

```bash
bash detect-display-env.sh
```

脚本输出 JSON 格式的检测结果，示例：

```json
{
  "has_display": true,
  "display_type": "dcv",
  "chrome_installed": true,
  "chrome_version": "136.0.7103.92",
  "node_installed": true,
  "node_version": "v22.15.0",
  "recommended_mode": "headed",
  "details": "Amazon DCV 远程桌面已运行。会话: my-session console ..."
}
```

### 检测项说明

| 字段 | 含义 | 可能的值 |
|------|------|----------|
| `has_display` | 是否有可用的图形显示 | `true` / `false` |
| `display_type` | 显示环境类型 | `dcv` / `x11` / `wayland` / `vnc` / `none` |
| `recommended_mode` | 推荐的 Chrome 运行模式 | `headed`（有桌面）/ `headless`（无桌面） |

### 根据检测结果选择配置路径

```
                    ┌─────────────────────┐
                    │  运行 detect-display │
                    │     -env.sh         │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  has_display = ?     │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │ true                          │ false
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ 图形桌面环境     │             │ 无显示器服务器    │
    │ (DCV/X11/VNC)   │             │ (纯 CLI)         │
    └────────┬────────┘             └────────┬────────┘
             │                               │
             ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ headed 模式      │             │ headless 模式    │
    │ • 不加 --headless│             │ • 加 --headless  │
    │ • 双 Profile     │             │ • noSandbox=true │
    │ • 可见浏览器窗口 │             │ • 后台无头运行   │
    └─────────────────┘             └─────────────────┘
```

### 一键自动配置（推荐）

检测 + 配置一步完成：

```bash
bash setup-devtools-mcp.sh
```

也可以强制指定模式：

```bash
bash setup-devtools-mcp.sh --headless   # 强制无头模式
bash setup-devtools-mcp.sh --headed     # 强制桌面模式
```

> 脚本会自动运行 `detect-display-env.sh`，根据结果配置 `~/.openclaw/openclaw.json` 中的 `browser` 和 `mcpServers` 字段，并重启 Gateway。

### 两种环境的配置差异对比

| 配置项 | 无显示器服务器 (headless) | 有桌面环境 (headed) |
|--------|--------------------------|---------------------|
| `browser.headless` | `true` | `false` |
| `browser.noSandbox` | `true` | `false` |
| MCP `--headless` 参数 | 有 | 无 |
| 双 Profile 支持 | 否（仅 MCP 自管理实例） | 是（chrome + openclaw） |
| Chrome 窗口可见 | 否 | 是 |
| 适用场景 | EC2 无桌面、Docker 容器 | DCV 远程桌面、本地开发机 |

---

## 前置条件（需用户提前完成）

1. 当前系统为 Ubuntu 20.04 / 22.04 / 24.04 LTS
2. 用户具有 `sudo` 权限
3. 系统已安装桌面环境（如 GNOME）— 如果是无显示器服务器，Step 0 检测后会自动使用 headless 模式
4. 网络可正常访问 `dl.google.com`

## 执行流程

Agent 按以下步骤依次执行，全程自动化，无需用户干预。

> **Agent 必须先执行 Step 0 的环境检测**，确认 `recommended_mode` 后再继续以下步骤。如果检测结果为 `headless`，Step 4（设置默认浏览器）和 Step 5（验证默认浏览器）可跳过。

### Step 1: 检测当前已安装的浏览器

列出系统中已安装的主流浏览器：

```bash
echo "=== 已安装的浏览器 ==="
for browser in google-chrome-stable chromium-browser firefox microsoft-edge-stable; do
  if command -v "$browser" &>/dev/null; then
    version=$("$browser" --version 2>/dev/null || echo "版本未知")
    echo "  ✔ $browser — $version"
  fi
done
```

### Step 2: 安装或升级 Google Chrome

**如果未安装 Chrome：**

```bash
# 下载最新版 Google Chrome .deb 包
wget -q -O /tmp/google-chrome-stable.deb \
  "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"

# 安装（自动处理依赖）
sudo apt-get install -y /tmp/google-chrome-stable.deb

# 清理安装包
rm -f /tmp/google-chrome-stable.deb
```

> 安装过程会自动添加 Google 官方 APT 源，后续可通过 `apt upgrade` 持续更新。

**如果已安装 Chrome：**

```bash
# 刷新软件源（含 Google Chrome 源）
sudo apt-get update

# 升级 Chrome 到最新版本
sudo apt-get install -y --only-upgrade google-chrome-stable
```

### Step 3: 验证安装结果

```bash
google-chrome-stable --version
```

期望输出类似：`Google Chrome 13x.x.xxxx.xx`。如果命令不存在，说明安装失败，检查 Step 2 的输出日志。

### Step 4: 设置 Chrome 为默认浏览器

**方法一：通过 `update-alternatives` 设置（推荐）：**

```bash
sudo update-alternatives --set x-www-browser /usr/bin/google-chrome-stable
sudo update-alternatives --set gnome-www-browser /usr/bin/google-chrome-stable
```

**方法二：通过 `xdg-settings` 设置（GNOME 桌面）：**

```bash
xdg-settings set default-web-browser google-chrome.desktop
```

### Step 5: 验证默认浏览器设置

```bash
xdg-settings get default-web-browser
```

期望输出：`google-chrome.desktop`。如果输出不同，手动确认 `.desktop` 文件是否存在：

```bash
ls /usr/share/applications/google-chrome.desktop
```

## 完整一键脚本

将以上步骤整合为可直接执行的脚本：

```bash
#!/bin/bash
set -e

echo "=== 检测已安装的浏览器 ==="
for browser in google-chrome-stable chromium-browser firefox microsoft-edge-stable; do
  if command -v "$browser" &>/dev/null; then
    echo "  ✔ $browser — $($browser --version 2>/dev/null)"
  fi
done

if command -v google-chrome-stable &>/dev/null; then
  echo ""
  echo "=== Chrome 已安装，尝试升级 ==="
  sudo apt-get update -qq
  sudo apt-get install -y --only-upgrade google-chrome-stable
else
  echo ""
  echo "=== Chrome 未安装，开始安装 ==="
  wget -q -O /tmp/google-chrome-stable.deb \
    "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
  sudo apt-get install -y /tmp/google-chrome-stable.deb
  rm -f /tmp/google-chrome-stable.deb
fi

echo ""
echo "=== 当前 Chrome 版本 ==="
google-chrome-stable --version

echo ""
echo "=== 设置 Chrome 为默认浏览器 ==="
sudo update-alternatives --set x-www-browser /usr/bin/google-chrome-stable 2>/dev/null || true
sudo update-alternatives --set gnome-www-browser /usr/bin/google-chrome-stable 2>/dev/null || true
xdg-settings set default-web-browser google-chrome.desktop 2>/dev/null || true

echo ""
echo "=== 验证默认浏览器 ==="
default=$(xdg-settings get default-web-browser 2>/dev/null || echo "无法获取")
echo "  默认浏览器: $default"

echo ""
echo "✔ Chrome 安装/升级完成，已设为默认浏览器。"
```

Agent 可将此脚本保存为 `install-chrome.sh` 并执行：

```bash
sudo bash install-chrome.sh
```

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| `wget` 下载失败 | `curl -I https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb` | 检查网络连接或 DNS 配置 |
| 依赖缺失导致安装失败 | `sudo apt-get -f install` | 修复依赖后重新安装 |
| `update-alternatives` 报错 | `update-alternatives --list x-www-browser` | 确认 Chrome 已注册为候选项 |
| `xdg-settings` 无效 | `echo $XDG_CURRENT_DESKTOP` | 确认桌面环境已启动（非纯 CLI 模式） |
| Chrome 启动崩溃 | `google-chrome-stable --no-sandbox --disable-gpu` | 排查 GPU 驱动或沙箱权限问题 |
| APT 源签名错误 | `sudo apt-key list \| grep Google` | `wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \| sudo apt-key add -` |

---

# OpenClaw Browser 能力配置与 Chrome DevTools MCP 插件安装

> Chrome 安装完成后，继续配置 OpenClaw 的浏览器操作能力，并安装 Chrome DevTools MCP 插件。

## 前置条件

1. Chrome 已按上述步骤安装完成
2. OpenClaw 已安装并可正常运行（`openclaw --version`）
3. Node.js v20.19 或更高版本（`node --version`）
4. npm 已安装（`npm --version`）

## Part 1: 启用 OpenClaw Browser 操作能力

OpenClaw 的浏览器操作能力默认是启用的（`browser.enabled = true`）。Agent 需要先检查当前配置状态，如果未启用则手动开启。

### Step 6: 检查 Browser 能力是否启用

查看当前 OpenClaw 配置文件中的 browser 设置：

```bash
cat ~/.openclaw/openclaw.json | python3 -c "
import sys, json
try:
    cfg = json.load(sys.stdin)
    browser = cfg.get('browser', {})
    enabled = browser.get('enabled', True)  # 默认值为 True
    print(f'browser.enabled = {enabled}')
    print(f'browser.headless = {browser.get(\"headless\", False)}')
    print(f'browser.noSandbox = {browser.get(\"noSandbox\", False)}')
    print(f'browser.evaluateEnabled = {browser.get(\"evaluateEnabled\", True)}')
except Exception as e:
    print(f'配置文件读取失败: {e}')
    print('可能尚未创建配置文件，browser 将使用默认值（enabled=true）')
"
```

### Step 7: 如果 Browser 未启用，执行启用

**如果 `browser.enabled = False`，需要启用：**

```bash
openclaw config set browser.enabled true
```

对于 Linux 服务器环境（无显示器），建议同时配置 headless 和 noSandbox 模式：

```bash
openclaw config set browser.headless true
openclaw config set browser.noSandbox true
```

> 如果通过 DCV 远程桌面访问，有图形界面可用，可以不设置 headless。

### Step 8: 重启 Gateway 服务使配置生效

修改 browser 配置后需要重启 gateway 服务：

```bash
openclaw gateway restart
```

验证 gateway 服务状态：

```bash
openclaw gateway status
```

期望输出包含 `running` 状态。如果 gateway 未以后台服务方式运行（前台模式），需要先停止当前进程（`Ctrl+C`），然后重新启动：

```bash
openclaw gateway --port 18789
```

> OpenClaw gateway 支持配置热重载（`gateway.reload.mode: "hybrid"`，默认值）。部分 browser 配置变更可以热生效，但 `browser.enabled` 的变更需要完整重启。

### Step 9: 验证 Browser 能力已生效

```bash
openclaw gateway status
```

确认输出中包含 browser 相关信息。也可以通过 API 检查：

```bash
curl -s http://127.0.0.1:18789/healthz | python3 -m json.tool
```

## Part 2: 安装 Chrome DevTools MCP 插件

[chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) 是 Google 官方提供的 MCP 服务器，让 AI Agent 能够通过 Chrome DevTools Protocol 控制和检查浏览器，支持自动化操作、调试和性能分析。

### Step 10: 确认 Node.js 环境

```bash
node --version
npm --version
```

期望 Node.js 版本 ≥ v20.19。如果版本过低：

```bash
# 使用 nvm 升级（推荐）
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install --lts
nvm use --lts
```

### Step 11: 环境检测 + 配置 Chrome DevTools MCP 服务器

> 此步骤使用 `setup-devtools-mcp.sh` 脚本自动完成环境检测和 MCP 配置，无需手动判断是否加 `--headless` 参数。

**方法一：一键自动配置（推荐）**

脚本会先运行 `detect-display-env.sh` 检测当前系统的显示环境，然后根据结果自动选择 headed 或 headless 模式写入配置：

```bash
bash setup-devtools-mcp.sh
```

脚本自动完成以下操作：

1. 检测显示环境（DCV / X11 / Wayland / VNC / 无显示器）
2. 检查 Chrome 和 Node.js 是否已安装
3. 备份现有 `~/.openclaw/openclaw.json`
4. 根据环境写入 `browser` 和 `mcpServers` 配置
5. 预下载 `chrome-devtools-mcp`
6. 重启 OpenClaw Gateway

如果需要强制指定模式（覆盖自动检测结果）：

```bash
# 强制 headless（无显示器服务器、Docker 容器）
bash setup-devtools-mcp.sh --headless

# 强制 headed（DCV 远程桌面、本地开发机）
bash setup-devtools-mcp.sh --headed
```

> 两种模式的配置差异：
>
> | 配置项 | headless（无显示器） | headed（有桌面） |
> |--------|---------------------|-----------------|
> | `browser.headless` | `true` | `false` |
> | `browser.noSandbox` | `true` | `false` |
> | MCP args | `["--headless"]` | `[]`（无额外参数） |
> | 双 Profile | 否 | 是（chrome + openclaw） |

**方法二：仅运行环境检测（不自动配置）**

如果只想查看检测结果，手动决定配置方式：

```bash
bash detect-display-env.sh
```

输出示例：

```json
{
  "has_display": true,
  "display_type": "dcv",
  "chrome_installed": true,
  "chrome_version": "136.0.7103.92",
  "node_installed": true,
  "node_version": "v22.15.0",
  "recommended_mode": "headed",
  "details": "Amazon DCV 远程桌面已运行。会话: my-session console ..."
}
```

然后根据 `recommended_mode` 手动编辑 `~/.openclaw/openclaw.json`：

- `recommended_mode = "headless"` → MCP args 加 `"--headless"`，browser 设 `headless: true, noSandbox: true`
- `recommended_mode = "headed"` → MCP args 不加 `"--headless"`，browser 设 `headless: false`

### Step 12: 验证配置结果

`setup-devtools-mcp.sh` 已自动完成 Gateway 重启。如果使用方法二或方法三手动配置，需要手动重启：

```bash
openclaw gateway restart
```

**验证 1：确认配置文件已正确写入**

```bash
python3 -c "
import json, os
with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
    cfg = json.load(f)
mcp = cfg.get('mcpServers', {}).get('chrome-devtools', {})
browser = cfg.get('browser', {})
print(f'MCP args:          {mcp.get(\"args\", [])}')
print(f'browser.headless:  {browser.get(\"headless\", \"未设置\")}')
print(f'browser.noSandbox: {browser.get(\"noSandbox\", \"未设置\")}')
print(f'browser.enabled:   {browser.get(\"enabled\", \"未设置\")}')
"
```

**验证 2：测试 MCP 服务器可启动**

```bash
# 启动 MCP 服务器（后台运行 5 秒后自动退出）
timeout 5 npx -y chrome-devtools-mcp@latest --headless 2>&1 || true
echo "✔ MCP 服务器可正常启动"
```

**验证 3：通过 OpenClaw 发送测试指令**

在 OpenClaw 对话中输入以下提示词测试浏览器操作：

```
打开 https://www.google.com 并截图
```

如果 MCP 插件工作正常，OpenClaw 应能自动打开 Chrome、导航到目标页面并返回截图。

## Part 3: 在 Chrome 中启用 DevTools Remote Debugging（多 Profile 支持）

chrome-devtools-mcp 通过 Chrome DevTools Protocol (CDP) 与浏览器通信。实际使用中通常存在两个独立的 Chrome Profile：

| Profile | 用途 | 启动方式 | User Data Dir |
|---------|------|----------|---------------|
| User Profile | 用户日常浏览，Agent 可观察/操作用户正在看的页面 | 用户手动打开 Chrome | `~/.config/google-chrome/` (系统默认) |
| OpenClaw Profile | Agent 专用的独立浏览器实例，互不干扰 | MCP 自动启动 | `~/.cache/chrome-devtools-mcp/chrome-profile-stable` |

> 两个 Profile 使用不同的 User Data Dir，Cookie、登录状态、书签等完全隔离，互不影响。

### Step 13: 为 User Profile 启用 Remote Debugging

此步骤让 Agent 能连接到用户正在使用的 Chrome 浏览器。

**在用户的 Chrome 浏览器中操作：**

1. 地址栏输入 `chrome://inspect/#remote-debugging` 并回车
2. 找到 "Allow remote debugging for this browser instance" 复选框
3. 勾选该复选框
4. 确认页面显示 `Server running at: 127.0.0.1:9222`

> 注意：`chrome://` 页面无法通过外部链接打开，必须在地址栏手动输入。

**验证 User Profile 的 Remote Debugging：**

```bash
curl -s http://127.0.0.1:9222/json/version | python3 -m json.tool
```

期望输出包含 Chrome 版本信息和 `webSocketDebuggerUrl`。

> ⚠ 安全提示：启用 Remote Debugging 后，本机上的任何应用都可以通过该端口完全控制浏览器（包括读取 Cookie、浏览数据等）。仅在开发/测试环境中使用。

### Step 14: 为 OpenClaw Profile 启用 Remote Debugging

OpenClaw Profile 是 chrome-devtools-mcp 自动管理的独立 Chrome 实例。有两种方式启用：

**方式一：MCP 自动管理（推荐）**

chrome-devtools-mcp 默认会自动启动一个独立的 Chrome 实例，使用专用的 User Data Dir（`~/.cache/chrome-devtools-mcp/chrome-profile-stable`），无需手动启用 Remote Debugging。MCP 启动时会自动配置 CDP 端口。

此方式无需额外操作，MCP 配置中不加 `--autoConnect` 或 `--browser-url` 即可：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

**方式二：手动启动独立 Chrome 实例**

如果需要更精细的控制（如指定端口、使用自定义 Profile 目录），可以手动启动：

```bash
# 为 OpenClaw 启动独立 Chrome 实例（使用不同端口和 User Data Dir）
google-chrome-stable \
  --remote-debugging-port=9223 \
  --user-data-dir="$HOME/.cache/openclaw-chrome-profile" \
  --no-first-run \
  --no-default-browser-check &
```

然后在该 Chrome 窗口中同样访问 `chrome://inspect/#remote-debugging` 并启用。

验证：

```bash
curl -s http://127.0.0.1:9223/json/version | python3 -m json.tool
```

### Step 15: 验证双 Profile 与 MCP 配置

> Step 11 的 `setup-devtools-mcp.sh` 在 headed 模式下已自动完成双 Profile 配置（chrome + openclaw）和 MCP 服务器配置，并重启了 Gateway。此步骤仅用于验证。

**验证 User Profile 连接（需先完成 Step 13）：**

在 OpenClaw 对话中测试：

```
使用用户浏览器打开 https://www.google.com 并截图
```

首次连接时 Chrome 会弹出权限确认对话框，点击 "Allow" 即可。

**验证 OpenClaw Profile（独立实例）：**

```
打开 https://www.google.com 并截图
```

MCP 会自动启动一个独立的 Chrome 实例完成操作。

### MCP 模式参考（高级）

`setup-devtools-mcp.sh` 默认配置独立实例模式。如需其他模式，可手动编辑 `~/.openclaw/openclaw.json` 中的 `mcpServers.chrome-devtools.args`：

| 模式 | args 参数 | 适用场景 | 是否需要手动启用 Remote Debugging |
|------|----------|----------|----------------------------------|
| 独立实例 | `["-y", "chrome-devtools-mcp@latest"]` | Agent 独立工作，不影响用户浏览 | 否（MCP 自动管理） |
| autoConnect | 追加 `"--autoConnect"` | Agent 操作用户当前页面（Chrome ≥ 144） | 是（Step 13） |
| browser-url | 追加 `"--browser-url=http://127.0.0.1:9222"` | 手动指定连接地址 | 是（Step 13 或命令行启动） |
| headless | 追加 `"--headless"` | 纯服务器环境，无图形界面 | 否 |

同时注册两个 MCP 服务器（同时支持独立实例和连接用户浏览器）：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    },
    "chrome-devtools-user": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--autoConnect"]
    }
  }
}
```

## 完整配置一键脚本

Part 1（Chrome 安装）和 Part 2（MCP 配置）已整合为本目录下的脚本，支持自动环境检测：

```bash
# Step 1-5: 安装 Chrome（如果尚未安装）
sudo bash install-chrome.sh

# Step 6-12: 环境检测 + Browser 能力 + MCP 配置（一键完成）
bash setup-devtools-mcp.sh
```

`setup-devtools-mcp.sh` 内部会自动调用 `detect-display-env.sh` 检测显示环境，根据结果选择 headless 或 headed 模式，写入 `~/.openclaw/openclaw.json` 并重启 Gateway。

如需单独查看环境检测结果：

```bash
bash detect-display-env.sh
```

如需强制指定模式：

```bash
bash setup-devtools-mcp.sh --headless   # 无显示器服务器
bash setup-devtools-mcp.sh --headed     # DCV / 远程桌面 / 本地开发机
```

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| `wget` 下载失败 | `curl -I https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb` | 检查网络连接或 DNS 配置 |
| 依赖缺失导致安装失败 | `sudo apt-get -f install` | 修复依赖后重新安装 |
| `update-alternatives` 报错 | `update-alternatives --list x-www-browser` | 确认 Chrome 已注册为候选项 |
| `xdg-settings` 无效 | `echo $XDG_CURRENT_DESKTOP` | 确认桌面环境已启动（非纯 CLI 模式） |
| Chrome 启动崩溃 | `google-chrome-stable --no-sandbox --disable-gpu` | 排查 GPU 驱动或沙箱权限问题 |
| APT 源签名错误 | `sudo apt-key list \| grep Google` | `wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \| sudo apt-key add -` |
| `openclaw config set` 报错 | `cat ~/.openclaw/openclaw.json` | 确认 JSON 格式正确，手动修复后重试 |
| Gateway 重启失败 | `openclaw gateway status` | 检查端口占用：`ss -tlnp \| grep 18789` |
| MCP 服务器启动失败 | `npx -y chrome-devtools-mcp@latest --help` | 确认 Node.js ≥ v20.19，检查网络是否可访问 npm registry |
| MCP 连接 Chrome 失败 | `google-chrome-stable --headless --remote-debugging-port=9222 &` 然后 `curl http://127.0.0.1:9222/json/version` | 确认 Chrome 可正常启动，CDP 端口可访问 |
| Browser 能力未生效 | `openclaw config set browser.enabled true && openclaw gateway restart` | 确认重启后配置已加载 |
| headless 模式下截图空白 | 添加 `--disable-gpu` 参数 | 在 `openclaw.json` 的 `browser.extraArgs` 中添加 `["--disable-gpu"]` |
| Remote Debugging 未启用 | `curl -s http://127.0.0.1:9222/json/version` | 在 Chrome 中访问 `chrome://inspect/#remote-debugging` 并勾选启用 |
| 9222 端口无响应 | `ss -tlnp \| grep 9222` | 确认 Chrome 正在运行且已启用 Remote Debugging |
| autoConnect 模式连接失败 | 确认 Chrome 版本 ≥ 144 | `google-chrome-stable --version`；低版本请改用 `--browser-url=http://127.0.0.1:9222` 模式 |
| Chrome 弹出权限对话框 | 首次 autoConnect 连接时正常 | 点击 "Allow" 允许 MCP 连接 |
| 两个 Profile 端口冲突 | `ss -tlnp \| grep -E '9222\|9223'` | User Profile 用 9222，OpenClaw Profile 用 9223 或由 MCP 自动分配，确保端口不重复 |
| OpenClaw Profile 数据残留 | `ls ~/.cache/chrome-devtools-mcp/` | 删除 `chrome-profile-stable` 目录可重置 OpenClaw 的 Chrome Profile |
| 切换 Profile 后操作无效 | `openclaw gateway restart` | 修改 `browser.defaultProfile` 后需重启 Gateway |

## Chrome DevTools MCP 工具列表

安装成功后，OpenClaw 可使用以下 Chrome DevTools 工具：

| 类别 | 工具 | 说明 |
|------|------|------|
| 输入自动化 | `click`, `fill`, `hover`, `press_key`, `type_text` 等 | 模拟用户交互操作 |
| 导航自动化 | `navigate_page`, `new_page`, `close_page`, `list_pages` 等 | 页面导航与管理 |
| 模拟 | `emulate`, `resize_page` | 设备模拟与视口调整 |
| 性能 | `performance_start_trace`, `performance_stop_trace`, `performance_analyze_insight` | 性能录制与分析 |
| 网络 | `list_network_requests`, `get_network_request` | 网络请求监控 |
| 调试 | `take_screenshot`, `take_snapshot`, `evaluate_script`, `list_console_messages` 等 | 截图、DOM 快照、JS 执行、控制台日志 |

## 参考链接

- [Google Chrome 官方下载](https://www.google.com/chrome/)
- [Chrome for Linux 安装说明](https://support.google.com/chrome/answer/95346)
- [Ubuntu update-alternatives 文档](https://manpages.ubuntu.com/manpages/noble/man1/update-alternatives.1.html)
- [XDG MIME 默认应用设置](https://wiki.archlinux.org/title/XDG_MIME_Applications)
- [Chrome DevTools MCP GitHub](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [Chrome DevTools MCP 工具参考](https://github.com/nicolo-ribaudo/chrome-devtools-mcp/blob/main/docs/tool-reference.md)
- [Chrome DevTools MCP 故障排查](https://github.com/nicolo-ribaudo/chrome-devtools-mcp/blob/main/docs/troubleshooting.md)
- [Chrome Remote Debugging 文档](https://developer.chrome.com/docs/devtools/remote-debugging/)
- [OpenClaw 文档](https://docs.openclaw.ai)
