---
name: article2video
description: >
  将博客文章（URL 或本地 Markdown）自动转换为带语音、字幕、Ken Burns 动效的短视频。
  完整管道：文章拆分 → TTS 语音（含逐词时间戳）→ 图片获取 → 字幕生成 → Remotion 渲染 → FFmpeg 压缩。
  支持真实照片（Unsplash）和 AI 生图（Bedrock Nova Canvas）两种视觉方案。
  全流程约 40 分钟（ARM64），建议通过 SubAgent 委托执行。
  Activate when: 用户要求将文章转视频, 文章生成视频, 博客转视频, article to video,
  生成短视频, 做视频, 文章变视频, markdown to video, blog to video,
  视频生成, 演讲视频, 口播视频, 自动生成视频, article2video。
---

# Article2Video — 博客文章→短视频生成管道

将博客文章（3000-7000 字）自动转换为 7-10 分钟的专业短视频，包含 AI 演讲稿、TTS 语音、
Ken Burns 动效、原生 JSX 字幕渲染、进度条。

## 执行架构

本 Skill 执行时间较长（约 40 分钟），**必须**通过 SubAgent 委托执行：

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 独立执行 Phase 1-5
                          ├── Phase 1: 文章 → 演讲稿（~30 秒）
                          ├── Phase 2: TTS + 图片（~3 分钟，并行）
                          ├── Phase 3: TTS 时间戳字幕（~1 秒；whisper 备选 ~8 分钟）
                          ├── Phase 4: Remotion 渲染（~27 分钟）
                          ├── Phase 5: FFmpeg 压缩（~3 分钟）
                          └── 完成后向用户汇报结果
```

主 Agent 启动 SubAgent 时的 prompt 示例：

```
sessions_spawn:
  prompt: |
    你是 Article2Video 视频生成 Agent。
    请读取 ~/.openclaw/skills/article2video/SKILL.md 了解执行流程。
    用户要求将以下文章转为视频: <URL 或 .md 路径>
    选项: --style photo --slides 10 --voice zh-CN-YunyangNeural
    请执行 main.py 并汇报每个 Phase 的进度。
```

主 Agent 只负责：确认用户意图 → 启动 SubAgent → 等待完成通知。

## 进度汇报规范

SubAgent 在执行过程中**必须定期向用户汇报进度**，不能静默执行到结束。

### 阶段性汇报

| 节点 | 汇报内容 |
|------|----------|
| Phase 1 完成 | 📝 演讲稿已生成：N 段，总字数约 M 字 |
| Phase 2A 完成 | 🔊 语音合成完成：总时长 X 分 Y 秒 |
| Phase 2B 完成 | 🖼️ 图片就绪：N/M 张成功下载 |
| Phase 3 完成 | 📄 字幕提取完成：N 条字幕，覆盖全部音频 |
| Phase 4 开始 | 🎬 Remotion 渲染开始：预计 ~27 分钟（ARM64） |
| Phase 4 完成 | ✅ 视频渲染完成：X 帧，时长 Y 分钟 |
| Phase 5 完成 | 📦 压缩完成：原始 X MB → 压缩后 Y MB |

### 最终总结

```
🎬 Article2Video 生成总结
━━━━━━━━━━━━━━━━━━━━━━━━
标题：<文章标题>
幻灯片：<N> 张
视觉风格：photo / ai
声音：<TTS voice name>
时长：<X 分 Y 秒>
原始大小：<X> MB
压缩大小：<Y> MB（≤20MB）
输出路径：~/.openclaw/workspace/output/<slug>-video.mp4
状态：✅ 视频已就绪
━━━━━━━━━━━━━━━━━━━━━━━━
```

## Prerequisites

### 系统依赖

```bash
# FFmpeg（音频合并、视频压缩）
ffmpeg -version

# Node.js（Remotion 渲染）
node --version  # >= 18

# whisper.cpp（字幕提取备选方案）— 仅当 TTS 时间戳缺失时需要
# ls ~/whisper.cpp/main  # ARM64 编译
# ls ~/whisper.cpp/models/ggml-small.bin  # 466MB 模型

# Noto CJK 字体（中文渲染）
fc-list | grep "Noto Sans CJK"
```

### Python 依赖

```bash
pip install -r ~/.openclaw/skills/article2video/requirements.txt
```

### 环境变量

```bash
# AI 演讲稿生成（Phase 1）— 需要 LiteLLM 兼容的模型配置
# 使用 litellm 库，支持 OpenAI / Anthropic / Bedrock 等多种后端

# Unsplash 照片下载（Phase 2B photo 模式）— 无需 API key

# Bedrock AI 生图（Phase 2B ai 模式，可选）
aws configure  # 需要 us-east-1 区域访问 amazon.nova-canvas-v1:0
```

### Remotion 首次安装

```bash
cd ~/.openclaw/skills/article2video/remotion-template
npm install  # 首次约 2 分钟，后续复用 node_modules
```

### whisper.cpp 编译（ARM64）

如果未编译，参考：
```bash
cd ~
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
make -j4
# 下载 small 模型
bash models/download-ggml-model.sh small
```

## Workflow

### 视频格式

通过 `--format` 参数选择输出格式：

| 格式 | 分辨率 | 用途 |
|------|--------|------|
| `landscape` (默认) | 1920×1080 (16:9) | 电脑/电视/YouTube |
| `portrait` | 720×1280 (9:16) | 手机竖屏/抖音/Reels |
| `both` | 两种都渲染 | 全平台分发 |

**竖屏模板特点**：
- 通用 data-driven 设计（从 data.json 读取配置，不硬编码文章内容）
- Ken Burns 动效偏重垂直平移（适配 9:16 画幅）
- 标题在上方（上下堆叠式布局）
- 字幕区在下 1/3（`bottom: 100px`，避开手机底栏）
- 字号适配小屏：字幕 36px，标题 42-56px
- 4px 进度条保持底部

### 虚拟人物形象

视频中使用 3D 卡通虚拟形象作为品牌标识和虚拟主播。

**素材位置**：`assets/avatar/`
| 文件 | 说明 |
|------|------|
| `presenter-half-nobg.png` | 半身像（rembg 抠图，727×1290） |
| `presenter-half-original.jpg` | 半身像原图 |
| `presenter-sitting-nobg.png` | 坐姿全身（白色阈值抠图，备用） |
| `presenter-sitting-original.jpg` | 坐姿全身原图 |

**横屏（landscape, 1920×1080）使用方案**：
1. **模式 1（片头/片尾卡片）**：深色渐变背景 + 左侧虚拟白板（代码绘制，蓝色科技发光边框、角落光点、浅灰白渐变面板）写文章标题 + 右侧半身人物（`presenter-half-nobg.png`）
2. **模式 3 v3（正文出镜）**：右下角半身人物叠加在内容画面上，高度约 280px，半透明底座，无名牌

**竖屏（portrait, 720×1280）使用方案**：
- **模式 3 v3（全程出镜）**：右下角半身人物，高度约 320px，半透明底座，无名牌

**虚拟白板绘制参数（模式 1）**：
- 白板尺寸：880×560，圆角 12px
- 边框：`rgba(160, 210, 235, 0.63)` 2px + 内边框 `rgba(180, 220, 240, 0.31)` 1px
- 四角发光节点：`rgba(140, 220, 245)` 渐变，半径 6px
- 面板渐变：顶部 `rgb(238, 242, 250)` → 底部 `rgb(246, 248, 246)`
- 底部金属夹：30×8px 圆角矩形
- 倾斜角度：1.5°
- 文字字号：标题 68pt Bold / 副标题 44pt Regular / 品牌 30pt Bold

**抠图方案**：使用 `rembg`（u2net 深度学习模型），边缘干净。避免简单像素阈值抠图（白色残留严重）。

### Phase 1: 文章 → 演讲稿拆分（~30 秒）

**脚本**: `scripts/split_article.py`
**输入**: Markdown 文件或 URL
**输出**: `{workdir}/speech-script.json`

通过 AI（LiteLLM → Claude/GPT）将文章拆分为 N 段演讲脚本，每段包含：
- `slide`: 序号（1-N）
- `title`: 幻灯片标题
- `speech`: 口播文本（80-200 字，口语化）
- `visual`: 视觉描述（用于图片搜索/AI 生图 prompt）

**关键参数**:
- 每段 20-60 秒口播
- 第 1 段 = 开场引入，最后一段 = 总结呼吁
- 口播风格：口语化、短句、设问、数据支撑

### Phase 2A: TTS 语音合成 + 逐词时间戳（~2 分钟）

**脚本**: `scripts/generate_audio.py`
**输出**: `{workdir}/audio/slide-{01-N}.mp3` + `audio/slide-{01-N}.json` + `timing.json` + `full-audio.mp3` + `full-audio.wav`

使用 Edge TTS（免费无限量），同步采集 WordBoundary 事件输出逐词时间戳：
- 默认声音: `zh-CN-YunyangNeural`（男声，新闻风格）
- 语速: `rate="-5%"`，音调: `pitch="+0Hz"`
- 各段串行生成 → 收集 WordBoundary → 保存 slide-NN.json
- ffprobe 获取时长 → ffmpeg concat 合并 → 转 WAV

### Phase 2B: 视觉素材获取（~30 秒 / ~3 分钟）

**脚本（photo 模式）**: `scripts/fetch_images.py`
- 从 Unsplash 下载 1920×1080 照片
- 基于 `visual` 描述生成搜索关键词
- **成本**: $0

**脚本（ai 模式）**: `scripts/generate_ai_images.py`
- 使用 Bedrock Nova Canvas 生成 1280×720 插画
- 必须在 prompt 中强调 **NO TEXT/WORDS**
- **成本**: ~$0.08/张 × N 张

**输出**: `{workdir}/images/slide-{01-N}.jpg`

### Phase 3: 字幕生成（TTS 时间戳直出，~1 秒）

**脚本**: `scripts/extract_subtitles.py`
**输入**: `{workdir}/audio/slide-{01-N}.json`（TTS 时间戳）+ `timing.json`
**输出**: `{workdir}/subtitles.json`

**主要模式（TTS 时间戳）**：
- 读取 generate_audio.py 输出的逐词时间戳 JSON
- 按句号/问号/感叹号/分号分句，合并为句子级字幕
- 每条字幕 ≤40 中文字
- 使用原始演讲文本，**零错别字**
- 加上 slide 间累计偏移量，对齐全局时间轴

**备选模式（whisper.cpp）**：
- 仅当 TTS 时间戳文件不存在时自动触发
- 使用 whisper.cpp（small 模型）从音频"听写"字幕
- 注意：可能产生同音字错误

### Phase 4: Remotion 视频渲染（~27 分钟 ARM64）

**脚本**: `scripts/prepare_remotion.py`（准备 data.json + 复制素材）

1. 组装 `data.json`：合并 timing + subtitles + slides 信息
2. 复制素材到 `remotion-template/public/`
3. 执行 Remotion 渲染：

```bash
cd remotion-template
npx remotion render AgentVideo --output output.mp4 --codec h264 --crf 23 --log=error
```

**视觉效果**:
- Ken Burns 动效（5 种方向交替，缩放 1.0↔1.12）
- 暗色渐变叠层（`rgba(10,14,39,0.55)`）
- 原生 JSX 渲染标题/内容卡片
- 底部字幕条（白色 30px + 半透明背景）
- 底部进度条（青色渐变 `#00d4ff → #00e676`）

### Phase 5: FFmpeg 压缩（~3 分钟）

**脚本**: `scripts/compress_video.py`
**输出**: `~/.openclaw/workspace/output/{slug}-video.mp4`

2-pass VBR 压缩策略：
- 视频: `libx264 -b:v 280k -preset medium`
- 音频: `aac -b:a 96k`
- 目标: ≤20MB（飞书云盘上传限制）
- 7 分钟视频 → 约 19MB

## Configuration

配置文件：`SKILL_DIR/config.json`

```json
{
  "default_voice": "zh-CN-YunyangNeural",
  "default_style": "photo",
  "default_slides": 10,
  "tts_rate": "-5%",
  "tts_pitch": "+0Hz",
  "whisper_binary": "~/whisper.cpp/main",
  "whisper_model": "~/whisper.cpp/models/ggml-small.bin",
  "remotion_composition_id": "AgentVideo",
  "video_width": 1920,
  "video_height": 1080,
  "video_fps": 30,
  "video_crf": 23,
  "compress_target_mb": 20,
  "compress_video_bitrate": "280k",
  "compress_audio_bitrate": "96k",
  "bedrock_region": "us-east-1",
  "bedrock_model_id": "amazon.nova-canvas-v1:0",
  "ai_model": "anthropic/claude-sonnet-4-20250514",
  "output_dir": "~/.openclaw/workspace/output"
}
```

### 配置项说明

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `default_voice` | Edge TTS 声音 | `zh-CN-YunyangNeural` |
| `default_style` | 图片方案 `photo` / `ai` | `photo` |
| `default_slides` | 幻灯片数量 | `10` |
| `default_format` | 视频格式 `landscape` / `portrait` / `both` | `landscape` |
| `whisper_binary` | whisper.cpp 可执行文件路径 (备选) | `~/whisper.cpp/main` |
| `whisper_model` | whisper 模型路径 (备选) | `~/whisper.cpp/models/ggml-small.bin` |
| `compress_target_mb` | 压缩目标大小 (MB) | `20` |
| `ai_model` | Phase 1 演讲稿生成模型 | `anthropic/claude-sonnet-4-20250514` |

## Troubleshooting

| 问题 | 解决方案 |
|------|----------|
| `edge_tts` 超时 | 网络问题，重试即可；脚本支持中断恢复 |
| Unsplash 下载 403 | Unsplash Source 已下线，使用 `images.unsplash.com` 直接 URL |
| Pexels 下载 403 | Cloudflare 保护，改用 Unsplash |
| AI 生图文字乱码 | prompt 必须含 "NO TEXT/WORDS/LABELS"，negativeText 加 "text, words, letters" |
| AI 生图缺乏叙事性 | 推荐使用 `--style photo` 真实照片 |
| whisper.cpp 编译失败 | ARM64: `make -j4`；确保有 gcc/g++ |
| whisper 中文识别差 | 使用 `ggml-small.bin`（small 模型），不要用 tiny/base |
| Remotion 渲染慢 | ARM64 约 8 帧/秒，12000+ 帧需 ~27 分钟，属正常 |
| `interpolate` outputRange 报错 | 必须是纯数字，不能含 `'px'` 等字符串 |
| 中文引号导致 JS 语法错误 | 使用 `\u201c` `\u201d` 转义 |
| Remotion 找不到 Chrome | 首次运行自动下载 ARM64 headless Chrome 到 `node_modules/.remotion/` |
| 压缩后仍 >20MB | 降低 `compress_video_bitrate`（如 `200k`），或增加 CRF |
| pyenv 环境 python3 失败 | 使用 `command /usr/bin/python3` 或指定绝对路径 |
| 重复触发（heartbeat） | main.py 使用 PID 文件保护单实例运行 |

## 版本迭代经验

| 版本 | 方案 | 问题 | 改进方向 |
|------|------|------|----------|
| A (FFmpeg 拼接) | 静态图片 + 无转场 | 像 PPT 录屏，毫无生气 | → B |
| B (Remotion+AI图) | AI 生图 + Ken Burns | 缺乏叙事性，AI 文字渲染乱码 | → C |
| B2 (AI图v2) | 改进 prompt 禁止文字 | 画面仍不够自然 | → C |
| C (Remotion+照片) | 真实照片 + PNG 叠层字幕 | 字幕不够清晰 | → D |
| C2 (叠层优化) | 加深暗色叠层 + PNG overlay | PNG 叠层字体渲染模糊 | → D |
| **D (最终版)** | **原生 JSX 渲染全部文字** | **完美** | ✅ |

### 关键洞察

1. **原生 JSX 渲染 >> PNG 叠层** — 清晰度质的飞跃，文字锐利无锯齿
2. **真实照片 >> AI 生图** — 叙事性和自然度远超 AI 插画
3. **Ken Burns 动效** — 让静态照片有"呼吸感"，观感提升巨大
4. **暗色渐变叠层** — `rgba(10,14,39,0.55)` 保证白色文字在任何照片上可读
5. **单实例保护** — 必须防止 heartbeat 重复触发长时间渲染

## 成本与耗时

| 项目 | 成本 | 耗时 |
|------|------|------|
| AI 改写演讲稿 | ~$0.05 (Claude) | 30 秒 |
| Edge TTS 语音 | $0 | 2 分钟 |
| 照片下载 | $0 | 30 秒 |
| AI 生图 (可选) | $0.80 (10张) | 3 分钟 |
| whisper.cpp 字幕 (备选) | $0 | 8 分钟 (ARM64) |
| Remotion 渲染 | $0 | 27 分钟 (ARM64) |
| FFmpeg 压缩 | $0 | 3 分钟 |
| **总计 (photo)** | **~$0.05** | **~40 分钟** |
| **总计 (ai)** | **~$0.85** | **~43 分钟** |
