# F8-BiliPublisher — B站视频自动投稿

> 将 F6 Article2Video 生成的短视频，通过 B站 API 自动投稿到 Bilibili。
> 基于 [bilitool](https://github.com/timerring/bilitool) 实现，支持 CLI 和 Python API 两种调用方式。
> 支持自动上传视频、AI 生成标题/描述/标签、封面上传、分区选择、分P投稿。

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.10+ | 运行环境 |
| bilitool | B站上传工具库，`pip install bilitool` |
| Kiro CLI | AI 文本智能（标题/描述/标签生成） |
| B站账号 | 已通过 `bilitool login` 完成登录 |

Python 依赖：

```
bilitool
```

---

## 为什么用 bilitool？

与视频号不同，B站有成熟的第三方上传工具链。对比几个方案：

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| bilitool | CLI + Python API，活跃维护，支持分P/封面/多线路 | 需 Python 3.10+ | ✅ 推荐 |
| bilibili-api-python | 功能全面（视频/动态/直播） | 偏重读取，上传文档少 | 备选 |
| biliup | 直播录制+上传，Rust 核心 | 偏向直播场景 | 不适合 |
| CDP 浏览器自动化 | 无需第三方库 | 脆弱，维护成本高 | 不推荐 |

bilitool 提供了干净的 Python API：

```python
from bilitool import UploadController
UploadController().upload_video_entry(
    video_path="video.mp4",
    tid=95,              # 分区号（数码 → 95）
    title="视频标题",
    desc="视频描述",
    tag="标签1,标签2",
    cover="cover.jpg",   # 封面图
    source="",           # 转载来源（原创留空）
    copyright=1,         # 1=原创, 2=转载
)
```

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 执行方式：SubAgent 委托

本 Skill 涉及视频上传（大文件传输），执行时间约 3-10 分钟，**建议通过 SubAgent 委托执行**。

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行
                          ├── Phase 1: 检查登录状态
                          ├── Phase 2: AI 生成元数据（标题/描述/标签）
                          ├── Phase 3: 上传视频 + 封面
                          └── 完成后向用户汇报结果（含 BV 号）
```

### 前置检查

```bash
# bilitool
bilitool --version 2>/dev/null && echo "✓ bilitool" || echo "✗ pip install bilitool"

# 登录状态
bilitool check 2>/dev/null && echo "✓ 已登录" || echo "✗ 需要 bilitool login"

# Kiro CLI
kiro-cli --version 2>/dev/null && echo "✓ Kiro CLI" || echo "✗ Kiro CLI 未安装"
```

---

## 一、架构概览

```
F6 Article2Video 产出
  └── output-compressed.mp4 (≤20MB)
        │
        ▼
F8 BiliPublisher
  ├── Phase 1: 检查 bilitool 登录状态
  │     └── 未登录 → 提示用户 bilitool login
  │
  ├── Phase 2: AI 生成元数据
  │     ├── 标题（≤80字，Kiro CLI）
  │     ├── 描述（≤2000字）
  │     ├── 标签（逗号分隔，每个≤20字）
  │     └── 分区选择（tid）
  │
  ├── Phase 3: 上传视频
  │     ├── bilitool upload（自动选择最佳线路）
  │     ├── 上传封面（可选）
  │     └── 显示上传进度
  │
  └── Phase 4: 确认投稿结果
        └── 返回 BV 号 + 视频链接
```

---

## 二、B站分区参考（tid）

常用科技/知识类分区：

| 分区 | tid | 说明 |
|------|-----|------|
| 科学科普 | 201 | 科普知识 |
| 社科·法律·心理 | 124 | 社科人文 |
| 人文历史 | 228 | 历史文化 |
| 野生技术协会 | 122 | 技术分享 |
| 软件应用 | 230 | 软件教程 |
| 计算机技术 | 231 | 编程/IT |
| 科技杂谈 | 232 | 科技评论 |
| 数码 | 95 | 数码产品 |
| 职业职场 | 241 | 职场经验 |
| 日常 | 21 | 日常生活 |

> 完整分区列表参见 [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)

---

## 三、模块说明

```
bili-publisher/
├── SKILL.md                    # Agent 执行指南
├── main.py                     # 入口脚本
├── bili_uploader.py            # bilitool 封装 + 上传逻辑
├── metadata_generator.py       # AI 生成标题/描述/标签（复用 F7 模式）
├── video_cover.py              # 智能视频封面截取（与 F7 共享）
└── config.json                 # 默认配置（分区、标签等）
```

| 模块 | 职责 |
|------|------|
| `bili_uploader.py` | 封装 bilitool API，处理登录检查、上传、分P追加 |
| `metadata_generator.py` | 调用 Kiro CLI 生成 B站风格的标题/描述/标签 |
| `main.py` | 流程编排入口 |

---

## 四、使用方法

### 首次使用：登录

```bash
# 扫码登录（推荐）
bilitool login

# 验证登录状态
bilitool check
```

登录信息持久化存储，后续无需重复登录。

### 上传视频

```bash
# 基本用法：上传视频（AI 自动生成标题/描述/标签）
python3 main.py /path/to/video.mp4 --article /path/to/article.md

# 手动指定元数据
python3 main.py /path/to/video.mp4 \
  --title "AI 如何改变软件开发" \
  --desc "深入探讨 AI 编程助手的现状与未来" \
  --tags "AI,编程,软件开发" \
  --tid 232

# 指定封面 + 分区
python3 main.py /path/to/video.mp4 --cover /path/to/cover.jpg --tid 231

# 转载视频（需注明来源）
python3 main.py /path/to/video.mp4 --copyright 2 --source "https://example.com/original"

# 分P追加到已有视频
python3 main.py /path/to/part2.mp4 --append BV1xx411x7xx

# 指定上传线路（海外服务器推荐）
python3 main.py /path/to/video.mp4 --cdn ws
```

### CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `video` | 视频文件路径（必填） | — |
| `--article` | 原始文章路径（用于 AI 生成元数据） | — |
| `--title` | 手动指定标题（跳过 AI 生成） | AI 生成 |
| `--desc` | 手动指定描述 | AI 生成 |
| `--tags` | 逗号分隔的标签 | AI 生成 |
| `--tid` | B站分区号 | `232`（科技杂谈） |
| `--cover` | 封面图路径（留空则智能截取） | 智能截取 |
| `--no-auto-cover` | 禁用智能封面截取 | `false` |
| `--copyright` | 1=原创, 2=转载 | `1` |
| `--source` | 转载来源 URL（copyright=2 时必填） | — |
| `--cdn` | 上传线路: qn/bldsa/ws/bda2/tx/auto | `auto` |
| `--append` | 追加到已有视频的 BV 号（分P投稿） | — |
| `--yaml` | YAML 配置文件路径（覆盖所有参数） | — |

### YAML 配置文件

支持通过 YAML 文件批量配置上传参数：

```yaml
# upload_config.yaml
copyright: 1
tid: 232
title: "AI 如何改变软件开发"
desc: "深入探讨 AI 编程助手的现状与未来..."
tag: "AI,编程,软件开发,科技,程序员"
cover: "/path/to/cover.jpg"
dynamic: "新视频发布！#AI #编程"
```

```bash
python3 main.py /path/to/video.mp4 --yaml upload_config.yaml
```

---

## 五、智能封面截取（video_cover.py）

当用户未指定 `--cover` 时，自动从视频中智能截取最佳封面：

```
视频文件
  │
  ├── Step 1: 跳过片头(10%)片尾(8%)，在正文段提取 8 个候选帧
  │     ├── 优先: ffmpeg scene 滤镜检测场景变化点（内容最丰富的时刻）
  │     └── 回退: 均匀时间采样
  │
  ├── Step 2: AI 评分选择最佳帧
  │     ├── Kiro CLI 评分（信息密度、视觉吸引力、避免黑屏/模糊）
  │     └── 回退: 启发式选择（文件最大 = 内容最丰富）
  │
  └── Step 3: ffmpeg 裁剪到 B站推荐比例 (16:10)
```

独立使用：

```bash
# B站封面（16:10）
python3 video_cover.py video.mp4 --ratio 16:10 --title "文章标题" -o cover.jpg

# 视频号封面（16:9）
python3 video_cover.py video.mp4 --ratio 16:9 -o cover_channels.jpg

# 禁用场景检测，使用均匀采样
python3 video_cover.py video.mp4 --no-scene-detect -o cover.jpg
```

本模块与 F7-ChannelsPublisher 共享，修改时请同步更新。

---

## 六、与现有模块的复用关系

| 复用来源 | 复用内容 |
|---------|---------|
| `10. F6-Article2Video` | 视频文件输入（output-compressed.mp4） |
| `8. F4-WexinPublisher/cover_generator.py` | Kiro CLI 调用模式、AI 文本生成 |
| `11. F7-ChannelsPublisher/video_cover.py` | 智能封面截取模块（共享） |
| `11. F7-ChannelsPublisher/metadata_generator.py` | AI 元数据生成模式（标题/描述/标签） |

---

## 七、与 F7 视频号发布的对比

| 维度 | F7 视频号 | F8 B站 |
|------|----------|--------|
| 接入方式 | CDP 浏览器自动化 | Python API (bilitool) |
| 稳定性 | 中（前端可能变化） | 高（API 稳定） |
| 登录方式 | 浏览器 session | bilitool login 扫码 |
| 封面 | CDP 注入 | API 参数 |
| 分P投稿 | 不支持 | 支持（bilitool append） |
| 上传线路 | 浏览器默认 | 可选（qn/ws/tx 等） |
| headless 支持 | 受限 | 完全支持 |

---

## 八、在流水线中的位置

```
F1 采集 → F2 写作 → F4 发布微信公众号 → F5 归档
                  └──→ F6 短视频生成
                           ├──→ F7 发布视频号
                           └──→ F8 发布B站 ← 本模块
```

一篇文章，文字版走公众号（F4），视频版走视频号（F7）+ B站（F8），一鱼三吃。

---

## 九、已知限制与注意事项

| 限制 | 说明 |
|------|------|
| 登录有效期 | bilitool 的 cookie 有效期约 30 天，过期需重新 `bilitool login` |
| 视频审核 | B站投稿后需经过审核（通常 1-24 小时），审核期间视频不可见 |
| 标题长度 | B站标题上限 80 字符 |
| 标签限制 | 每个标签 ≤20 字符，最多 12 个标签 |
| 封面要求 | 推荐 16:10 比例，≤2MB，JPG/PNG |
| 视频大小 | 普通用户单个视频 ≤4GB，时长 ≤4 小时 |
| 分区选择 | tid 必须是有效的子分区号，不能用父分区号 |
