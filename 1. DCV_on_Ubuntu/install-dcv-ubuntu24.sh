#!/bin/bash
#
# Amazon DCV Server 自动安装脚本 — Ubuntu 24.04
#
# 用法:
#   sudo bash install-dcv-ubuntu24.sh [选项]
#
# 选项:
#   --arch <x86_64|aarch64>   CPU 架构（默认自动检测）
#   --user <username>         DCV 会话所有者（默认: ubuntu）
#   --password <password>     为用户设置密码（交互式输入如未指定）
#   --session <name>          DCV 会话名称（默认: my-session）
#   --no-reboot               安装完成后不自动重启
#   --gpu                     启用 GPU 相关组件（nice-dcv-gl）
#   --help                    显示帮助信息
#
# 参考: https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-server.html
#

set -euo pipefail

# ============================================================
# 默认参数
# ============================================================
ARCH=""
DCV_USER="ubuntu"
DCV_PASSWORD=""
SESSION_NAME="my-session"
NO_REBOOT=false
GPU_MODE=false

# ============================================================
# 颜色输出
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}==>${NC} $*"; }

# ============================================================
# 帮助信息
# ============================================================
show_help() {
    head -20 "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
}

# ============================================================
# 参数解析
# ============================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch)       ARCH="$2"; shift 2 ;;
        --user)       DCV_USER="$2"; shift 2 ;;
        --password)   DCV_PASSWORD="$2"; shift 2 ;;
        --session)    SESSION_NAME="$2"; shift 2 ;;
        --no-reboot)  NO_REBOOT=true; shift ;;
        --gpu)        GPU_MODE=true; shift ;;
        --help|-h)    show_help ;;
        *)            log_error "未知参数: $1"; show_help ;;
    esac
done

# ============================================================
# 前置检查
# ============================================================
if [[ $EUID -ne 0 ]]; then
    log_error "请使用 root 权限运行此脚本: sudo bash $0"
    exit 1
fi

# 检查 Ubuntu 版本
if ! grep -q "24.04" /etc/os-release 2>/dev/null; then
    log_warn "此脚本针对 Ubuntu 24.04 设计，当前系统可能不兼容"
    read -rp "是否继续？(y/N) " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

# 自动检测架构
if [[ -z "$ARCH" ]]; then
    case "$(uname -m)" in
        x86_64)  ARCH="x86_64" ;;
        aarch64) ARCH="aarch64" ;;
        *)       log_error "不支持的架构: $(uname -m)"; exit 1 ;;
    esac
fi

if [[ "$ARCH" == "x86_64" ]]; then
    DEB_ARCH="amd64"
else
    DEB_ARCH="arm64"
fi

log_info "系统架构: $ARCH ($DEB_ARCH)"
log_info "DCV 用户: $DCV_USER"
log_info "会话名称: $SESSION_NAME"
log_info "GPU 模式: $GPU_MODE"

# ============================================================
# Step 1: 安装桌面环境
# ============================================================
log_step "Step 1/8: 安装桌面环境 (ubuntu-desktop + gdm3)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ubuntu-desktop gdm3

# 确保 GDM3 是默认显示管理器
echo "/usr/sbin/gdm3" > /etc/X11/default-display-manager
dpkg-reconfigure -f noninteractive gdm3 || true

log_info "桌面环境安装完成"

# ============================================================
# Step 2: 禁用 Wayland
# ============================================================
log_step "Step 2/8: 禁用 Wayland 协议"

GDM_CONF="/etc/gdm3/custom.conf"
if [[ -f "$GDM_CONF" ]]; then
    if grep -q "^WaylandEnable=false" "$GDM_CONF"; then
        log_info "Wayland 已禁用，跳过"
    else
        sed -i '/^\[daemon\]/a WaylandEnable=false' "$GDM_CONF"
        log_info "已在 $GDM_CONF 中禁用 Wayland"
    fi
else
    mkdir -p "$(dirname "$GDM_CONF")"
    cat > "$GDM_CONF" <<EOF
[daemon]
WaylandEnable=false
EOF
    log_info "已创建 $GDM_CONF 并禁用 Wayland"
fi

# ============================================================
# Step 3: 配置 X Server
# ============================================================
log_step "Step 3/8: 配置 X Server"

systemctl set-default graphical.target
log_info "已设置 graphical.target 为默认启动目标"

# 非 GPU 实例安装 XDummy
if [[ "$GPU_MODE" == false ]]; then
    log_info "非 GPU 模式，安装 XDummy 驱动"
    apt-get install -y xserver-xorg-video-dummy

    # 仅在没有 xorg.conf 时创建
    if [[ ! -f /etc/X11/xorg.conf ]]; then
        cat > /etc/X11/xorg.conf <<'XORG'
Section "Device"
    Identifier "DummyDevice"
    Driver "dummy"
    Option "UseEDID" "false"
    VideoRam 512000
EndSection

Section "Monitor"
    Identifier "DummyMonitor"
    HorizSync   5.0 - 1000.0
    VertRefresh 5.0 - 200.0
    Option "ReducedBlanking"
EndSection

Section "Screen"
    Identifier "DummyScreen"
    Device "DummyDevice"
    Monitor "DummyMonitor"
    DefaultDepth 24
    SubSection "Display"
        Viewport 0 0
        Depth 24
        Virtual 4096 2160
    EndSubSection
EndSection
XORG
        log_info "已创建 XDummy xorg.conf"
    fi
fi

# 安装 glxinfo
apt-get install -y mesa-utils

# ============================================================
# Step 4: 导入 GPG 密钥
# ============================================================
log_step "Step 4/8: 导入 Amazon DCV GPG 密钥"

WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"

wget -q https://d1uj6qtbmh3dt5.cloudfront.net/NICE-GPG-KEY
gpg --import NICE-GPG-KEY 2>/dev/null || true
log_info "GPG 密钥导入完成"

# ============================================================
# Step 5: 下载并安装 DCV Server
# ============================================================
log_step "Step 5/8: 下载 Amazon DCV 安装包"

if [[ "$ARCH" == "x86_64" ]]; then
    DCV_URL="https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-ubuntu2404-x86_64.tgz"
else
    DCV_URL="https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-ubuntu2404-aarch64.tgz"
fi

log_info "下载地址: $DCV_URL"
wget -q --show-progress "$DCV_URL" -O dcv-packages.tgz

tar -xzf dcv-packages.tgz
DCV_DIR=$(find . -maxdepth 1 -type d -name "nice-dcv-*" | head -1)
cd "$DCV_DIR"

log_step "Step 6/8: 安装 DCV 组件"

# 核心: DCV Server
log_info "安装 nice-dcv-server..."
apt-get install -y ./nice-dcv-server_*_${DEB_ARCH}.ubuntu2404.deb

# Web Viewer（浏览器访问）
log_info "安装 nice-dcv-web-viewer..."
apt-get install -y ./nice-dcv-web-viewer_*_${DEB_ARCH}.ubuntu2404.deb

# 将 dcv 用户加入 video 组
usermod -aG video dcv

# 虚拟会话支持
log_info "安装 nice-xdcv..."
apt-get install -y ./nice-xdcv_*_${DEB_ARCH}.ubuntu2404.deb

# GPU 共享（仅 x86_64 + GPU 模式）
if [[ "$GPU_MODE" == true && "$ARCH" == "x86_64" ]]; then
    log_info "安装 nice-dcv-gl (GPU 共享)..."
    apt-get install -y ./nice-dcv-gl_*_${DEB_ARCH}.ubuntu2404.deb || \
        log_warn "nice-dcv-gl 安装失败，可能缺少 GPU 驱动"
fi

# 麦克风重定向
apt-get install -y pulseaudio-utils || true

log_info "DCV 组件安装完成"

# ============================================================
# Step 7: 配置 DCV 服务
# ============================================================
log_step "Step 7/8: 配置 DCV 服务"

# 启用并启动 dcvserver
systemctl enable dcvserver

# 配置自动创建 console session
DCV_CONF="/etc/dcv/dcv.conf"
if [[ -f "$DCV_CONF" ]]; then
    # 设置自动创建 console session
    if ! grep -q "create-session" "$DCV_CONF"; then
        sed -i '/^\[session-management\/automatic-console-session\]/,/^\[/{s/.*/&/}' "$DCV_CONF" 2>/dev/null || true
        if ! grep -q "\[session-management\/automatic-console-session\]" "$DCV_CONF"; then
            cat >> "$DCV_CONF" <<EOF

[session-management/automatic-console-session]
owner="$DCV_USER"
EOF
            log_info "已配置自动 console session，owner=$DCV_USER"
        fi
    fi
fi

# ============================================================
# Step 8: 设置用户密码
# ============================================================
log_step "Step 8/8: 设置用户密码"

# 确保用户存在
if ! id "$DCV_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$DCV_USER"
    log_info "已创建用户: $DCV_USER"
fi

if [[ -n "$DCV_PASSWORD" ]]; then
    echo "${DCV_USER}:${DCV_PASSWORD}" | chpasswd
    log_info "已设置 $DCV_USER 的密码"
else
    log_warn "未指定密码，请手动设置: sudo passwd $DCV_USER"
fi

# ============================================================
# 清理
# ============================================================
cd /
rm -rf "$WORK_DIR"

# ============================================================
# 配置防火墙
# ============================================================
if command -v ufw &>/dev/null; then
    ufw allow 8443/tcp || true
    log_info "已在 UFW 中放行 8443/tcp"
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "=============================================="
echo -e "${GREEN}  Amazon DCV Server 安装完成!${NC}"
echo "=============================================="
echo ""
echo "  DCV 端口:    8443 (TCP)"
echo "  会话用户:    $DCV_USER"
echo "  会话名称:    $SESSION_NAME"
echo ""
echo "  重启后，通过浏览器访问:"
echo "    https://<服务器IP>:8443"
echo ""
echo "  或使用 DCV 客户端连接:"
echo "    https://download.amazondcv.com"
echo ""
echo "  手动管理会话:"
echo "    dcv list-sessions"
echo "    dcv create-session --type=console --owner $DCV_USER $SESSION_NAME"
echo "    dcv close-session $SESSION_NAME"
echo ""

if [[ "$NO_REBOOT" == true ]]; then
    log_warn "安装完成，请手动重启服务器以使所有配置生效"
    log_info "重启后 DCV 服务将自动启动"
else
    log_info "系统将在 10 秒后重启..."
    log_info "按 Ctrl+C 取消重启"
    sleep 10
    reboot
fi
