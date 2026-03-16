# Amazon DCV Server 自动安装指南 — Ubuntu 24.04

> 本文档供 AI Agent（如 OpenClaw）读取并在本机自动执行，部署 Amazon DCV Server 实现远程桌面访问。
>
> 参考: [AWS 官方文档](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-server.html)

## 前置条件（需用户提前完成）

以下操作需要用户在 AWS 控制台或通过 CLI 手动完成，Agent 无法代为执行：

1. 当前实例为 Ubuntu 24.04 LTS（建议至少 t3.medium）
2. 安全组入站规则已放行 TCP 8443（DCV 远程桌面端口）
3. 如需 GPU 加速，需使用 G4dn / G5 实例并提前安装 NVIDIA 驱动

## 安装流程

整个安装通过 `install-dcv-ubuntu24.sh` 脚本一键完成。脚本位于本文档同目录下。

### Step 1: 执行安装脚本

确认脚本路径后，直接在本机执行：

基本安装（非 GPU 实例）：

```bash
sudo bash install-dcv-ubuntu24.sh --password <密码> --no-reboot
```

GPU 实例安装：

```bash
sudo bash install-dcv-ubuntu24.sh --gpu --password <密码> --no-reboot
```

自定义用户和会话名：

```bash
sudo bash install-dcv-ubuntu24.sh --user <用户名> --session <会话名> --password <密码> --no-reboot
```

> 始终使用 `--no-reboot`，在验证完成后再手动触发重启。
>
> 如果用户未指定密码，请主动询问用户设置一个密码，不要跳过。

### Step 2: 重启服务器

```bash
sudo reboot
```

> 重启后 Agent 会断开连接，需等待约 1-2 分钟后重新连接。请提前告知用户这一点。

### Step 3: 验证安装

重启并重新连接后，依次执行以下检查：

**检查 DCV 服务状态：**

```bash
sudo systemctl status dcvserver --no-pager
```

期望输出包含 `Active: active (running)`。如果不是，执行：

```bash
sudo systemctl start dcvserver
```

**检查端口监听：**

```bash
ss -tlnp | grep 8443
```

期望输出包含 `LISTEN` 和 `8443`。如果无输出，查看日志：

```bash
sudo journalctl -u dcvserver -n 30 --no-pager
```

**检查 DCV 会话：**

```bash
dcv list-sessions
```

期望输出包含一个 console 类型的会话。如果无会话，创建：

```bash
sudo dcv create-session --type=console --owner ubuntu my-session
```

### Step 4: 向用户输出连接信息

所有验证通过后，获取本机公网 IP：

```bash
curl -s http://169.254.169.254/latest/meta-data/public-ipv4
```

然后向用户输出：

```
DCV 远程桌面已就绪。

连接方式：
  浏览器访问: https://<公网IP>:8443
  DCV 客户端下载: https://download.amazondcv.com

登录凭据：
  用户名: <--user 参数值，默认 ubuntu>
  密码: <安装时设置的密码>

注意: 首次浏览器访问会提示证书不受信任（自签名证书），选择继续访问即可。
```

## 脚本参数参考

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--arch <x86_64\|aarch64>` | CPU 架构 | 自动检测 |
| `--user <username>` | DCV 会话所有者 | `ubuntu` |
| `--password <password>` | 用户登录密码 | 未指定则需手动设置 |
| `--session <name>` | DCV 会话名称 | `my-session` |
| `--no-reboot` | 安装后不自动重启 | 默认自动重启 |
| `--gpu` | 启用 GPU 组件 | 关闭 |
| `--help` | 显示帮助 | — |

## 脚本执行内容

脚本自动完成以下操作，无需手动干预：

| 步骤 | 操作 |
|------|------|
| 1 | 安装 `ubuntu-desktop` + `gdm3` 桌面环境 |
| 2 | 禁用 Wayland 协议（DCV 不支持） |
| 3 | 配置 X Server，非 GPU 实例自动安装 XDummy 驱动 |
| 4 | 导入 Amazon DCV GPG 签名密钥 |
| 5 | 下载并安装 DCV Server、Web Viewer、虚拟会话支持 |
| 6 | GPU 模式额外安装 nice-dcv-gl |
| 7 | 启用 dcvserver 开机自启，配置自动 console session |
| 8 | 设置用户密码，配置 UFW 防火墙放行 8443 |

## 故障排查

| 症状 | 排查命令 | 处理方式 |
|------|----------|----------|
| DCV 服务未运行 | `sudo journalctl -u dcvserver -n 50 --no-pager` | 根据日志定位错误 |
| 8443 端口未监听 | `ss -tlnp \| grep 8443` | `sudo systemctl restart dcvserver` |
| 无 DCV 会话 | `dcv list-sessions` | `sudo dcv create-session --type=console --owner ubuntu my-session` |
| X Server 未运行 | `ps aux \| grep X \| grep -v grep` | `sudo systemctl isolate multi-user.target && sudo systemctl isolate graphical.target` |
| Wayland 未禁用 | `grep WaylandEnable /etc/gdm3/custom.conf` | 应含 `WaylandEnable=false`，否则手动添加后 `sudo systemctl restart gdm3` |

## 参考链接

- [Amazon DCV 管理员指南 - Linux 安装](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-server.html)
- [Amazon DCV 前提条件](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-prereq.html)
- [Amazon DCV 安装后检查](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-checks.html)
- [Amazon DCV 客户端下载](https://download.amazondcv.com)
