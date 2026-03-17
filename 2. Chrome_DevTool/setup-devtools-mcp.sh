#!/bin/bash
# setup-devtools-mcp.sh — 根据环境检测结果自动配置 OpenClaw Browser + Chrome DevTools
# 供 OpenClaw Agent 调用，自动完成：
#   1. 运行环境检测（架构、显示环境、浏览器）
#   2. ARM64 Snap Chromium 的 AppArmor 沙箱问题处理
#   3. 配置 OpenClaw browser 参数（通过内置 browser profile 机制）
#
# 注意：OpenClaw 不使用 mcpServers 顶层字段，而是通过内置的 browser 配置 +
#       profile 机制（driver: "existing-session"）集成 Chrome DevTools Protocol。
#
# 用法:
#   bash setup-devtools-mcp.sh              # 自动检测并配置
#   bash setup-devtools-mcp.sh --headless   # 强制 headless 模式
#   bash setup-devtools-mcp.sh --headed     # 强制 headed 模式

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${HOME}/.openclaw/openclaw.json"
FORCE_MODE="${1:-auto}"
CDP_PORT=18800

echo "╔══════════════════════════════════════════════════════╗"
echo "║  OpenClaw Browser — 自动环境检测与配置               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# --- Step 1: 环境检测 ---

echo "▶ Step 1: 检测运行环境..."
echo ""

if [ ! -f "${SCRIPT_DIR}/detect-display-env.sh" ]; then
  echo "✘ 找不到 detect-display-env.sh，请确认脚本在同一目录下"
  exit 1
fi

ENV_JSON=$(bash "${SCRIPT_DIR}/detect-display-env.sh")

eval "$(echo "$ENV_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'ARCH={d[\"arch\"]}')
print(f'HAS_DISPLAY={str(d[\"has_display\"]).lower()}')
print(f'DISPLAY_TYPE={d[\"display_type\"]}')
print(f'CHROME_INSTALLED={str(d[\"chrome_installed\"]).lower()}')
print(f'CHROME_BINARY={d.get(\"chrome_binary\", \"\")}')
print(f'CHROME_VERSION={d[\"chrome_version\"]}')
print(f'NODE_INSTALLED={str(d[\"node_installed\"]).lower()}')
print(f'NODE_VERSION={d[\"node_version\"]}')
print(f'RECOMMENDED_MODE={d[\"recommended_mode\"]}')
")"

echo "  架构:     ${ARCH}"
echo "  显示环境: ${DISPLAY_TYPE}"
echo "  浏览器:   ${CHROME_INSTALLED} ${CHROME_BINARY:+(${CHROME_BINARY})} ${CHROME_VERSION:+v${CHROME_VERSION}}"
echo "  Node.js:  ${NODE_INSTALLED} ${NODE_VERSION:+(${NODE_VERSION})}"
echo "  推荐模式: ${RECOMMENDED_MODE}"
echo ""

# --- 确定最终模式 ---

if [ "$FORCE_MODE" = "--headless" ]; then
  MODE="headless"
  echo "  ⚙ 强制使用 headless 模式"
elif [ "$FORCE_MODE" = "--headed" ]; then
  MODE="headed"
  echo "  ⚙ 强制使用 headed 模式"
else
  MODE="$RECOMMENDED_MODE"
  echo "  ⚙ 自动选择: ${MODE} 模式"
fi
echo ""

# --- Step 2: 前置检查 ---

echo "▶ Step 2: 前置条件检查..."
echo ""

if [ "$CHROME_INSTALLED" != "true" ]; then
  echo "  ✘ 浏览器未安装，请先运行 Chrome/Chromium 安装步骤"
  echo "    参考本目录 README.md 的安装步骤"
  exit 1
else
  echo "  ✔ ${CHROME_BINARY} ${CHROME_VERSION}"
fi

echo ""

# --- Step 3: ARM64 Snap Chromium 处理 ---

IS_SNAP_CHROMIUM=false
if [ "$ARCH" = "arm64" ] && [ "$CHROME_BINARY" = "chromium-browser" ]; then
  # 检查是否为 snap 安装
  if snap list chromium &>/dev/null 2>&1; then
    IS_SNAP_CHROMIUM=true
    echo "▶ Step 3: ARM64 Snap Chromium 特殊处理..."
    echo ""
    echo "  ⚠ 检测到 Snap 版 Chromium（ARM64）"
    echo "  Snap 的 AppArmor 沙箱会阻止 OpenClaw 直接启动 Chromium。"
    echo "  解决方案: 创建 systemd 用户服务，手动运行 Chromium headless，"
    echo "  OpenClaw 通过 attachOnly 模式连接 CDP 端口。"
    echo ""

    # 创建 systemd 用户服务
    mkdir -p "${HOME}/.config/systemd/user"

    cat > "${HOME}/.config/systemd/user/chromium-headless.service" <<UNIT
[Unit]
Description=Chromium Headless for OpenClaw CDP
After=graphical-session.target

[Service]
Type=simple
ExecStart=/snap/bin/chromium --headless --no-sandbox --disable-gpu --remote-debugging-port=${CDP_PORT} --remote-debugging-address=127.0.0.1 --user-data-dir=%h/.cache/openclaw-chromium-profile --no-first-run --no-default-browser-check
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

    echo "  ✔ systemd 服务文件已创建: chromium-headless.service"

    # 启用并启动服务
    systemctl --user daemon-reload
    systemctl --user enable chromium-headless.service
    systemctl --user start chromium-headless.service 2>/dev/null || true

    # 等待 CDP 端口就绪
    echo "  等待 CDP 端口 ${CDP_PORT} 就绪..."
    for i in $(seq 1 10); do
      if curl -s --connect-timeout 1 "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
        echo "  ✔ Chromium headless 已启动，CDP 端口 ${CDP_PORT} 就绪"
        curl -s "http://127.0.0.1:${CDP_PORT}/json/version" | python3 -c "
import sys, json
info = json.load(sys.stdin)
print(f'    Browser: {info.get(\"Browser\", \"unknown\")}')
print(f'    Protocol: {info.get(\"Protocol-Version\", \"unknown\")}')
" 2>/dev/null || true
        break
      fi
      sleep 1
    done

    if ! curl -s --connect-timeout 1 "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
      echo "  ⚠ CDP 端口未就绪，请检查: systemctl --user status chromium-headless"
    fi
    echo ""
  fi
fi

if [ "$IS_SNAP_CHROMIUM" = "false" ]; then
  echo "▶ Step 3: 跳过（非 Snap Chromium）"
  echo ""
fi

# --- Step 4: 配置 OpenClaw ---

echo "▶ Step 4: 写入 OpenClaw browser 配置..."
echo ""

mkdir -p "$(dirname "$CONFIG_PATH")"

# 备份
if [ -f "$CONFIG_PATH" ]; then
  cp "$CONFIG_PATH" "${CONFIG_PATH}.bak.$(date +%Y%m%d%H%M%S)"
  echo "  ✔ 已备份现有配置"
fi

if [ "$IS_SNAP_CHROMIUM" = "true" ]; then
  # ===== ARM64 Snap Chromium: attachOnly 模式 =====
  echo "  📋 配置方案: ARM64 Snap Chromium — attachOnly + existing-session"
  echo ""
  echo "  browser.enabled    = true"
  echo "  browser.attachOnly = true"
  echo "  browser.headless   = true"
  echo "  CDP 端口: ${CDP_PORT}"
  echo ""

  python3 -c "
import json, os

config_path = os.path.expanduser('${CONFIG_PATH}')
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

if 'browser' not in config:
    config['browser'] = {}

config['browser']['enabled'] = True
config['browser']['headless'] = True
config['browser']['attachOnly'] = True
config['browser']['evaluateEnabled'] = True
config['browser']['defaultProfile'] = 'user'

# Profile: 连接到 systemd 管理的 Chromium headless 实例
config['browser']['profiles'] = {
    'user': {
        'cdpUrl': 'http://127.0.0.1:${CDP_PORT}',
        'driver': 'existing-session',
        'attachOnly': True,
        'color': '#FF4500'
    }
}

# 清理无效的 mcpServers 字段（如果之前误写入）
config.pop('mcpServers', None)

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print('  ✔ 配置已写入 (ARM64 attachOnly 模式)')
"

elif [ "$MODE" = "headless" ]; then
  # ===== 无显示器服务器环境（非 Snap）=====
  echo "  📋 配置方案: 无显示器服务器（headless）"
  echo ""
  echo "  browser.enabled   = true"
  echo "  browser.headless  = true"
  echo "  browser.noSandbox = true"
  echo ""

  python3 -c "
import json, os

config_path = os.path.expanduser('${CONFIG_PATH}')
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

if 'browser' not in config:
    config['browser'] = {}

config['browser']['enabled'] = True
config['browser']['headless'] = True
config['browser']['noSandbox'] = True
config['browser']['evaluateEnabled'] = True

# 清理无效的 mcpServers 字段（如果之前误写入）
config.pop('mcpServers', None)

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print('  ✔ 配置已写入 (headless 模式)')
"

else
  # ===== 有显示器环境（DCV / X11 / Wayland / VNC）=====
  echo "  📋 配置方案: 图形桌面环境（headed）— ${DISPLAY_TYPE}"
  echo ""
  echo "  browser.enabled   = true"
  echo "  browser.headless  = false"
  echo ""

  python3 -c "
import json, os

config_path = os.path.expanduser('${CONFIG_PATH}')
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

if 'browser' not in config:
    config['browser'] = {}

config['browser']['enabled'] = True
config['browser']['headless'] = False
config['browser']['noSandbox'] = False
config['browser']['evaluateEnabled'] = True
config['browser']['defaultProfile'] = 'openclaw'

# 双 Profile 配置
config['browser']['profiles'] = {
    'user': {
        'cdpUrl': 'http://127.0.0.1:9222',
        'driver': 'existing-session',
        'attachOnly': True,
        'color': '#00AA00'
    },
    'openclaw': {
        'color': '#FF4500'
    }
}

# 清理无效的 mcpServers 字段（如果之前误写入）
config.pop('mcpServers', None)

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print('  ✔ 配置已写入 (headed 模式，含双 Profile)')
"

fi

echo ""

# --- Step 5: 重启 Gateway ---

echo "▶ Step 5: 重启 OpenClaw Gateway..."
echo ""

if command -v openclaw &>/dev/null; then
  if openclaw gateway restart 2>/dev/null; then
    echo "  ✔ Gateway 已重启"
  else
    echo "  ⚠ Gateway 重启失败，请手动执行: openclaw gateway restart"
  fi
else
  echo "  ⚠ openclaw 命令不可用，请手动重启 Gateway"
fi

echo ""

# --- 完成 ---

echo "╔══════════════════════════════════════════════════════╗"
echo "║  配置完成                                            ║"
echo "╠══════════════════════════════════════════════════════╣"

if [ "$IS_SNAP_CHROMIUM" = "true" ]; then
  echo "║  模式: ARM64 Snap Chromium — attachOnly             ║"
  echo "║  Chromium headless 通过 systemd 服务运行             ║"
  echo "║  OpenClaw 通过 CDP 端口 ${CDP_PORT} 连接             ║"
  echo "║                                                      ║"
  echo "║  管理服务:                                           ║"
  echo "║    systemctl --user status chromium-headless         ║"
  echo "║    systemctl --user restart chromium-headless        ║"
elif [ "$MODE" = "headless" ]; then
  echo "║  模式: headless（无显示器服务器）                    ║"
  echo "║  OpenClaw 内置浏览器管理将自动启动 headless Chrome   ║"
else
  echo "║  模式: headed（${DISPLAY_TYPE} 图形桌面）            ║"
  echo "║  Chrome 将在桌面上可见运行                           ║"
  echo "║                                                      ║"
  echo "║  可选: 在 Chrome 地址栏输入                          ║"
  echo "║    chrome://inspect/#remote-debugging                ║"
  echo "║  勾选启用 Remote Debugging 以支持 user Profile       ║"
fi

echo "║                                                      ║"
echo "║  测试: 在 OpenClaw 对话中输入                        ║"
echo "║    「打开 https://www.google.com 并截图」            ║"
echo "╚══════════════════════════════════════════════════════╝"
