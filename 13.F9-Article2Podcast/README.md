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
| [ElevenLabs](https://elevenlabs.io) | Voice Cloning，自定义音色，多语言 TTS，API 调用 | ✅ 嘉宾音色推荐方案，支持克隆真人音色 |
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
│  TTS 后端（Smart 模式自动选择）：                       │
│  ├── minimax（MiniMax T2A，高质量中文，需 API Key）     │
│  ├── elevenlabs（自定义克隆音色，需 API Key）           │
│  └── edge-tts（免费兜底方案）                           │
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

### 5. 音色方案 — Smart 模式（默认）

采用 **Smart 模式**，自动选择最优音色组合，支持多 TTS 后端混合使用：

**主持人（Host）— 随机选择，增加节目新鲜感：**

| 候选 | TTS 后端 | Voice ID | 说明 |
|------|----------|----------|------|
| 男主持 | MiniMax | `male-qn-jingying` | 精英青年男声，专业沉稳 |
| 女主持 | ElevenLabs | `APSIkVZudNbPAwyPoeVO` | 自然女声，亲和力强 |

每次生成播客时随机选择其中一个，让节目风格更多样化。

**嘉宾 薛以致用（Guest）— 优先级 fallback 链：**

| 优先级 | TTS 后端 | Voice ID | 说明 |
|--------|----------|----------|------|
| 1（首选） | MiniMax | `jason_podcast_voice_001` | MiniMax 定制音色 |
| 2（备选） | ElevenLabs | `Vki3eB7XF9nxH50xK1s9` | ElevenLabs 克隆音色 jasonsh |

启动时自动探测首选音色是否可用，不可用则自动降级到备选。

**Edge TTS 中文音色（兜底方案）：**

| 角色 | 音色 | 说明 |
|------|------|------|
| 主持人（女） | `zh-CN-XiaoxiaoNeural` | 温暖女声，免费 |
| 嘉宾（男） | `zh-CN-YunyangNeural` | 成熟男声，免费 |

### 5.1 TTS 后端选择

`config.json` 中 `default_tts_backend` 支持以下模式：

| 模式 | 说明 |
|------|------|
| `smart`（默认） | 主持人随机选择 + 嘉宾 fallback 链，自动探测可用性 |
| `mixed` | 主持人 Edge TTS + 嘉宾 ElevenLabs（固定组合） |
| `elevenlabs` | 全部使用 ElevenLabs |
| `minimax` | 全部使用 MiniMax |
| `edge-tts` | 全部使用 Edge TTS（免费，零配置） |

### 5.2 敏感信息管理

API Key 等敏感信息**不保存在 `config.json` 中**，而是独立存放在 `credentials.json`：

```bash
# 从模板创建凭证文件
cp credentials.json.example credentials.json

# 编辑填入你的 API Key
vim credentials.json
```

`credentials.json` 格式：
```json
{
  "elevenlabs_api_key": "your-actual-api-key-here",
  "minimax_api_key": "your-minimax-api-key",
  "minimax_group_id": "your-minimax-group-id"
}
```

`credentials.json` 已在 `.gitignore` 中排除，不会被提交到 Git 仓库。

### 5.3 MiniMax API 域名选择

MiniMax 在不同地区/不同平台签发的 API Key**并不可跨域名使用**，每把 Key 只对某一个域名有效。选错域名会得到 `status_code: 2049 invalid api key`。在 `config.json` 中通过 `minimax_api_base`（TTS 用）和 `minimax_anthropic_api_base`（LLM Anthropic 兼容接口用）分别指定。

| 域名 | 适用场景 | 备注 |
|------|----------|------|
| `https://api.minimaxi.com/v1` | 中文开放平台 [platform.minimaxi.com](https://platform.minimaxi.com) 签发的 Key（**默认值**） | 支持 TTS / voice clone / LLM 全量能力 |
| `https://api.minimax.io/v1` | 国际站 [platform.minimax.io](https://platform.minimax.io) 签发的 Key | 官方英文文档示例使用此域名 |
| `https://api.minimaxi.chat/v1` | 国际备用域名 | SillyTavern 等第三方文档列为国际服务器之一 |
| `https://api.minimax.chat/v1` | 中国大陆专用域名 | ⚠️ **不支持 voice cloning**，功能受限 |

选择建议：

- **你的 Key 从哪个平台申请的？** 从 [platform.minimaxi.com](https://platform.minimaxi.com) 申请的用 `api.minimaxi.com`（默认），从 [platform.minimax.io](https://platform.minimax.io) 申请的改成 `api.minimax.io`。
- **不确定？** 用下面的 curl 片段分别 ping 两个域名，哪个返回 `status_code: 0 success` 就用哪个。
- **LLM Anthropic 兼容接口**（`llm_client.py` 里 `minimax/<model>` 前缀）：由 `minimax_anthropic_api_base` 配置，默认 `https://api.minimaxi.com`，路径前缀是 `/anthropic/v1/messages`，和 TTS 的 `/v1/t2a_v2` 用同一 host 不同路径。

**Key-域名匹配快速验证：**

```bash
# 替换 $MINIMAX_API_KEY 和 $GROUP_ID 后依次尝试两个域名
for BASE in https://api.minimaxi.com/v1 https://api.minimax.io/v1; do
  echo "== $BASE =="
  curl -s -X POST "$BASE/t2a_v2?GroupId=$GROUP_ID" \
    -H "Authorization: Bearer $MINIMAX_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"speech-2.8-hd","text":"测试","voice_setting":{"voice_id":"male-qn-jingying"},"audio_setting":{"sample_rate":32000,"format":"mp3"}}' \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("base_resp"))'
done
```

返回 `{'status_code': 0, 'status_msg': 'success'}` 的就是你 Key 对应的域名。

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
- `requests` — 使用 ElevenLabs / MiniMax TTS 后端时需要（`pip install requests`）
- `mutagen` — 无 FFmpeg 时用于获取音频时长（`pip install mutagen`）
- ElevenLabs API Key — 配置在 `credentials.json` 中
- MiniMax API Key + Group ID — 配置在 `credentials.json` 中

---

## 使用方法

```bash
# 基本用法（Smart 模式，自动选择最优音色组合）
python3 main.py https://example.com/blog-post

# 从本地 Markdown
python3 main.py ~/articles/my-article.md

# 强制使用 Edge TTS（免费，零配置）
python3 main.py article.md --tts-backend edge-tts

# 强制使用 ElevenLabs
python3 main.py article.md --tts-backend elevenlabs --guest-voice Vki3eB7XF9nxH50xK1s9

# 强制使用 MiniMax
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
    ├── config.json                    ← 默认配置（不含敏感信息）
    ├── credentials.json.example       ← 凭证模板（API Key 等）
    ├── credentials.json               ← 实际凭证（.gitignore 排除）
    ├── requirements.txt               ← Python 依赖
    ├── scripts/
    │   ├── generate_script.py         ← Phase 1: 文章→对话脚本
    │   ├── generate_podcast_audio.py  ← Phase 2: 对话脚本→多角色音频（支持 Edge TTS / ElevenLabs）
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
