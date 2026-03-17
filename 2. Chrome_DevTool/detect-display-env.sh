#!/bin/bash
# detect-display-env.sh — 检测当前系统的显示环境
# 供 OpenClaw Agent 调用，根据结果自动决定 Chrome DevTools MCP 的配置方式
#
# 输出 JSON 格式结果，包含：
#   has_display    : 是否有可用的图形显示
#   display_type   : "dcv" | "x11" | "wayland" | "vnc" | "none"
#   chrome_installed: Chrome 是否已安装
#   chrome_version : Chrome 版本号（未安装则为空）
#   node_installed : Node.js 是否已安装
#   node_version   : Node.js 版本号
#   recommended_mode: "headed" | "headless"
#   details        : 人类可读的诊断摘要

set -euo pipefail

# --- 检测函数 ---

detect_dcv() {
  # 检查 DCV Server 服务是否运行
  if systemctl is-active --quiet dcvserver 2>/dev/null; then
    return 0
  fi
  # 备选：检查 dcv 命令和会话
  if command -v dcv &>/dev/null && dcv list-sessions 2>/dev/null | grep -q "console"; then
    return 0
  fi
  return 1
}

detect_x11() {
  # DISPLAY 环境变量存在且 X server 可达
  if [ -n "${DISPLAY:-}" ]; then
    if command -v xdpyinfo &>/dev/null && xdpyinfo &>/dev/null 2>&1; then
      return 0
    fi
    # DISPLAY 设了但 X server 不可达，仍算有 X（可能是 SSH forwarding）
    if [ -S "/tmp/.X11-unix/X${DISPLAY##*:}" ] 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

detect_wayland() {
  if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/${WAYLAND_DISPLAY}" ] 2>/dev/null; then
    return 0
  fi
  return 1
}

detect_vnc() {
  if pgrep -x "Xvnc|x11vnc|tigervnc" &>/dev/null 2>&1; then
    return 0
  fi
  if ss -tlnp 2>/dev/null | grep -qE ':590[0-9]'; then
    return 0
  fi
  return 1
}

detect_desktop_env() {
  # 检查是否有桌面环境进程
  if pgrep -x "gnome-shell|plasmashell|xfce4-session|mate-session|cinnamon" &>/dev/null 2>&1; then
    return 0
  fi
  if [ -n "${XDG_CURRENT_DESKTOP:-}" ]; then
    return 0
  fi
  return 1
}

# --- 主检测逻辑 ---

HAS_DISPLAY=false
DISPLAY_TYPE="none"
DETAILS=""

if detect_dcv; then
  HAS_DISPLAY=true
  DISPLAY_TYPE="dcv"
  DCV_SESSIONS=$(dcv list-sessions 2>/dev/null | tail -n +2 || echo "unknown")
  DETAILS="Amazon DCV 远程桌面已运行。会话: ${DCV_SESSIONS}"
elif detect_wayland; then
  HAS_DISPLAY=true
  DISPLAY_TYPE="wayland"
  DETAILS="Wayland 显示服务器可用 (${WAYLAND_DISPLAY:-unknown})"
elif detect_x11; then
  HAS_DISPLAY=true
  DISPLAY_TYPE="x11"
  DETAILS="X11 显示服务器可用 (DISPLAY=${DISPLAY:-unset})"
elif detect_vnc; then
  HAS_DISPLAY=true
  DISPLAY_TYPE="vnc"
  DETAILS="VNC 远程桌面已运行"
elif detect_desktop_env; then
  HAS_DISPLAY=true
  DISPLAY_TYPE="x11"
  DETAILS="检测到桌面环境进程，但显示服务器连接未确认"
else
  HAS_DISPLAY=false
  DISPLAY_TYPE="none"
  DETAILS="无图形显示环境（纯 CLI 服务器）"
fi

# --- Chrome 检测 ---

CHROME_INSTALLED=false
CHROME_VERSION=""
CHROME_BINARY=""
if command -v google-chrome-stable &>/dev/null; then
  CHROME_INSTALLED=true
  CHROME_BINARY="google-chrome-stable"
  CHROME_VERSION=$(google-chrome-stable --version 2>/dev/null | sed 's/Google Chrome //' | tr -d '[:space:]')
elif command -v google-chrome &>/dev/null; then
  CHROME_INSTALLED=true
  CHROME_BINARY="google-chrome"
  CHROME_VERSION=$(google-chrome --version 2>/dev/null | sed 's/Google Chrome //' | tr -d '[:space:]')
elif command -v chromium-browser &>/dev/null; then
  CHROME_INSTALLED=true
  CHROME_BINARY="chromium-browser"
  CHROME_VERSION=$(chromium-browser --version 2>/dev/null | sed 's/Chromium //' | tr -d '[:space:]')
fi

# --- 架构检测 ---

ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
# 统一命名: amd64 / arm64
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64) ARCH="arm64" ;;
esac

# --- Node.js 检测 ---

NODE_INSTALLED=false
NODE_VERSION=""
if command -v node &>/dev/null; then
  NODE_INSTALLED=true
  NODE_VERSION=$(node --version 2>/dev/null | tr -d '[:space:]')
fi

# --- 推荐模式 ---

if [ "$HAS_DISPLAY" = true ]; then
  RECOMMENDED_MODE="headed"
else
  RECOMMENDED_MODE="headless"
fi

# --- 输出 JSON ---

cat <<EOF
{
  "arch": "$ARCH",
  "has_display": $HAS_DISPLAY,
  "display_type": "$DISPLAY_TYPE",
  "chrome_installed": $CHROME_INSTALLED,
  "chrome_binary": "$CHROME_BINARY",
  "chrome_version": "$CHROME_VERSION",
  "node_installed": $NODE_INSTALLED,
  "node_version": "$NODE_VERSION",
  "recommended_mode": "$RECOMMENDED_MODE",
  "details": "$DETAILS"
}
EOF
