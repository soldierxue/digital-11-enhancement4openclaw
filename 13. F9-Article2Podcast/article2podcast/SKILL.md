---
name: article2podcast
description: >
  将博客文章（URL 或本地 Markdown）自动转换为多人对话播客音频。
  完整管道：文章解析 → AI 生成双人对话脚本 → 多角色 TTS 语音合成 → 音频拼接后处理 → 元数据生成。
  支持 Edge TTS（免费）、ElevenLabs（高质量）、MiniMax（中文优化）三种 TTS 后端，auto 模式自动选择和降级。
  科技博主风格，主持人+嘉宾对话，中文语言。
  全流程约 8 分钟（含多次 LLM 调用 + 38 段 TTS），建议通过 SubAgent 委托执行。
  Activate when: 用户要求将文章转播客, 文章生成播客, 博客转播客, article to podcast,
  生成播客, 做播客, 文章变播客, markdown to podcast, blog to podcast,
  播客生成, 对话播客, 多人播客, 自动生成播客, article2podcast,
  podcast generation, 文章转音频对话。
---

# Article2Podcast — 博客文章→多人对话播客

将博客文章（3000-7000 字，平均 4500 字）自动转换为 25-35 分钟的双人对话播客音频，
包含主持人和嘉宾两个角色，科技博主风格，自然对话体。

## 执行架构

本 Skill 执行时间约 8 分钟，**建议**通过 SubAgent 委托执行：

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 独立执行 Phase 1-5
                          ├── Phase 1: 文章 → 对话脚本（~60 秒，可能多次 LLM 调用）
                          ├── Phase 2: 多角色 TTS 合成（~5 分钟，38 段）
                          ├── Phase 3: 音频拼接 + 后处理（~30 秒）
                          ├── Phase 4: 元数据生成（~10 秒）
                          ├── Phase 5: S3 上传 + RSS Feed 更新（~15 秒）
                          └── 完成后向用户汇报结果
```

主 Agent 启动 SubAgent 时的 prompt 示例：

```
sessions_spawn:
  prompt: |
    你是 Article2Podcast 播客生成 Agent。
    请读取 ~/.openclaw/skills/article2podcast/SKILL.md 了解执行流程。
    用户要求将以下文章转为播客: <URL 或 .md 路径>
    选项: --host-voice zh-CN-XiaoxiaoNeural --guest-voice zh-CN-YunyangNeural --turns 38
    请执行 main.py 并汇报每个 Phase 的进度。
```

主 Agent 只负责：确认用户意图 → 启动 SubAgent → 等待完成通知。

## 进度汇报规范

SubAgent 在执行过程中**必须定期向用户汇报进度**，不能静默执行到结束。

### 阶段性汇报

| 节点 | 汇报内容 |
|------|----------|
| Phase 1 完成 | 📝 对话脚本已生成：N 轮对话，总字数约 M 字 |
| Phase 2 完成 | 🔊 多角色语音合成完成：总时长 X 分 Y 秒 |
| Phase 3 完成 | 🎙️ 播客音频拼接完成：最终时长 X 分 Y 秒 |
| Phase 4 完成 | 📋 元数据 + Show Notes 已生成（标题、描述、N 个章节、M 条金句） |
| Phase 5 完成 | 📡 已上传 S3 + RSS Feed 更新 + CloudFront 缓存失效 |

### 最终总结

```
🎙️ Article2Podcast 生成总结
━━━━━━━━━━━━━━━━━━━━━━━━
标题：<播客标题>
副标题：<副标题>
对话轮数：<N> 轮
角色：主持人 (<host_voice>) + 嘉宾 (<guest_voice>)
TTS 后端：<edge-tts / elevenlabs / minimax / mixed>
时长：<X 分 Y 秒>
章节：<N> 个
金句：<M> 条
文件大小：<X> MB
输出路径：~/.openclaw/workspace/output/<slug>-podcast.mp3
Show Notes：~/.openclaw/workspace/output/<slug>-show-notes.md
元数据：~/.openclaw/workspace/output/<slug>-metadata.json
状态：✅ 播客已就绪
━━━━━━━━━━━━━━━━━━━━━━━━
```

## 前置条件

```bash
# FFmpeg
ffmpeg -version 2>/dev/null && echo "✓ FFmpeg" || echo "✗ FFmpeg 未安装"

# Python 依赖
python3 -c "import edge_tts; import litellm" 2>/dev/null && echo "✓ Python deps" || echo "✗ pip install edge-tts litellm"
```

## 执行流程

### Phase 1: 文章 → 对话脚本

```bash
python3 scripts/generate_script.py <article_path_or_url> \
    --output podcast-script.json \
    --turns 20 \
    --model anthropic/claude-sonnet-4-20250514
```

输入：文章 URL 或 .md 文件
输出：`podcast-script.json`（对话脚本 JSON 数组）

脚本格式：
```json
[
  {"turn": 1, "role": "host", "text": "...", "emotion": "cheerful"},
  {"turn": 2, "role": "guest", "text": "...", "emotion": "thoughtful"}
]
```

### Phase 2: 多角色 TTS 合成

```bash
python3 scripts/generate_podcast_audio.py podcast-script.json \
    --output-dir audio/ \
    --timing-output timing.json \
    --host-voice zh-CN-XiaoxiaoNeural \
    --guest-voice zh-CN-YunyangNeural
```

输入：`podcast-script.json`
输出：`audio/turn-{NN}-{role}.mp3` + `timing.json`

### Phase 3: 音频拼接 + 后处理

```bash
python3 scripts/assemble_podcast.py timing.json \
    --output podcast.mp3 \
    --gap-ms 400 \
    --normalize
```

输入：`timing.json` + 音频片段
输出：`podcast.mp3`（完整播客音频）

功能：
- 按对话顺序拼接音频片段
- 角色切换间插入静音间隔（默认 400ms）
- 可选背景音乐混入
- 响度标准化（-16 LUFS，播客行业标准）

### Phase 4: 元数据 + Show Notes 生成

```bash
python3 scripts/generate_metadata.py podcast-script.json \
    --timing timing.json \
    --article <article_path> \
    --article-url <article_url> \
    --output metadata.json \
    --show-notes-output show-notes.md
```

输入：对话脚本 + timing + 原文
输出：
- `metadata.json`（标题、副标题、描述、章节标记、金句摘录、Show Notes 分段）
- `show-notes.md`（面向听众的 Markdown 格式节目说明）

Show Notes 包含：
- 节目简介（150-250字）
- 时间线（带时间戳的章节导航）
- 主题段落 + 要点（引用对话时间戳）
- 金句摘录（5-8句精华语录）
- 标签和相关链接

## Phase 5: S3 上传 + RSS Feed 更新

播客生成完成后，需要上传到 S3 并更新 RSS feed，供小宇宙等播客平台抓取。

### Step 1: 上传 MP3 到 S3

```bash
aws s3 cp ~/.openclaw/workspace/output/<slug>-podcast.mp3 \
  s3://claw2026/podcast/episodes/<slug>.mp3
```

### Step 2: 生成 Show Notes HTML 并上传

```bash
python3 -c "
import sys
sys.path.insert(0, '/home/ubuntu/.openclaw/skills/weixin-publisher')
from md2weixin import md_to_weixin_html
md = open('$HOME/.openclaw/workspace/output/<slug>-show-notes.md', encoding='utf-8').read()
html = md_to_weixin_html(md)
with open('/tmp/<slug>-show-notes.html', 'w', encoding='utf-8') as f:
    f.write(html)
"
aws s3 cp /tmp/<slug>-show-notes.html \
  s3://claw2026/podcast/episodes/<slug>-show-notes.html \
  --content-type "text/html; charset=utf-8"
```

### Step 3: 更新 RSS Feed

使用 `scripts/update_rss_feed.py` 脚本自动更新 RSS feed：

```bash
# 单集更新
python3 scripts/update_rss_feed.py --slug <slug> --upload --invalidate

# 批量更新（JSON 文件包含 slug 列表）
python3 scripts/update_rss_feed.py --batch slugs.json --upload --invalidate

# 仅预览不修改
python3 scripts/update_rss_feed.py --slug <slug> --dry-run
```

脚本自动完成：
1. 从 `metadata.json` 读取标题、**完整描述**（150-250字节目简介）、时长
2. 从 show-notes HTML 生成 `<content:encoded>`（小宇宙等平台显示的详细 Show Notes）
3. 从 MP3 文件获取 `enclosure length`
4. 去重检查（已存在的 slug 跳过）
5. 新 item 插入 feed 最前面（最新在前）
6. 上传 S3 + 失效 CloudFront 缓存

### ⚠️ RSS Item 必填字段（血泪教训）

| 字段 | 数据来源 | 说明 |
|------|---------|------|
| `<title>` | metadata.title | 播客标题 |
| `<description>` | **metadata.description** | 完整节目简介（150-250字），**不是 subtitle** |
| `<content:encoded>` | show-notes HTML | 完整 Show Notes（含时间线、知识点、金句），**不可省略** |
| `<enclosure>` | MP3 文件 | url + length + type="audio/mpeg" |
| `<guid>` | slug | 唯一标识 |
| `<pubDate>` | 日期 | RFC 2822 格式 |
| `<itunes:duration>` | metadata.duration_formatted | 时长 |

**错误案例（3/28）**：`<description>` 误用 `subtitle`（一句话）而非 `description`（完整简介），
且缺少 `<content:encoded>`，导致小宇宙只显示一句话的节目说明。

### 播客基础设施

| 组件 | 值 |
|------|-----|
| S3 Bucket | `claw2026` |
| S3 路径 | `podcast/episodes/<slug>.mp3` |
| RSS Feed | `s3://claw2026/podcast/feed.xml` |
| CDN | `https://dwnvpa8lfeaci.cloudfront.net/podcast/` |
| CloudFront 分发 ID | `E3KM4YV1GLQRGD` |
| Cache-Control | `max-age=300,s-maxage=300`（5 分钟） |

## 配置文件

`config.json` 关键字段：

```json
{
  "default_host_voice": "zh-CN-XiaoxiaoNeural",
  "default_guest_voice": "zh-CN-YunyangNeural",
  "default_turns": 38,
  "default_tts_backend": "auto",
  "gap_ms": 400,
  "normalize_lufs": -16,
  "host_name": "十一",
  "guest_name": "薛以致用",
  "podcast_name": "军见数科·科技播客",
  "opening_line": "大家好，欢迎收听军见数科科技播客，我是主持人十一。今天请到的嘉宾是我们的老朋友薛以致用。",
  "ai_model": "anthropic/claude-sonnet-4-20250514",
  "output_dir": "~/.openclaw/workspace/output"
}
```

## TTS 音色策略

默认使用 `auto` 模式（`--tts-backend auto`），自动为主持人和嘉宾选择最优音色，并在后端不可用时自动降级。

### 主持人（host）— 随机选择

每次生成播客时，从以下两个选项中**随机选择**一个作为主持人音色：

| 选项 | 后端 | voice_id | 说明 |
|------|------|----------|------|
| 男声 | MiniMax | `male-qn-jingying` | MiniMax 男声精英 |
| 女声 | ElevenLabs | `APSIkVZudNbPAwyPoeVO` | ElevenLabs 女声 |

**降级链路**：选中后端不可用 → 尝试另一个后端 → edge-tts（男声 `zh-CN-YunyangNeural` / 女声 `zh-CN-XiaoxiaoNeural`）

### 嘉宾（guest）— 固定优先级

| 优先级 | 后端 | voice_id | 说明 |
|--------|------|----------|------|
| 首选 | MiniMax | `jason_podcast_voice_001` | 薛以致用克隆音色 |
| 降级 | ElevenLabs | `Vki3eB7XF9nxH50xK1s9` | ElevenLabs 薛以致用 |
| 最终降级 | edge-tts | `zh-CN-YunyangNeural` | Edge 男声 |

### 可用性检测

- 启动时通过检查 `credentials.json` 中的 API key 是否存在且非空来判断后端可用性
- MiniMax 需要 `minimax_api_key` 和 `minimax_group_id` 两个字段
- ElevenLabs 需要 `elevenlabs_api_key`
- edge-tts 始终可用（免费，无需 API key）

### 运行时降级

即使启动时检测后端可用，实际 API 调用仍可能失败。此时会：
1. 记录错误日志
2. 删除该 turn 的缓存文件
3. 自动降级到下一个后端重试
4. 最终降级到 edge-tts 保证不中断

### credentials.json 配置

```json
{
  "elevenlabs_api_key": "sk_your_key_here",
  "minimax_api_key": "your_minimax_key",
  "minimax_group_id": "your_group_id"
}
```

### 向后兼容

旧的 `--tts-backend edge-tts` / `--tts-backend elevenlabs` / `--tts-backend minimax` / `--tts-backend mixed` 参数仍然有效，行为不变。只有 `auto` 模式才启用随机主持人 + 嘉宾优先级逻辑。

## 使用方法

```bash
# 基本用法（默认 auto 模式：随机主持人 + 嘉宾优先级降级）
python3 main.py https://example.com/blog-post

# 本地 Markdown
python3 main.py ~/articles/my-article.md

# 自定义音色（使用 edge-tts 后端）
python3 main.py article.md --tts-backend edge-tts --host-voice zh-CN-XiaoxiaoNeural --guest-voice zh-CN-YunyangNeural

# 使用 MiniMax TTS（所有角色）
python3 main.py article.md --tts-backend minimax

# 使用 ElevenLabs TTS
python3 main.py article.md --tts-backend elevenlabs

# 添加背景音乐
python3 main.py article.md --bgm assets/bgm/tech-ambient.mp3 --bgm-volume 0.08
```

## 错误处理

| 错误 | 处理方式 |
|------|----------|
| 文章加载失败 | 检查 URL 可达性或文件路径 |
| LLM 调用失败 | 重试 1 次，仍失败则报错退出 |
| TTS 单段失败 | 跳过该段，在最终报告中标注 |
| FFmpeg 不可用 | 直接拼接 MP3（不做后处理） |
| 音频时长异常（<1min 或 >30min） | 警告用户，建议调整 --turns |
