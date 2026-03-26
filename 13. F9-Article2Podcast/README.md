# F9-Article2Podcast — 博客文章自动转播客

> 从博客文章（URL 或本地 Markdown），自动生成多人对话播客音频。
> 至少两位角色（主持人 + 嘉宾），科技博主风格，中文语言。
> 完整管道：文章解析 → AI 生成对话脚本 → 多角色 TTS 语音合成 → 音频拼接 → 元数据生成。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 执行方式：SubAgent 委托

本 Skill 执行时间约 8 分钟（Phase 1 LLM 生成 ~60s + Phase 2 TTS 38 段 ~5min + Phase 3 拼接 ~30s + Phase 4 元数据 ~10s），**必须通过 SubAgent 委托执行**，避免阻塞主 Agent。

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行完整流程
                          ├── Phase 1: 文章 → 对话脚本（~60 秒，可能多次 LLM 调用）
                          ├── Phase 2: 多角色 TTS 合成（~5 分钟，38 段）
                          ├── Phase 3: 音频拼接 + 响度标准化（~30 秒）
                          ├── Phase 4: 元数据生成（~10 秒）
                          └── 完成后向用户汇报结果
```

启动 SubAgent 的 prompt：

```
sessions_spawn:
  prompt: |
    你是 Article2Podcast 播客生成 Agent。
    请读取 skills/article2podcast/SKILL.md 了解你的职责和执行流程。
    用户要求将以下文章转为播客: <URL 或 .md 路径>
    选项: --host-voice zh-CN-XiaoxiaoNeural --guest-voice zh-CN-YunyangNeural --turns 38
    开始执行。
```

### 主 Agent 职责

1. 确认用户意图（哪篇文章、对话轮数、是否需要背景音乐）
2. 启动 SubAgent（sessions_spawn）
3. 等待 SubAgent 完成，向用户汇报结果

**不要**在主 Agent 中直接运行 `main.py`，那会阻塞 8+ 分钟。

### 进度汇报规范

SubAgent 在执行过程中**必须定期向用户汇报进度**，不能静默执行到结束。

阶段性汇报节点：

| 节点 | 汇报内容 |
|------|----------|
| Phase 1 完成 | 📝 对话脚本已生成：N 轮对话（host:X, guest:Y），总字数约 M 字 |
| Phase 2 完成 | 🔊 多角色语音合成完成：总时长 X 分 Y 秒 |
| Phase 3 完成 | 🎙️ 播客音频拼接完成：最终时长 X 分 Y 秒，文件大小 N MB |
| Phase 4 完成 | 📋 元数据已生成（标题、描述、章节标记） |

### 前置检查（启动前快速验证）

```bash
# FFmpeg
ffmpeg -version 2>/dev/null && echo "✓ FFmpeg" || echo "✗ FFmpeg 未安装"

# Python 依赖
python3 -c "import edge_tts; import litellm" 2>/dev/null && echo "✓ Python deps" || echo "✗ pip install edge-tts litellm"
```

---

## 设计思路

### 1. 为什么做 Article2Podcast？

Article2Video（F6）已经实现了"文章→视频"的管道，但播客（纯音频）有独特价值：

| 维度 | 视频 | 播客 |
|------|------|------|
| 制作时间 | ~40 分钟（含渲染） | ~5 分钟（纯音频） |
| 消费场景 | 需要看屏幕 | 通勤、运动、做家务 |
| 文件大小 | ~20MB | ~5-10MB |
| 分发平台 | B站、视频号 | 小宇宙、Apple Podcasts、喜马拉雅 |
| 内容深度 | 3-5 分钟精华 | 25-35 分钟深度对话 |

播客的核心差异：**对话体**。不是一个人念稿，而是两个人讨论，更有趣、更易消化。

### 2. 参考方案调研

| 方案 | 特点 | 适用性 |
|------|------|--------|
| [PodLM](https://podlm.ai) | SaaS 产品，URL/文本→播客，多语言 | 商业产品，不可本地化 |
| [MiniMax Speech](https://platform.minimax.io) | 100+ 系统音色，支持中文，异步长文本 TTS，API 调用 | ✅ 高质量中文 TTS，适合做 TTS 后端 |
| [Microsoft VibeVoice](https://github.com/microsoft/VibeVoice) | 开源，90 分钟长对话，4 人多角色，支持中文 | ✅ 本地部署，需 GPU（1.5B 模型需 8GB VRAM） |
| [Edge TTS](https://github.com/rany2/edge-tts) | 免费，多音色，逐词时间戳，无需 API Key | ✅ 零成本，已在 F6 验证，适合快速方案 |
| [FireRedTTS-2](https://arxiv.org/abs/2509.02020) | 长对话流式 TTS，多角色切换 | 研究阶段，暂不可用 |

### 3. 技术方案选型

采用**分层架构**，支持多种 TTS 后端，默认使用 Edge TTS（零成本、已验证）：

```
┌─────────────────────────────────────────────────────┐
│                  Article2Podcast                     │
├─────────────────────────────────────────────────────┤
│  Phase 1: 文章 → 对话脚本（LLM）                      │
│  Phase 2: 对话脚本 → 多角色音频（TTS）                  │
│  Phase 3: 音频片段 → 完整播客（FFmpeg）                 │
│  Phase 4: 元数据生成（标题/描述/章节标记）               │
├─────────────────────────────────────────────────────┤
│  TTS 后端（可切换）：                                  │
│  ├── edge-tts（默认，免费，已验证）                     │
│  ├── minimax（高质量，需 API Key）                     │
│  └── vibevoice（本地 GPU，最高质量）                    │
└─────────────────────────────────────────────────────┘
```

### 4. 对话脚本设计

核心创新点：用 LLM 将单人叙述文章改写为**双人对话**。

角色设定：
- **主持人 十一（Host，女）**：引导话题、提问、总结，语气温暖亲和、轻松专业
- **嘉宾 薛以致用（Guest，男）**：深入解读、举例说明、分享观点，语气沉稳有见地

对话风格参考科技播客（如"硬地骇客"、"津津乐道"、"What's Next"）：
- 开场寒暄 → 主题引入 → 逐层深入 → 互动讨论 → 总结展望
- 自然的语气词（"对"、"没错"、"这个很有意思"）
- 适当的追问和补充
- 数据和案例穿插

### 5. 音色方案

Edge TTS 中文音色推荐（默认方案）：

| 角色 | 音色 | 说明 |
|------|------|------|
| 主持人（女）默认 | `zh-CN-XiaoxiaoNeural` | 温暖女声，亲和力强，适合主持引导 |
| 嘉宾（男）默认 | `zh-CN-YunyangNeural` | 成熟男声，沉稳有深度，适合专家解读 |
| 主持人（男）备选 | `zh-CN-YunxiNeural` | 年轻男声，清晰自然 |
| 嘉宾（女）备选 | `zh-CN-XiaoyiNeural` | 年轻女声，活泼有活力 |

MiniMax 方案（高质量备选）：
- 支持 100+ 系统音色 + 自定义克隆音色
- 更自然的语调和情感表达
- 需要 API Key，按字符计费

VibeVoice 方案（最高质量）：
- 本地部署，支持 4 人对话
- 自然的轮流说话和语气变化
- 需要 GPU（1.5B 模型需 8GB VRAM）

### 6. 管道架构

```
输入: 文章 URL 或 .md 文件
  │
  ▼
Phase 1: 生成对话脚本 (~60s, 可能需多次 LLM 调用)
  ├── LLM 分析文章结构和要点
  ├── 生成 Host/Guest 对话（35-40 轮，~6500 字）
  ├── 若单次生成不足 25 分钟，自动追加深度讨论轮次
  └── 输出 podcast-script.json
  │
  ▼
Phase 2: 多角色 TTS 合成 (~5min)
  ├── 按角色分配音色
  ├── 逐段生成音频 + 时间戳
  └── 输出 audio/turn-{NN}-{role}.mp3
  │
  ▼
Phase 3: 音频拼接 + 后处理 (~30s)
  ├── 按对话顺序拼接
  ├── 插入角色切换间隔（300ms 静音）
  ├── 可选：添加背景音乐（低音量）
  ├── 响度标准化（-16 LUFS，播客标准）
  └── 输出 podcast.mp3
  │
  ▼
Phase 4: 元数据生成 (~10s)
  ├── AI 生成播客标题、描述
  ├── 生成章节标记（Podcast Chapters）
  └── 输出 metadata.json
  │
  ▼
输出: ~/.openclaw/workspace/output/{slug}-podcast.mp3
      ~/.openclaw/workspace/output/{slug}-metadata.json
```

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | 运行环境 |
| FFmpeg | 音频拼接与后处理，`brew install ffmpeg`（macOS） |
| edge-tts | 默认 TTS 后端，`pip install edge-tts` |
| litellm | LLM 调用（对话脚本生成），`pip install litellm` |
| AWS 凭证 | `~/.aws/credentials`（如使用 Bedrock 模型） |

可选依赖：
- `minimax` SDK — 使用 MiniMax TTS 后端时需要
- `vibevoice` — 使用 VibeVoice 本地 TTS 时需要（需 GPU）

---

## 使用方法

```bash
# 基本用法（从 URL）
python3 main.py https://example.com/blog-post

# 从本地 Markdown
python3 main.py ~/articles/my-article.md

# 指定角色音色
python3 main.py article.md --host-voice zh-CN-XiaoxiaoNeural --guest-voice zh-CN-YunyangNeural

# 使用 MiniMax TTS（更高质量）
python3 main.py article.md --tts-backend minimax

# 指定对话轮数
python3 main.py article.md --turns 20

# 添加背景音乐
python3 main.py article.md --bgm assets/bgm/tech-ambient.mp3 --bgm-volume 0.08
```

---

## 项目结构

```
13. F9-Article2Podcast/
├── README.md                          ← 本文件
└── article2podcast/
    ├── SKILL.md                       ← OpenClaw Skill 定义
    ├── main.py                        ← 管道编排入口
    ├── config.json                    ← 默认配置
    ├── requirements.txt               ← Python 依赖
    ├── scripts/
    │   ├── generate_script.py         ← Phase 1: 文章→对话脚本
    │   ├── generate_podcast_audio.py  ← Phase 2: 对话脚本→多角色音频
    │   ├── assemble_podcast.py        ← Phase 3: 音频拼接+后处理
    │   └── generate_metadata.py       ← Phase 4: 元数据生成
    └── assets/
        └── bgm/                       ← 背景音乐素材（可选）
            └── .gitkeep
```

---

## 对话脚本格式（podcast-script.json）

```json
[
  {
    "turn": 1,
    "role": "host",
    "text": "大家好，欢迎收听本期科技播客。今天我们要聊一个很有意思的话题...",
    "emotion": "cheerful"
  },
  {
    "turn": 2,
    "role": "guest",
    "text": "对，这个话题我最近也一直在关注。其实核心问题在于...",
    "emotion": "thoughtful"
  }
]
```

---

## 与 F6 Article2Video 的关系

Article2Podcast 复用了 F6 的部分经验：
- 文章加载逻辑（URL / 本地 Markdown）
- Edge TTS 调用模式（已验证的音频生成方案）
- Phase 化管道编排 + 幂等跳过
- SubAgent 委托执行模式

但有关键差异：
- F6 是**单人独白** → F9 是**多人对话**
- F6 需要视觉素材 + 视频渲染 → F9 纯音频，更轻量
- F6 ~40 分钟 → F9 ~5 分钟
- F9 新增对话脚本生成、角色音色分配、响度标准化等环节

---

## 后续扩展

- [ ] 支持 3+ 人圆桌讨论模式
- [ ] 接入播客分发平台（小宇宙、Apple Podcasts RSS）
- [ ] 支持自定义角色人设（通过 config 配置）
- [ ] 支持插入音效（笑声、掌声等）
- [ ] 生成播客封面图（复用 Nova Canvas）
- [ ] 与 F7/F8 联动，生成播客视频版（静态封面 + 音频波形）
