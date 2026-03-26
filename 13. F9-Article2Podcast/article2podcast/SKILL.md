---
name: article2podcast
description: >
  将博客文章（URL 或本地 Markdown）自动转换为多人对话播客音频。
  完整管道：文章解析 → AI 生成双人对话脚本 → 多角色 TTS 语音合成 → 音频拼接后处理 → 元数据生成。
  支持 Edge TTS（免费）、MiniMax（高质量）、VibeVoice（本地 GPU）三种 TTS 后端。
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
                    └── SubAgent 独立执行 Phase 1-4
                          ├── Phase 1: 文章 → 对话脚本（~60 秒，可能多次 LLM 调用）
                          ├── Phase 2: 多角色 TTS 合成（~5 分钟，38 段）
                          ├── Phase 3: 音频拼接 + 后处理（~30 秒）
                          ├── Phase 4: 元数据生成（~10 秒）
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
| Phase 4 完成 | 📋 元数据已生成（标题、描述、章节标记） |

### 最终总结

```
🎙️ Article2Podcast 生成总结
━━━━━━━━━━━━━━━━━━━━━━━━
标题：<播客标题>
对话轮数：<N> 轮
角色：主持人 (<host_voice>) + 嘉宾 (<guest_voice>)
TTS 后端：<edge-tts / minimax / vibevoice>
时长：<X 分 Y 秒>
文件大小：<X> MB
输出路径：~/.openclaw/workspace/output/<slug>-podcast.mp3
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

### Phase 4: 元数据生成

```bash
python3 scripts/generate_metadata.py podcast-script.json \
    --timing timing.json \
    --article <article_path> \
    --output metadata.json
```

输入：对话脚本 + timing + 原文
输出：`metadata.json`（标题、描述、章节标记）

## 配置文件

`config.json` 关键字段：

```json
{
  "default_host_voice": "zh-CN-XiaoxiaoNeural",
  "default_guest_voice": "zh-CN-YunyangNeural",
  "default_turns": 38,
  "default_tts_backend": "edge-tts",
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

## 使用方法

```bash
# 基本用法
python3 main.py https://example.com/blog-post

# 本地 Markdown
python3 main.py ~/articles/my-article.md

# 自定义音色
python3 main.py article.md --host-voice zh-CN-XiaoxiaoNeural --guest-voice zh-CN-YunyangNeural

# 使用 MiniMax TTS
python3 main.py article.md --tts-backend minimax

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
