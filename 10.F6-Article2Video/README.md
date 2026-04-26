# F6-Article2Video — 博客文章自动转短视频

> 从博客文章（URL 或本地 Markdown），自动生成演讲稿、合成语音、渲染视觉幻灯片，最终合成 3-5 分钟短视频。
> 支持横屏（1920×1080）和竖屏（720×1280）双模板，含虚拟人物形象出镜、Ken Burns 动效、结构化数据内容（stats/list/comparison/quote/grid 五种布局）、原生 JSX 字幕渲染。

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | 运行环境 |
| Node.js 18+ | Remotion 视频渲染 |
| FFmpeg | 音频合并、视频压缩，`brew install ffmpeg`（macOS）或 `sudo apt install ffmpeg`（Ubuntu） |
| AWS 凭证 | `~/.aws/credentials`，用于 Bedrock AI 生图（可选）和 Phase 1 演讲稿生成 |
| Noto Sans CJK 字体 | 中文渲染，`fc-list \| grep "Noto Sans CJK"` 验证 |

Python 依赖：

```
edge-tts>=6.1.0
litellm>=1.0.0
```

可选依赖：
- `rembg` — 虚拟人物形象抠图（仅制作/更新 avatar 素材时需要）
- `whisper.cpp` — 字幕生成备选方案（仅当 TTS 时间戳缺失时需要）

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 执行方式：SubAgent 委托

本 Skill 执行时间较长（约 40 分钟），**必须通过 SubAgent 委托执行**，避免阻塞主 Agent。

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行完整流程
                          ├── Phase 1: 文章 → 演讲稿 + 结构化数据（~45 秒）
                          ├── Phase 2: TTS 语音 + 图片获取（~3 分钟，并行）
                          ├── Phase 3: TTS 时间戳字幕生成（~1 秒）
                          ├── Phase 4: Remotion 视频渲染（~27 分钟 ARM64）
                          ├── Phase 5: FFmpeg 压缩（~3 分钟）
                          └── 完成后向用户汇报结果
```

启动 SubAgent 的 prompt：

```
sessions_spawn:
  prompt: |
    你是 Article2Video 视频生成 Agent。
    请读取 skills/article2video/SKILL.md 了解你的职责和执行流程。
    用户要求将以下文章转为视频: <URL 或 .md 路径>
    视频格式: portrait（竖屏）/ landscape（横屏）/ both（双版本）
    开始执行。
```

### 主 Agent 职责

1. 确认用户意图（哪篇文章、横屏/竖屏/双版本、photo/ai 风格）
2. 启动 SubAgent（sessions_spawn）
3. 等待 SubAgent 完成，向用户汇报结果

**不要**在主 Agent 中直接运行 `main.py`，那会阻塞 40+ 分钟。

### 进度汇报规范

SubAgent 在执行过程中**必须定期向用户汇报进度**，不能静默执行到结束。

阶段性汇报节点：

| 节点 | 汇报内容 |
|------|----------|
| Phase 1 完成 | 📝 演讲稿已生成：N 段，总字数约 M 字 |
| Phase 2A 完成 | 🔊 语音合成完成：总时长 X 分 Y 秒 |
| Phase 2B 完成 | 🖼️ 图片就绪：N/M 张成功 |
| Phase 3 完成 | 📄 字幕生成完成：N 条字幕 |
| Phase 4 开始 | 🎬 Remotion 渲染开始：预计 ~27 分钟（ARM64） |
| Phase 4 完成 | ✅ 视频渲染完成：时长 Y 分钟 |
| Phase 5 完成 | 📦 压缩完成：原始 X MB → 压缩后 Y MB |

### 前置检查（启动前快速验证）

```bash
# FFmpeg
ffmpeg -version 2>/dev/null && echo "✓ FFmpeg" || echo "✗ FFmpeg 未安装"

# Node.js
node --version 2>/dev/null && echo "✓ Node.js" || echo "✗ Node.js 未安装"

# Python 依赖
python3 -c "import edge_tts; import litellm" 2>/dev/null && echo "✓ Python deps" || echo "✗ pip install edge-tts litellm"

# Remotion node_modules
[ -d "article2video/remotion-template/node_modules" ] && echo "✓ Remotion deps" || echo "✗ 需要 cd remotion-template && npm install"

# 中文字体
fc-list | grep -q "Noto Sans CJK" && echo "✓ CJK 字体" || echo "✗ 需要安装 Noto Sans CJK"

# AWS 凭证（AI 生图可选）
aws sts get-caller-identity 2>/dev/null && echo "✓ AWS 凭证" || echo "⚠ AWS 凭证不可用（photo 模式不需要）"
```

如有缺失，参考本文档「安装部署」章节补齐后再启动 SubAgent。

---

## 一、定位与目标

将已有的博客内容（F2 产出的文章、或任意 MD/URL）转化为短视频形式，扩展内容分发渠道。

在现有流水线中的位置：

```
F1 采集 → F2 写作 → F4 发布微信 → F5 归档
                  └──→ F6 短视频 ← 也可独立输入任意文章
```

核心价值：同一篇文章，文字版走微信公众号，视频版走视频号/B站/YouTube，一鱼多吃。

---

## 二、完整管道架构

```
博客文章 (.md / URL)
  │
  ├─ Phase 1: 内容拆分（AI）
  │    └─ 文章 → 10 段演讲稿 + 结构化数据（key_facts）
  │    └─ 输出: speech-script.json
  │
  ├─ Phase 2A: 语音合成 + 逐词时间戳（并行）
  │    └─ Edge TTS (zh-CN-YunyangNeural, rate=-5%)
  │    └─ 输出: audio/slide-{01-10}.mp3 + slide-{01-10}.json（时间戳）+ timing.json
  │
  ├─ Phase 2B: 视觉素材（并行）
  │    ├─ 方案 A（推荐）: Unsplash 真实照片（$0）
  │    ├─ 方案 B: Bedrock Nova Canvas AI 生图（$0.08/张）
  │    └─ 输出: images/slide-{01-10}.jpg
  │
  ├─ Phase 3: 字幕生成
  │    └─ 主方案: TTS 逐词时间戳 + 原文拼接（零错别字，<1秒）
  │    └─ 备选: whisper.cpp 语音识别（有同音字错误风险，~8分钟）
  │    └─ 输出: subtitles.json
  │
  ├─ Phase 4: 视频渲染（Remotion）
  │    └─ 双模板：横屏 1920×1080 + 竖屏 720×1280
  │    └─ 五层合成：背景图(Ken Burns) + 暗叠层 + 结构化内容 + 字幕 + 虚拟人物
  │    └─ 输出: output.mp4
  │
  └─ Phase 5: 压缩与交付
       └─ FFmpeg CRF 压缩至 ≤20MB
       └─ 输出: output-compressed.mp4
```

预计总耗时：~40 分钟（ARM64 c7g.large），其中 Remotion 渲染占 ~27 分钟。

---

## 三、技术选型

| 环节 | 推荐方案 | 备选 | 理由 |
|------|---------|------|------|
| 内容拆分 | LiteLLM → Claude | 任何 LiteLLM 兼容模型 | 灵活切换后端 |
| 演讲稿生成 | 同上 | — | — |
| TTS 语音 | Edge TTS (YunyangNeural) | Amazon Polly Neural | 免费无限量，质量够用 |
| 视觉素材 | Unsplash 真实照片 | Bedrock Nova Canvas AI 生图 | 真实照片叙事性更强，$0 |
| 视频渲染 | Remotion 4.0 (React JSX) | FFmpeg 静态拼接 | 原生文字渲染清晰，动效丰富 |
| 字幕 | TTS 逐词时间戳直出 | whisper.cpp 听写 | 零错别字，<1 秒 |
| 结构化内容 | AI 自动提取 key_facts + 5 种布局 | 手动 Slidev | 全自动，信息密度高 |
| 压缩 | FFmpeg CRF 模式 | — | 行业标准 |

---

## 四、结构化数据内容（方案 A）

之前的通用模板正文 slides 只有「照片 + 标题 + 字幕」，信息密度低，观众只能听不能看。方案 A 在 Phase 1 拆分时让 AI 额外输出每个 slide 的结构化数据（`key_facts`），Remotion 模板根据数据类型自动选择视觉布局。

### key_facts 数据格式

```json
{
  "slide": 2,
  "title": "传统开发模式已过时",
  "speech": "...",
  "visual": "...",
  "key_facts": {
    "type": "stats",
    "items": [
      {"value": "1.2亿", "label": "年化 Sales Pipeline", "color": "#22d3ee"},
      {"value": "90%", "label": "试点项目用错误方法", "color": "#fb923c"},
      {"value": "29,000", "label": "Agentforce 签约数", "color": "#4ade80"}
    ]
  }
}
```

### 五种布局类型

| 类型 | 用途 | items 结构 | 最佳数量 |
|------|------|-----------|---------|
| `stats` | 大数字卡片 | `{value, label, color}` | 2-4 个 |
| `list` | 图标列表 | `{icon, title, desc, color}` | 3-5 条 |
| `comparison` | A vs B 对比 | `{left, right, label}` | 2-4 行 |
| `quote` | 关键引言 | `{text, source}` | 1 条 |
| `grid` | 2×2 概念网格 | `{icon, title, desc, color}` | 4 个 |

### 布局渲染风格

通用卡片样式：`background: rgba(10,14,39,0.75); border-radius: 16px; backdrop-filter: blur(8px)`

| 布局 | 视觉特征 |
|------|----------|
| stats | 数字 60px 加粗 + 主题色 + 发光阴影，水平等宽分栏 |
| list | 左侧 4px 彩色边框 + emoji icon 40px + 标题/描述，垂直堆叠 |
| comparison | 左右两列（A vs B），中间分隔线，对比色红/灰 vs 绿/青 |
| quote | 大引号装饰 80px + 引言 28px 斜体 + 来源 16px 灰色 |
| grid | 2×2 CSS Grid，每格带彩色边框和 emoji icon |

布局区域约束：横屏 padding-right 预留 300px 给人物出镜，竖屏 padding-bottom 预留 350px 给字幕和人物。

颜色推荐：`#22d3ee`(青) `#fb923c`(橙) `#4ade80`(绿) `#f87171`(红) `#60a5fa`(蓝) `#c084fc`(紫) `#facc15`(黄)

---

## 五、开场白定制

标准开场白：
> 大家好，我是薛以致用，科技有深度，职场有办法，管理有温度，更多内容请关注公众号军见数科。

Phase 1 拆分时 Prompt 中固定第一段 speech 的开头为此标准开场白。通过 `config.json` 配置：

```json
{
  "opening_line": "大家好，我是薛以致用，科技有深度，职场有办法，管理有温度，更多内容请关注公众号军见数科。",
  "branding": "薛以致用 · AI 洞察",
  "channel_name": "军见数科"
}
```

---

## 六、虚拟人物形象方案

视频中使用 3D 卡通虚拟形象作为品牌标识和虚拟主播。

### 素材

| 素材 | 路径 | 尺寸 | 用途 |
|------|------|------|------|
| 半身像（rembg 抠图）| `assets/avatar/presenter-half-nobg.png` | 727×1290 | 片头白板 + 正文出镜 |
| 半身像原图 | `assets/avatar/presenter-half-original.jpg` | 727×1290 | 备份 |
| 坐姿全身（抠图）| `assets/avatar/presenter-sitting-nobg.png` | 1079×1434 | 备用 |
| 坐姿全身原图 | `assets/avatar/presenter-sitting-original.jpg` | 1079×1434 | 备份 |

抠图使用 `rembg`（u2net 深度学习模型），边缘干净。避免简单像素阈值抠图（白色残留严重，在深色背景上很明显）。

### 横屏方案（1920×1080）— 五层合成 + 三段式结构

| Slide | 模式 | 层次 |
|-------|------|------|
| 第 1 个（片头）| 模式 1 | 深色背景 + 虚拟白板(标题) + 半身人物 |
| 第 2 到 N-1（正文）| 模式 3 v3 | 照片(Ken Burns) + 暗叠层 + 结构化内容 + 字幕 + 人物出镜 |
| 第 N 个（片尾）| 模式 1 | 深色背景 + 结束语 + 半身人物 |

**模式 1（片头/片尾卡片）**：

```
┌──────────────────────────────────────────────┐
│                                              │
│   ┌─────────────┐                            │
│   │  虚拟白板    │          ┌──────┐         │
│   │  ┌─────────┐│          │      │         │
│   │  │ 标题    ││          │ 半身 │         │
│   │  │ 副标题  ││          │ 人物 │         │
│   │  │ ——————  ││          │      │         │
│   │  │ 品牌    ││          │      │         │
│   │  └─────────┘│          └──────┘         │
│   └─────────────┘                            │
│                                              │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 进度条    │
└──────────────────────────────────────────────┘
```

虚拟白板参数：880×560，圆角 12px，蓝色科技发光边框 + 角落光点 + 浅灰白渐变面板 + 底部金属夹 + 1.5° 倾斜。

**模式 3 v3（正文出镜）**：

```
┌──────────────────────────────────────────────┐
│   品牌水印                                    │
│                                              │
│     [ 标题 / 数据卡片 / 内容 ]                 │
│                                              │
│                                  ┌──────┐    │
│                                  │ 半身 │    │
│   [ 字幕条 ]                      │ 人物 │    │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓└──────┘▓▓▓│
└──────────────────────────────────────────────┘
```

人物高度 ~280px，右下角，透明度 0.85。

### 竖屏方案（720×1280）— 全程模式 3 v3

```
┌──────────────┐
│  📌 标题     │
│  ────────    │
│              │
│  [ 背景图    │
│    Ken Burns │
│    + 暗叠层 ]│
│              │
│         ┌──┐ │
│         │人│ │
│ [字幕条]│物│ │
│▓▓▓▓▓▓▓▓└──┘▓│
└──────────────┘
```

人物高度 ~320px，右下角，透明度 0.85。

---

## 七、各阶段关键参数与踩坑

### Phase 1: 内容拆分

- 输入：Markdown 文章（3000-7000 字）
- 输出：`speech-script.json` — N 段演讲脚本 + 结构化数据（默认 10 段）
- 每段 20-60 秒口播文本（约 80-200 字）
- 第 1 段 = 标准开场白 + 引入，最后一段 = 总结呼吁
- `visual` 字段用于指导图片搜索/AI 生图 prompt
- `key_facts` 字段（第 1 和最后一个 slide 除外）：AI 自动从演讲文本提取数据点，选择最匹配的布局类型

### Phase 2A: TTS 语音 + 逐词时间戳

- Edge TTS `zh-CN-YunyangNeural`，`rate="-5%"`
- ⚠️ 必须用 `communicate.stream(boundary="WordBoundary")`，不能用 `communicate.save()`
- ⚠️ edge_tts 7.x 默认 `SentenceBoundary`，必须显式传 `boundary="WordBoundary"`
- ⚠️ offset/duration 单位是 100 纳秒，除以 10000 转毫秒

### Phase 2B: 视觉素材

- **photo 模式（推荐）**：Unsplash 直接 URL `images.unsplash.com/photo-XXX?w=1920&h=1080&fit=crop`，无需 API key
- **ai 模式**：Bedrock `amazon.nova-canvas-v1:0`（us-east-1），prompt 必须含 "NO TEXT/WORDS/LABELS"
- ⚠️ `source.unsplash.com` 已下线（503），使用 `images.unsplash.com` 直接 URL
- ⚠️ AI 生图渲染的文字是乱码 → 推荐真实照片

### Phase 3: 字幕生成

- 主方案：TTS 逐词时间戳 + 原文直出（零错别字，<1 秒）
- 按标点分句（。！？；），每条 ≤40 中文字
- 加 slide 间累计偏移量对齐全局时间轴
- 备选：whisper.cpp（small 模型），仅当 TTS 时间戳文件不存在时自动触发

### Phase 4: Remotion 视频渲染

- Remotion 4.0.438 + React JSX
- 横屏 `AgentVideo`（1920×1080）：~8 fps，~27 分钟（ARM64）
- 竖屏 `AgentVideoPortrait`（720×1280）：~13 fps，~14 分钟（ARM64）
- 五层合成：背景图(Ken Burns) + 暗色渐变叠层 + 结构化内容(key_facts) + 字幕 + 虚拟人物
- 结构化内容根据 `key_facts.type` 自动选择 stats/list/comparison/quote/grid 布局
- ⚠️ ARM64 渲染速度比 x86 慢 2-3 倍
- ⚠️ 单实例保护（PID 文件锁）防止并发渲染

### Phase 5: FFmpeg 压缩

- 目标 ≤20MB（飞书云盘上传限制）
- CRF 模式：`libx264 -crf 28 -preset medium -c:a aac -b:a 96k`
- 竖屏压缩优势：720×1280 原始仅 ~30-50MB，压缩后 ≤12MB

---

## 八、架构与模块

> `main.py` 是唯一入口，包含完整的五阶段流程编排。无需任何额外脚本。

```
article2video/
├── SKILL.md                              # Agent 执行指南（SubAgent 委托执行）
├── main.py                               # 唯一入口（python3 main.py <文章路径> [选项]）
├── config.json                           # 默认配置
├── requirements.txt                      # Python 依赖（edge-tts, litellm）
├── assets/
│   └── avatar/
│       ├── presenter-half-nobg.png       # 半身像 rembg 抠图（727×1290）
│       ├── presenter-half-original.jpg   # 半身像原图
│       ├── presenter-sitting-nobg.png    # 坐姿全身抠图（备用）
│       └── presenter-sitting-original.jpg# 坐姿全身原图
├── scripts/
│   ├── split_article.py                  # Phase 1: AI 演讲稿拆分 + key_facts 提取
│   ├── generate_audio.py                 # Phase 2A: TTS + 逐词时间戳
│   ├── fetch_images.py                   # Phase 2B: Unsplash 照片下载
│   ├── generate_ai_images.py             # Phase 2B 备选: Bedrock AI 生图
│   ├── extract_subtitles.py              # Phase 3: TTS 时间戳字幕
│   ├── prepare_remotion.py               # Phase 4 前置: data.json 组装（含 key_facts）+ 素材复制
│   └── compress_video.py                 # Phase 5: FFmpeg CRF 压缩
└── remotion-template/
    ├── package.json                      # Remotion 4.0.438
    ├── src/
    │   ├── index.js                      # Remotion 入口
    │   ├── Root.jsx                      # 注册双 Composition（横屏 + 竖屏）
    │   ├── VideoComposition.jsx          # 横屏 1920×1080（片头白板 + 结构化内容 + 人物）
    │   └── VideoCompositionPortrait.jsx  # 竖屏 720×1280（结构化内容 + 人物）
    └── public/
        └── (渲染时动态填充 data.json、图片、音频)
```

### 模块说明

| 模块 | 职责 |
|------|------|
| `split_article.py` | 通过 LiteLLM 调用 AI 模型，将文章拆分为 N 段演讲脚本，每段含 title/speech/visual/key_facts |
| `generate_audio.py` | Edge TTS 逐段生成 MP3 + WordBoundary 逐词时间戳 JSON，ffmpeg concat 合并 |
| `fetch_images.py` | 基于 visual 描述生成搜索关键词，从 Unsplash 下载 1920×1080 照片 |
| `generate_ai_images.py` | Bedrock Nova Canvas 生成 1280×720 插画，prompt 强调 NO TEXT |
| `extract_subtitles.py` | 读取 TTS 时间戳 + 原文，按标点分句生成字幕 JSON；备选 whisper.cpp |
| `prepare_remotion.py` | 组装 data.json（timing + subtitles + slides + key_facts），复制素材到 remotion-template/public/ |
| `compress_video.py` | FFmpeg CRF 压缩至目标大小（默认 ≤20MB） |

---

## 九、安装部署

### 7.1 EC2 环境（推荐，ARM64 c7g.large）

```bash
# 1. 系统依赖
sudo apt update
sudo apt install -y ffmpeg fonts-noto-cjk

# 2. Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 3. Python 依赖
pip install edge-tts litellm

# 4. Remotion 依赖（首次）
cd article2video/remotion-template
npm install   # 约 2 分钟，后续复用 node_modules

# 5. 验证
ffmpeg -version
node --version
python3 -c "import edge_tts; import litellm; print('✓ Python deps OK')"
```

### 7.2 macOS 本地开发

```bash
brew install ffmpeg node
pip install edge-tts litellm
cd article2video/remotion-template && npm install
```

### 7.3 whisper.cpp 编译（可选，仅备选字幕方案需要）

```bash
cd ~
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
make -j4
bash models/download-ggml-model.sh small   # 下载 466MB 模型
```

---

## 十、使用方法

`main.py` 是唯一入口，包含完整的五阶段流程。

```bash
# 竖屏视频（手机/短视频平台，推荐）
python3 main.py ./article.md --format portrait

# 横屏视频（电脑/大屏/YouTube）
python3 main.py ./article.md --format landscape

# 双版本同时输出
python3 main.py ./article.md --format both

# 自定义选项
python3 main.py ./article.md --format both --style photo --slides 10 --voice zh-CN-YunyangNeural

# 调试：只跑到 Phase 3（不渲染视频）
python3 main.py ./article.md --skip-render

# 调试：跑到 Phase 4（不压缩）
python3 main.py ./article.md --skip-compress
```

**pyenv 环境兼容写法**（Agent 执行时推荐）：

```bash
env -i HOME="$HOME" \
  PATH="/usr/bin:/usr/local/bin:/opt/homebrew/bin:/bin:$HOME/.local/bin:$HOME/.nvm/versions/node/v18/bin" \
  AWS_SHARED_CREDENTIALS_FILE="$HOME/.aws/credentials" \
  AWS_CONFIG_FILE="$HOME/.aws/config" \
  python3 "article2video/main.py" "./article.md" --format portrait
```

### CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `article` | Markdown 文件路径或 URL | （必填） |
| `--format` | `landscape` / `portrait` / `both` | `landscape` |
| `--style` | `photo`（Unsplash）/ `ai`（Bedrock） | `photo` |
| `--slides` | 幻灯片数量 | `10` |
| `--voice` | Edge TTS 声音名称 | `zh-CN-YunyangNeural` |
| `--skip-render` | 跳过 Phase 4-5（调试用） | — |
| `--skip-compress` | 跳过 Phase 5（保留原始输出） | — |

---

## 十一、配置文件 config.json

```json
{
  "default_voice": "zh-CN-YunyangNeural",
  "default_style": "photo",
  "default_slides": 10,
  "default_format": "landscape",
  "tts_rate": "-5%",
  "tts_pitch": "+0Hz",
  "opening_line": "大家好，我是薛以致用，科技有深度，职场有办法，管理有温度，更多内容请关注公众号军见数科。",
  "branding": "薛以致用 · AI 洞察",
  "channel_name": "军见数科",
  "whisper_binary": "~/whisper.cpp/main",
  "whisper_model": "~/whisper.cpp/models/ggml-small.bin",
  "remotion_composition_id": "AgentVideo",
  "video_width": 1920,
  "video_height": 1080,
  "video_fps": 30,
  "video_crf": 23,
  "compress_target_mb": 20,
  "compress_crf": 28,
  "compress_audio_bitrate": "96k",
  "bedrock_region": "us-east-1",
  "bedrock_model_id": "amazon.nova-canvas-v1:0",
  "ai_model": "anthropic/claude-sonnet-4-20250514",
  "output_dir": "~/.openclaw/workspace/output"
}
```

---

## 十二、与现有模块的复用关系

| 复用来源 | 复用内容 |
|---------|---------|
| F4 input_handler.py | 文章加载逻辑可参考（URL 抓取 / 本地 MD 读取） |
| F4 SubAgent 委托模式 | 长时间任务的执行架构一致 |
| F2 AI 调用模式 | LiteLLM 文本处理（场景拆分、演讲稿） |
| 通用 AWS 凭证 | Bedrock AI 生图访问 |

---

## 十三、成本与耗时

| 项目 | 成本 | 耗时 |
|------|------|------|
| AI 拆分演讲稿 + key_facts | ~$0.08 (Claude) | 45 秒 |
| Edge TTS 语音 + 时间戳 | $0 | 1-2 分钟 |
| 照片下载（Unsplash） | $0 | 15-30 秒 |
| AI 生图（可选，Bedrock） | $0.80 (10 张) | 3 分钟 |
| TTS 字幕生成 | $0 | <1 秒 |
| Remotion 渲染（横屏） | $0 | ~27 分钟 (ARM64) |
| Remotion 渲染（竖屏） | $0 | ~14 分钟 (ARM64) |
| FFmpeg 压缩 | $0 | 2-3 分钟 |

| 总计 | 成本 | 耗时 |
|------|------|------|
| 竖屏（photo） | ~$0.08 | ~18 分钟 |
| 横屏（photo） | ~$0.08 | ~31 分钟 |
| 双版本（photo） | ~$0.08 | ~45 分钟 |

---

## 十四、版本迭代经验

| 版本 | 方案 | 核心改进 | 结论 |
|------|------|---------|------|
| A (FFmpeg 拼接) | 静态图片 + 无转场 | 基础版 | ❌ |
| B (Remotion+AI 图) | AI 生图 + Ken Burns | Ken Burns 动效 | ❌ |
| C (Remotion+照片) | 真实照片 + whisper 字幕 | 结构化文本（手动） | ❌ |
| D (横屏定稿) | 原生 JSX + 照片 | 清晰度飞跃 | ⚠️ |
| D2 (双模板+TTS 字幕) | + 竖屏 + TTS 时间戳 | 零错别字 | ⚠️ |
| D3 (人物形象) | + 片头白板 + 正文出镜 | 品牌感 | ⚠️ |
| **D4 (结构化数据) ✅** | **+ key_facts 自动布局 + 标准开场白** | **信息密度 + 品牌统一** | ✅ |

### 关键洞察

1. **原生 JSX 渲染文字 >> PNG 叠层** — 清晰度质的飞跃
2. **真实照片 >> AI 生图** — 叙事性和自然度远超 AI 插画
3. **TTS 时间戳直出 >> whisper 听写** — 零错别字 + 省时 8 分钟
4. **竖屏需要独立设计** — 不是裁一刀，布局必须重排
5. **虚拟白板由代码绘制 >> 原图写字** — 完全可控，无透视对齐烦恼
6. **rembg (u2net) >> 像素阈值抠图** — 深色背景下差距巨大
7. **结构化数据 >> 纯标题** — 信息密度翻倍，观众能"看到"数据
8. **AI 自动选布局 >> 手动 Slidev** — 全自动，无需人工排版

---

## 十五、已知问题与注意事项

| 问题 | 解决方案 |
|------|----------|
| `edge_tts` 超时 | 网络问题，重试即可；脚本支持中断恢复 |
| Unsplash 下载 403 | `source.unsplash.com` 已下线，使用 `images.unsplash.com` 直接 URL |
| AI 生图文字乱码 | prompt 必须含 "NO TEXT/WORDS/LABELS"，推荐用 `--style photo` |
| whisper.cpp 中文识别差 | 使用 `ggml-small.bin`（small 模型），不要用 tiny/base |
| Remotion 渲染慢 | ARM64 约 8 帧/秒属正常，12000+ 帧需 ~27 分钟 |
| `interpolate` outputRange 报错 | 必须是纯数字，不能含 `'px'` 等字符串 |
| 中文引号导致 JS 语法错误 | 使用 `\u201c` `\u201d` 转义 |
| Remotion 找不到 Chrome | 首次运行自动下载 ARM64 headless Chrome |
| 压缩后仍 >20MB | 降低 `compress_video_bitrate`（如 `200k`），或增加 CRF |
| pyenv 环境 python3 失败 | 使用 `command /usr/bin/python3` 或 `env -i` 指定 PATH |
| 重复触发（heartbeat） | main.py 使用 PID 文件锁保护单实例运行 |
