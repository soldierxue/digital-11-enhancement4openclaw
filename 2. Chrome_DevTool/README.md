# Google Chrome 自动安装与配置指南 — Ubuntu

> 本文档供 AI Agent（如 OpenClaw）读取并在本机自动执行，完成 Google Chrome 浏览器的检测、安装/升级、默认浏览器设置，以及 OpenClaw Browser 能力配置。
>
> 幂等性原则：所有操作执行前先检查当前状态，已安装的组件只验证不重复安装，重复执行不会产生副作用。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 第一步：通读全文，理解全貌

在执行任何命令之前，请先完整阅读本文档所有章节，理解：
- 文档分两大部分：Chrome 安装（Step 0-5）和 OpenClaw Browser 配置（Part 1-3, Step 6-14）
- Step 0 的环境检测结果决定后续所有配置路径（headless / headed / ARM64 attachOnly）
- 有一键脚本 `setup-devtools-mcp.sh` 可自动完成 Part 2 的全部配置
- 可选扩展：`web-article-saver` Skill
- 最终验收标准：Chrome/Chromium 已安装、OpenClaw `browser.enabled = true`、截图测试通过

### 第二步：检查当前环境状态

通读完成后，先执行以下诊断命令，收集当前状态：

```bash
# 1. 操作系统和架构
lsb_release -d 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME
ARCH=$(dpkg --print-architecture)
echo "架构: $ARCH"

# 2. 显示环境（如果 detect-display-env.sh 存在）
if [ -f detect-display-env.sh ]; then
  bash detect-display-env.sh
else
  echo "DETECT_SCRIPT_NOT_FOUND"
fi

# 3. Chrome / Chromium 是否已安装
for b in google-chrome-stable chromium-browser; do
  command -v "$b" >/dev/null 2>&1 && echo "INSTALLED: $b $($b --version 2>/dev/null)" || true
done

# 4. OpenClaw 是否已安装
openclaw --version 2>/dev/null || echo "OPENCLAW_NOT_FOUND"

# 5. OpenClaw browser 配置状态
python3 -c "
import json, os
try:
    cfg = json.load(open(os.path.expanduser('~/.openclaw/openclaw.json')))
    b = cfg.get('browser', {})
    print(f'browser.enabled={b.get(\"enabled\", True)}')
    print(f'browser.headless={b.get(\"headless\", False)}')
    print(f'browser.profiles={list(b.get(\"profiles\", {}).keys()) or \"none\"}')
except Exception as e:
    print(f'OPENCLAW_CONFIG_READ_FAILED: {e}')
" 2>/dev/null

# 6. Node.js 版本（Part 2 依赖）
node --version 2>/dev/null || echo "NODE_NOT_FOUND"

# 7. Gateway 状态
openclaw gateway status 2>/dev/null || echo "GATEWAY_STATUS_UNKNOWN"
```

### 第三步：根据状态制定分阶段计划

根据诊断结果，将执行拆分为以下阶段。**每个阶段完成后向用户汇报结果，再进入下一阶段：**

| 阶段 | 对应文档 | 前置条件 | 需要用户确认的情况 |
|------|----------|----------|-------------------|
| 阶段 1：环境检测 | Step 0 | 无 | 非 Ubuntu 系统时暂停；无 `sudo` 权限时暂停 |
| 阶段 2：Chrome 安装 | Step 1-5 | 阶段 1 完成 | Chrome/Chromium 已安装时跳过安装，仅验证版本；headless 模式跳过 Step 4-5 |
| 阶段 3：Browser 能力启用 | Part 1 (Step 6-9) | Chrome 已安装 + OpenClaw 已安装 | `browser.enabled` 已为 `true` 时跳过，仅验证 |
| 阶段 4：DevTools 配置 | Part 2 (Step 10-12) | 阶段 3 完成 | `setup-devtools-mcp.sh` 已执行过且 browser profiles 已配置时跳过，仅验证 |
| 阶段 5：双 Profile | Part 3 (Step 13-14) | 阶段 4 完成 + headed 模式 | headless / ARM64 attachOnly 模式跳过整个阶段；Remote Debugging 需用户手动操作 |
| 阶段 6：web-article-saver | 扩展 Skill 章节 | 阶段 4 完成 | 用户未要求时可跳过；Skill 已安装时跳过 |

### 执行原则

1. **先诊断，后执行** — 不要跳过 Step 0 环境检测直接安装 Chrome
2. **幂等性优先** — Chrome 已安装时不重复安装，browser 配置已存在时不覆盖
3. **环境检测结果决定路径** — `recommended_mode` 为 `headless` 时跳过 Step 4-5 和 Part 3
4. **优先使用一键脚本** — Part 2 优先用 `setup-devtools-mcp.sh`，它内部已包含幂等检查
5. **遇到异常立即暂停** — `sudo` 权限不足、网络不通、Gateway 重启失败等情况，停下来向用户说明
6. **每阶段汇报** — 完成一个阶段后，用简短的 ✅/❌ 汇总该阶段结果，再询问是否继续
7. **Step 13 需用户手动操作** — Remote Debugging 需要在 Chrome 地址栏手动输入 `chrome://inspect`，Agent 无法代为执行

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
  "arch": "arm64",
  "has_display": true,
  "display_type": "dcv",
  "chrome_installed": true,
  "chrome_binary": "chromium-browser",
  "chrome_version": "145.0.7632.116",
  "node_installed": true,
  "node_version": "v22.15.0",
  "recommended_mode": "headed",
  "details": "Amazon DCV 远程桌面已运行。会话: my-session console ..."
}
```

### 检测项说明

| 字段 | 含义 | 可能的值 |
|------|------|----------|
| `arch` | CPU 架构 | `amd64` / `arm64` |
| `has_display` | 是否有可用的图形显示 | `true` / `false` |
| `display_type` | 显示环境类型 | `dcv` / `x11` / `wayland` / `vnc` / `none` |
| `chrome_binary` | 实际使用的浏览器命令 | `google-chrome-stable` / `chromium-browser` / 空 |
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
    │ • 不加 --headless│             │ • headless=true  │
    │ • 双 Profile     │             │ • noSandbox=true │
    │ • 可见浏览器窗口 │             │ • 后台无头运行   │
    └─────────────────┘             └─────────────────┘
             │
             ├── ARM64 Snap Chromium?
             │   └── 是 → attachOnly 模式
             │         systemd 服务 + CDP 端口 18800
             └── 否 → 标准 headed 配置
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

> 脚本会自动运行 `detect-display-env.sh`，根据结果配置 `~/.openclaw/openclaw.json` 中的 `browser` 字段（含 profiles），并重启 Gateway。

### 三种环境的配置差异对比

| 配置项 | 无显示器服务器 (headless) | 有桌面环境 (headed) | ARM64 Snap Chromium |
|--------|--------------------------|---------------------|---------------------|
| `browser.headless` | `true` | `false` | `true` |
| `browser.noSandbox` | `true` | `false` | — |
| `browser.attachOnly` | — | — | `true` |
| CDP 连接方式 | OpenClaw 内置管理 | OpenClaw 内置管理 | systemd 服务 + 端口 18800 |
| 双 Profile 支持 | 否 | 是（user + openclaw） | 否（仅 user profile） |
| Chrome 窗口可见 | 否 | 是 | 否 |
| 适用场景 | EC2 无桌面、Docker 容器 | DCV 远程桌面、本地开发机 | AWS Graviton ARM64 实例 |

---

## 前置条件（需用户提前完成）

1. 当前系统为 Ubuntu 20.04 / 22.04 / 24.04 LTS（支持 amd64 和 arm64/Graviton）
2. 用户具有 `sudo` 权限
3. 系统已安装桌面环境（如 GNOME）— 如果是无显示器服务器，Step 0 检测后会自动使用 headless 模式
4. 网络可正常访问 `dl.google.com`（amd64）或 Ubuntu APT 源（arm64）

> **ARM64 注意**: Google Chrome 官方不提供 ARM64 `.deb` 包，ARM64 环境（如 AWS Graviton 实例）将自动安装 Chromium 替代。在 Ubuntu 24.04 上 Chromium 通过 Snap 安装，存在 AppArmor 沙箱限制，脚本会自动处理。

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

### Step 2: 安装或升级 Google Chrome / Chromium

> Google Chrome 官方仅提供 x86_64（amd64）的 `.deb` 包，**不支持 ARM64（aarch64/Graviton）**。ARM64 环境请安装 Chromium。

**首先检测 CPU 架构：**

```bash
ARCH=$(dpkg --print-architecture)
echo "当前架构: $ARCH"
```

**amd64 架构 — 安装 Google Chrome：**

```bash
# 下载最新版 Google Chrome .deb 包（仅 amd64）
wget -q -O /tmp/google-chrome-stable.deb \
  "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"

# 安装（自动处理依赖）
sudo apt-get install -y /tmp/google-chrome-stable.deb

# 清理安装包
rm -f /tmp/google-chrome-stable.deb
```

> 安装过程会自动添加 Google 官方 APT 源，后续可通过 `apt upgrade` 持续更新。

**arm64 架构 — 安装 Chromium：**

```bash
sudo apt-get update
sudo apt-get install -y chromium-browser
```

> Chromium 是 Chrome 的开源上游项目，功能基本一致，支持 ARM64。在 Ubuntu 24.04 上 `chromium-browser` 为 snap 包。

**如果已安装，升级到最新版本：**

```bash
# amd64: 升级 Chrome
sudo apt-get update
sudo apt-get install -y --only-upgrade google-chrome-stable

# arm64: 升级 Chromium
sudo apt-get update
sudo apt-get install -y --only-upgrade chromium-browser
```

### Step 3: 验证安装结果

```bash
# amd64
google-chrome-stable --version

# arm64
chromium-browser --version
```

期望输出类似：`Google Chrome 13x.x.xxxx.xx` 或 `Chromium 14x.x.xxxx.xx`。

### Step 4: 设置为默认浏览器

**amd64（Chrome）：**

```bash
sudo update-alternatives --set x-www-browser /usr/bin/google-chrome-stable
sudo update-alternatives --set gnome-www-browser /usr/bin/google-chrome-stable
xdg-settings set default-web-browser google-chrome.desktop 2>/dev/null || true
```

**arm64（Chromium）：**

```bash
sudo update-alternatives --set x-www-browser /usr/bin/chromium-browser
sudo update-alternatives --set gnome-www-browser /usr/bin/chromium-browser
xdg-settings set default-web-browser chromium-browser.desktop 2>/dev/null || true
```

### Step 5: 验证默认浏览器设置

```bash
xdg-settings get default-web-browser
```

期望输出：`google-chrome.desktop`（amd64）或 `chromium-browser.desktop`（arm64）。

## 完整一键脚本

将以上步骤整合为可直接执行的脚本：

```bash
#!/bin/bash
set -e

ARCH=$(dpkg --print-architecture)
echo "=== 当前架构: $ARCH ==="

echo ""
echo "=== 检测已安装的浏览器 ==="
for browser in google-chrome-stable chromium-browser firefox microsoft-edge-stable; do
  if command -v "$browser" &>/dev/null; then
    echo "  ✔ $browser — $($browser --version 2>/dev/null)"
  fi
done

if [ "$ARCH" = "arm64" ]; then
  # --- ARM64: 使用 Chromium ---
  if command -v chromium-browser &>/dev/null; then
    echo ""
    echo "=== Chromium 已安装，尝试升级 ==="
    sudo apt-get update -qq
    sudo apt-get install -y --only-upgrade chromium-browser
  else
    echo ""
    echo "=== ARM64 架构，安装 Chromium（Google Chrome 不支持 ARM64）==="
    sudo apt-get update -qq
    sudo apt-get install -y chromium-browser
  fi

  echo ""
  echo "=== 当前 Chromium 版本 ==="
  chromium-browser --version

  echo ""
  echo "=== 设置 Chromium 为默认浏览器 ==="
  sudo update-alternatives --set x-www-browser /usr/bin/chromium-browser 2>/dev/null || true
  sudo update-alternatives --set gnome-www-browser /usr/bin/chromium-browser 2>/dev/null || true
  xdg-settings set default-web-browser chromium-browser.desktop 2>/dev/null || true

else
  # --- amd64: 使用 Google Chrome ---
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
fi

echo ""
echo "=== 验证默认浏览器 ==="
default=$(xdg-settings get default-web-browser 2>/dev/null || echo "无法获取")
echo "  默认浏览器: $default"

echo ""
echo "✔ 浏览器安装/升级完成，已设为默认浏览器。"
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

# OpenClaw Browser 能力配置指南

> Chrome 安装完成后，继续配置 OpenClaw 的浏览器操作能力。
>
> **重要**: OpenClaw 不使用 `mcpServers` 顶层字段来集成 Chrome DevTools。OpenClaw 有自己内置的浏览器管理系统，通过 `browser` 配置 + `profiles` 机制（`driver: "existing-session"`）集成 Chrome DevTools Protocol。

## 前置条件

1. Chrome / Chromium 已按上述步骤安装完成
2. OpenClaw 已安装并可正常运行（`openclaw --version`）

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
    print(f'browser.attachOnly = {browser.get(\"attachOnly\", False)}')
    print(f'browser.evaluateEnabled = {browser.get(\"evaluateEnabled\", True)}')
    profiles = browser.get('profiles', {})
    if profiles:
        print(f'browser.profiles = {list(profiles.keys())}')
    else:
        print('browser.profiles = (未配置)')
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

## Part 2: 配置 Chrome DevTools 集成

OpenClaw 通过内置的 `browser` 配置和 `profiles` 机制集成 Chrome DevTools Protocol（CDP），无需安装独立的 MCP 服务器。

### Step 10: 确认 Node.js 环境

```bash
node --version
```

期望 Node.js 版本 ≥ v20.19。如果版本过低：

```bash
# 使用 nvm 升级（推荐）
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install --lts
nvm use --lts
```

### Step 11: 环境检测 + 自动配置 OpenClaw Browser

> 此步骤使用 `setup-devtools-mcp.sh` 脚本自动完成环境检测和 OpenClaw browser 配置。脚本会根据检测结果自动选择最佳配置方案。

**一键自动配置（推荐）：**

```bash
bash setup-devtools-mcp.sh
```

脚本自动完成以下操作：

1. 运行 `detect-display-env.sh` 检测显示环境（DCV / X11 / Wayland / VNC / 无显示器）
2. 检查 Chrome/Chromium 是否已安装
3. ARM64 Snap Chromium 特殊处理（创建 systemd 服务解决 AppArmor 沙箱问题）
4. 备份现有 `~/.openclaw/openclaw.json`
5. 根据环境写入 `browser` 配置（含 profiles）
6. 清理无效的 `mcpServers` 字段（如果之前误写入）
7. 重启 OpenClaw Gateway

如果需要强制指定模式（覆盖自动检测结果）：

```bash
# 强制 headless（无显示器服务器、Docker 容器）
bash setup-devtools-mcp.sh --headless

# 强制 headed（DCV 远程桌面、本地开发机）
bash setup-devtools-mcp.sh --headed
```

**脚本根据环境自动生成的配置方案：**

**方案 A — 无显示器服务器（headless）：**

```json
{
  "browser": {
    "enabled": true,
    "headless": true,
    "noSandbox": true,
    "evaluateEnabled": true
  }
}
```

**方案 B — 有桌面环境（headed，含双 Profile）：**

```json
{
  "browser": {
    "enabled": true,
    "headless": false,
    "noSandbox": false,
    "evaluateEnabled": true,
    "defaultProfile": "openclaw",
    "profiles": {
      "user": {
        "cdpUrl": "http://127.0.0.1:9222",
        "driver": "existing-session",
        "attachOnly": true,
        "color": "#00AA00"
      },
      "openclaw": {
        "color": "#FF4500"
      }
    }
  }
}
```

> `user` profile 需要浏览器启动时带有 `--remote-debugging-port=9222 --remote-allow-origins=*` 参数。推荐通过持久化配置注入（Snap Chromium 用 `~/.chromium-browser.init`，Chrome 用 `~/.config/chrome-flags.conf`，见 Part 3 Step 13），避免每次手动指定。

**方案 C — ARM64 Snap Chromium（attachOnly）：**

```json
{
  "browser": {
    "enabled": true,
    "headless": true,
    "attachOnly": true,
    "evaluateEnabled": true,
    "defaultProfile": "user",
    "profiles": {
      "user": {
        "cdpUrl": "http://127.0.0.1:18800",
        "driver": "existing-session",
        "attachOnly": true,
        "color": "#FF4500"
      }
    }
  }
}
```

> 方案 C 中，Snap Chromium 的 AppArmor 沙箱阻止 OpenClaw 直接启动浏览器。脚本会创建 systemd 用户服务（`chromium-headless.service`）在后台运行 Chromium headless，OpenClaw 通过 CDP 端口 18800 连接。

**仅运行环境检测（不自动配置）：**

如果只想查看检测结果，手动决定配置方式：

```bash
bash detect-display-env.sh
```

### Step 12: 验证配置结果

`setup-devtools-mcp.sh` 已自动完成 Gateway 重启。

**验证 1：确认配置文件已正确写入**

```bash
python3 -c "
import json, os
with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
    cfg = json.load(f)
browser = cfg.get('browser', {})
print(f'browser.enabled:    {browser.get(\"enabled\", \"未设置\")}')
print(f'browser.headless:   {browser.get(\"headless\", \"未设置\")}')
print(f'browser.noSandbox:  {browser.get(\"noSandbox\", \"未设置\")}')
print(f'browser.attachOnly: {browser.get(\"attachOnly\", \"未设置\")}')
profiles = browser.get('profiles', {})
if profiles:
    print(f'browser.profiles:   {list(profiles.keys())}')
    for name, p in profiles.items():
        driver = p.get('driver', 'default')
        cdp = p.get('cdpUrl', '—')
        print(f'  {name}: driver={driver}, cdpUrl={cdp}')
else:
    print('browser.profiles:   (未配置，使用默认)')
if 'mcpServers' in cfg:
    print('⚠ 发现无效的 mcpServers 字段，请运行 setup-devtools-mcp.sh 清理')
"
```

**验证 2：ARM64 Snap Chromium — 检查 systemd 服务**

```bash
# 仅 ARM64 Snap Chromium 环境需要
systemctl --user status chromium-headless
curl -s http://127.0.0.1:18800/json/version | python3 -m json.tool
```

**验证 3：通过 OpenClaw 发送测试指令**

在 OpenClaw 对话中输入以下提示词测试浏览器操作：

```
打开 https://www.google.com 并截图
```

如果配置正确，OpenClaw 应能自动打开浏览器、导航到目标页面并返回截图。

## Part 3: 双 Profile 使用说明（headed 模式）

> 仅适用于有桌面环境（headed 模式）的配置。headless 和 ARM64 Snap Chromium 环境无需此部分。

在 headed 模式下，`setup-devtools-mcp.sh` 自动配置了两个 Profile：

| Profile | 用途 | 连接方式 | 说明 |
|---------|------|----------|------|
| `user` | 连接用户正在使用的 Chrome | CDP `127.0.0.1:9222` | 需先在 Chrome 中启用 Remote Debugging |
| `openclaw` | OpenClaw 自动管理的独立实例 | OpenClaw 内置管理 | 默认 Profile，无需额外配置 |

### Step 13: 为 User Profile 启用 Remote Debugging（可选）

此步骤让 Agent 能连接到用户正在使用的 Chrome 浏览器。

> **核心要求**：Chrome/Chromium 必须同时启用 `--remote-debugging-port=9222` 和 `--remote-allow-origins=*` 两个参数。缺少后者会导致 WebSocket 握手被拒绝（端口在监听但 CDP 连接失败）。

#### 方法 A：持久化配置（推荐，重启浏览器自动生效）

将 CDP 参数写入 Chromium/Chrome 的启动配置文件，以后每次启动浏览器都会自动带上这些参数。

**Snap Chromium（Ubuntu 24.04 ARM64 等）：**

> ⚠ Snap Chromium **不读取** `chromium-flags.conf`。正确方式是通过 `~/.chromium-browser.init` 设置 `CHROMIUM_FLAGS` 环境变量——Snap launcher 启动时会 `source` 该文件。

```bash
INIT_FILE="$HOME/.chromium-browser.init"
REQUIRED_FLAGS="--remote-debugging-port=9222 --remote-allow-origins=*"

# 幂等写入：检查 CHROMIUM_FLAGS 是否已包含所需参数
if [ -f "$INIT_FILE" ] && grep -q "CHROMIUM_FLAGS" "$INIT_FILE"; then
  # 已有 CHROMIUM_FLAGS 行，检查是否缺少参数
  NEEDS_UPDATE=false
  grep -q "remote-debugging-port" "$INIT_FILE" || NEEDS_UPDATE=true
  grep -q "remote-allow-origins" "$INIT_FILE" || NEEDS_UPDATE=true
  if [ "$NEEDS_UPDATE" = "true" ]; then
    # 追加缺少的参数到现有 CHROMIUM_FLAGS 行
    sed -i '/^export CHROMIUM_FLAGS/s/"$/ '"${REQUIRED_FLAGS}"'"/' "$INIT_FILE"
    echo "✔ 已更新 $INIT_FILE 中的 CHROMIUM_FLAGS"
  else
    echo "✔ $INIT_FILE 已包含所需参数，无需修改"
  fi
else
  # 新增 CHROMIUM_FLAGS
  echo "export CHROMIUM_FLAGS=\"\$CHROMIUM_FLAGS ${REQUIRED_FLAGS}\"" >> "$INIT_FILE"
  echo "✔ 已写入 $INIT_FILE"
fi

cat "$INIT_FILE"
echo ""
echo "⚠ 需要关闭并重新打开 Chromium 浏览器才能生效"
```

**Google Chrome（amd64 .deb 安装）：**

```bash
FLAGS_FILE="$HOME/.config/chrome-flags.conf"

grep -q "remote-debugging-port" "$FLAGS_FILE" 2>/dev/null || \
  echo "--remote-debugging-port=9222" >> "$FLAGS_FILE"
grep -q "remote-allow-origins" "$FLAGS_FILE" 2>/dev/null || \
  echo "--remote-allow-origins=*" >> "$FLAGS_FILE"

echo "✔ 已写入 $FLAGS_FILE："
cat "$FLAGS_FILE"
echo ""
echo "⚠ 需要关闭并重新打开 Chrome 浏览器才能生效"
```

> 写入配置后，**必须完全关闭浏览器再重新打开**（不是刷新页面）。如果是 DCV 远程桌面环境，请提示用户在桌面上关闭浏览器窗口后重新打开。

#### 方法 B：通过 chrome://inspect 启用（临时，浏览器关闭后失效）

**在用户的 Chrome 浏览器中操作：**

1. 地址栏输入 `chrome://inspect/#remote-debugging` 并回车
2. 找到 "Allow remote debugging for this browser instance" 复选框
3. 勾选该复选框
4. 确认页面显示 `Server running at: 127.0.0.1:9222`

> 注意：`chrome://` 页面无法通过外部链接打开，必须在地址栏手动输入。此方法每次重启浏览器后需要重新启用。

#### 方法 C：命令行启动（一次性）

```bash
# Snap Chromium
chromium-browser --remote-debugging-port=9222 --remote-allow-origins=* &

# Google Chrome
google-chrome-stable --remote-debugging-port=9222 --remote-allow-origins=* &
```

> 此方法会启动一个新的浏览器实例。如果已有浏览器在运行，新实例可能无法绑定端口。

**验证 User Profile 的 Remote Debugging：**

```bash
# 验证端口监听
ss -tlnp | grep 9222

# 验证 CDP 连接（必须返回 JSON，而非连接被拒绝）
curl -s http://127.0.0.1:9222/json/version | python3 -m json.tool
```

期望输出包含 Chrome 版本信息和 `webSocketDebuggerUrl`。如果 `curl` 返回空或报错，说明 `--remote-allow-origins=*` 未生效，需要重启浏览器。

> ⚠ 安全提示：启用 Remote Debugging 后，本机上的任何应用都可以通过该端口完全控制浏览器（包括读取 Cookie、浏览数据等）。仅在开发/测试环境中使用。

### Step 14: 验证双 Profile

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

OpenClaw 会自动启动一个独立的 Chrome 实例完成操作。

## 完整配置一键脚本

Part 1（Chrome 安装）和 Part 2（Browser 配置）已整合为本目录下的脚本，支持自动环境检测：

```bash
# Step 1-5: 安装 Chrome（如果尚未安装）
sudo bash install-chrome.sh

# Step 6-12: 环境检测 + Browser 能力 + Profile 配置（一键完成）
bash setup-devtools-mcp.sh
```

`setup-devtools-mcp.sh` 内部会自动调用 `detect-display-env.sh` 检测显示环境，根据结果选择 headless / headed / ARM64 attachOnly 模式，写入 `~/.openclaw/openclaw.json` 并重启 Gateway。

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
| APT 源签名错误 | `sudo apt-key list \| grep Google` | 重新导入签名密钥 |
| `openclaw config set` 报错 | `cat ~/.openclaw/openclaw.json` | 确认 JSON 格式正确，手动修复后重试 |
| Gateway 重启失败 | `openclaw gateway status` | 检查端口占用：`ss -tlnp \| grep 18789` |
| Browser 能力未生效 | `openclaw config set browser.enabled true && openclaw gateway restart` | 确认重启后配置已加载 |
| headless 模式下截图空白 | 添加 `--disable-gpu` 参数 | 在 `openclaw.json` 的 `browser.extraArgs` 中添加 `["--disable-gpu"]` |
| Remote Debugging 未启用 | `curl -s http://127.0.0.1:9222/json/version` | 在 Chrome 中访问 `chrome://inspect/#remote-debugging` 并勾选启用，或使用持久化配置（见 Step 13） |
| CDP 端口在监听但连接被拒绝 | `ss -tlnp \| grep 9222` 显示端口在监听，但 `curl` 返回空 | 缺少 `--remote-allow-origins=*` 参数。Snap Chromium 写入 `~/.chromium-browser.init`（设置 `CHROMIUM_FLAGS`），Chrome 写入 `~/.config/chrome-flags.conf`，然后**关闭并重新打开浏览器**（见 Step 13 方法 A） |
| Snap Chromium 启动失败 | `systemctl --user status chromium-headless` | AppArmor 沙箱限制，使用 systemd 服务方式运行（setup 脚本自动处理） |
| Snap Chromium CDP 端口无响应 | `curl -s http://127.0.0.1:18800/json/version` | `systemctl --user restart chromium-headless` |
| 配置中存在 `mcpServers` | `python3 -c "..."` 检查 | 运行 `setup-devtools-mcp.sh` 自动清理，或手动删除该字段 |
| 切换 Profile 后操作无效 | `openclaw gateway restart` | 修改 `browser.defaultProfile` 后需重启 Gateway |
| 两个 Profile 端口冲突 | `ss -tlnp \| grep -E '9222\|18800'` | User Profile 用 9222，ARM64 Snap 用 18800，确保端口不重复 |

## Chrome DevTools 工具列表

配置成功后，OpenClaw 可使用以下 Chrome DevTools 工具：

| 类别 | 工具 | 说明 |
|------|------|------|
| 输入自动化 | `click`, `fill`, `hover`, `press_key`, `type_text` 等 | 模拟用户交互操作 |
| 导航自动化 | `navigate_page`, `new_page`, `close_page`, `list_pages` 等 | 页面导航与管理 |
| 模拟 | `emulate`, `resize_page` | 设备模拟与视口调整 |
| 性能 | `performance_start_trace`, `performance_stop_trace`, `performance_analyze_insight` | 性能录制与分析 |
| 网络 | `list_network_requests`, `get_network_request` | 网络请求监控 |
| 调试 | `take_screenshot`, `take_snapshot`, `evaluate_script`, `list_console_messages` 等 | 截图、DOM 快照、JS 执行、控制台日志 |

## 扩展 Skill: web-article-saver（网页文章保存）

> 本目录附带 `web-article-saver` Skill，可让 OpenClaw 抓取网页文章（含图片），保存为 Markdown 和 PDF。
>
> **双引擎架构**：优先使用 [Scrapling](https://github.com/D4Vinci/Scrapling)（轻量 HTTP 抓取，无需浏览器），对防盗链网站（如微信公众号）自动回退到 CDP 浏览器上下文模式。

### 功能特点

- 双引擎：Scrapling（HTTP 直抓）→ CDP（浏览器上下文）自动切换
- Scrapling 引擎：无需运行浏览器，支持 TLS 指纹伪装、反检测、自适应选择器
- CDP 引擎：在浏览器上下文中 fetch 图片，绕过微信公众号等防盗链限制
- 自动识别微信公众号、知乎专栏、通用网页
- 输出 Markdown（含本地图片引用）+ PDF（图片内嵌）
- 自动滚动触发懒加载图片（CDP 模式）

### 引擎选择逻辑

```
用户请求保存文章
    │
    ▼
检测目标 URL 域名
    │
    ├── mp.weixin.qq.com（防盗链）──→ CDP 引擎（需浏览器已打开该页面）
    │
    └── 其他网站 ──→ Scrapling 引擎（HTTP 直抓）
                        │
                        ├── 成功 → 输出 Markdown/PDF
                        │
                        └── 失败（反爬/JS 渲染）──→ 回退 CDP 引擎
```

| 场景 | 引擎 | 原因 |
|------|------|------|
| 微信公众号 | CDP | 图片有 Referer 防盗链，必须在浏览器上下文中 fetch |
| 知乎专栏 | Scrapling | 无防盗链，HTTP 直抓更快 |
| 通用网页 | Scrapling | 轻量高效，无需浏览器 |
| Scrapling 被反爬拦截 | CDP 回退 | 利用用户浏览器的真实会话绕过 |

### 安装步骤

**Step 1: 安装 Python 依赖**

```bash
# Scrapling（主引擎）
pip3 install --break-system-packages scrapling

# 如需 Scrapling 的浏览器自动化能力（StealthyFetcher/DynamicFetcher），还需安装浏览器依赖：
# pip3 install --break-system-packages "scrapling[fetchers]"
# scrapling install

# CDP 引擎依赖（回退用）
pip3 install --break-system-packages websocket-client
```

> Scrapling 基础安装（`pip install scrapling`）仅包含解析引擎和 `Fetcher`（HTTP 请求），体积小、无浏览器依赖。对于大多数文章抓取场景已足够。

**Step 2: 将 Skill 安装到 OpenClaw**

将 `web-article-saver` 目录复制到 OpenClaw 的 Skill 目录：

```bash
# OpenClaw Skill 目录（按实际路径调整）
SKILL_DIR="${HOME}/.openclaw/skills/web-article-saver"

# 复制 Skill 文件
mkdir -p "$SKILL_DIR"
cp -r web-article-saver/* "$SKILL_DIR/"

echo "✔ Skill 已安装到 $SKILL_DIR"
```

> Skill 目录结构：
> ```
> ~/.openclaw/skills/web-article-saver/
> ├── SKILL.md              # Skill 描述文件（OpenClaw 自动识别）
> └── scripts/
>     └── save_article.py   # 文章抓取脚本（含双引擎）
> ```

**Step 3: 验证 Scrapling 安装**

```bash
# 验证 Scrapling 可用
python3 -c "from scrapling.fetchers import Fetcher; print('✔ Scrapling OK')"

# 可选：用 CLI 快速测试抓取
scrapling extract get 'https://quotes.toscrape.com/' /tmp/test-scrapling.md
cat /tmp/test-scrapling.md | head -20
```

**Step 4: 确认浏览器 CDP 端口可用（CDP 回退引擎需要）**

仅当需要抓取防盗链网站（如微信公众号）或 Scrapling 失败回退时才需要。根据你的环境：

- ARM64 Snap Chromium（已配置 systemd 服务）：CDP 端口 `18800`
- 标准 Chrome/Chromium（headed 模式 user profile）：CDP 端口 `9222`，需确保浏览器启动时带有 `--remote-debugging-port=9222 --remote-allow-origins=*`（Snap Chromium 通过 `~/.chromium-browser.init` 注入，Chrome 通过 `~/.config/chrome-flags.conf`）

> 如果端口在监听但 `curl` 返回空或连接被拒绝，说明缺少 `--remote-allow-origins=*` 参数。参见 Part 3 Step 13 的持久化配置方法。

```bash
# 验证 CDP 端口（应返回 JSON 版本信息）
curl -s http://127.0.0.1:9222/json/version || curl -s http://127.0.0.1:18800/json/version
```

### 使用方式

安装完成后，在 OpenClaw 对话中直接说：

```
保存这篇微信公众号文章
```

```
把浏览器里打开的文章存下来，保存到 ~/Artical/Weixin
```

```
抓取 https://example.com/blog/post-1 保存为 Markdown
```

也可以手动运行脚本：

```bash
# Scrapling 引擎（默认，无需浏览器）
python3 ~/.openclaw/skills/web-article-saver/scripts/save_article.py \
  --url "https://zhuanlan.zhihu.com/p/123456789" \
  --output-dir ~/Artical \
  --format md

# 强制 CDP 引擎（需浏览器已打开目标页面）
python3 ~/.openclaw/skills/web-article-saver/scripts/save_article.py \
  --engine cdp \
  --cdp-url http://127.0.0.1:9222 \
  --tab-url "mp.weixin.qq.com" \
  --output-dir ~/Artical/Weixin \
  --format both

# Scrapling CLI 快速抓取（不经过脚本，直接输出 Markdown）
scrapling extract get 'https://example.com/article' article.md
```

### 脚本参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--engine` | `auto` | 引擎选择: `auto`（自动）、`scrapling`（强制 Scrapling）、`cdp`（强制 CDP） |
| `--url` | — | 目标文章 URL（Scrapling 引擎使用） |
| `--cdp-url` | `http://127.0.0.1:9222` | 浏览器 CDP 地址（CDP 引擎使用） |
| `--tab-url` | 自动选择 | 匹配标签页 URL 的关键词（CDP 引擎使用） |
| `--output-dir` | `~/Artical/Weixin` | 保存目录 |
| `--format` | `both` | `md`、`pdf` 或 `both` |
| `--no-images` | — | 不下载图片 |
| `--no-scroll` | — | 不滚动触发懒加载（CDP 引擎） |
| `--stealthy` | — | 使用 StealthyFetcher（需安装 `scrapling[fetchers]`） |

### Scrapling 引擎说明

[Scrapling](https://github.com/D4Vinci/Scrapling)（v0.4+）是一个自适应 Web 抓取框架，核心优势：

- **轻量 HTTP 抓取**：`Fetcher` 类通过 HTTP 直接请求页面，无需启动浏览器，速度快、资源占用低
- **TLS 指纹伪装**：可模拟 Chrome/Firefox 的 TLS 指纹，降低被反爬检测的概率
- **自适应选择器**：网站结构变化后，能通过相似度算法自动重新定位元素
- **CSS/XPath 选择器**：与 BeautifulSoup/Scrapy 类似的 API，上手成本低
- **CLI 工具**：`scrapling extract get URL output.md` 一行命令直接输出 Markdown

```python
# Scrapling 基本用法示例
from scrapling.fetchers import Fetcher

page = Fetcher.get('https://example.com/article', stealthy_headers=True)
title = page.css('h1::text').get()
content = page.css('article').get()       # HTML 内容
paragraphs = page.css('p::text').getall() # 所有段落文本
images = page.css('img::attr(src)').getall()
```

## 参考链接

- [Google Chrome 官方下载](https://www.google.com/chrome/)
- [Chrome for Linux 安装说明](https://support.google.com/chrome/answer/95346)
- [Ubuntu update-alternatives 文档](https://manpages.ubuntu.com/manpages/noble/man1/update-alternatives.1.html)
- [Chrome DevTools MCP GitHub](https://github.com/nicolo-ribaudo/chrome-devtools-mcp)
- [Chrome Remote Debugging 文档](https://developer.chrome.com/docs/devtools/remote-debugging/)
- [Scrapling — 自适应 Web 抓取框架](https://github.com/D4Vinci/Scrapling)
- [Scrapling 文档](https://scrapling.readthedocs.io/)
- [OpenClaw 文档](https://docs.openclaw.ai)
