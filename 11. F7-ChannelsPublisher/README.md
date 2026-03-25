# F7-ChannelsPublisher — 微信视频号自动发布

> 将 F6 Article2Video 生成的短视频，通过浏览器自动化（CDP）发布到微信视频号创作者中心。
> 支持自动上传视频、AI 生成标题/描述/标签、封面选择、保存草稿。

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | 运行环境 |
| Chrome/Chromium | 已启用 Remote Debugging（参见 `2. Chrome_DevTool/README.md`） |
| 微信视频号 | 已开通，已在浏览器中登录 [channels.weixin.qq.com](https://channels.weixin.qq.com) |
| Kiro CLI | AI 文本智能（标题/描述/标签生成） |

Python 依赖：

```
websocket-client
```

---

## 为什么用 CDP 而不是 API？

微信视频号（Channels）截至 2026 年 3 月**没有开放第三方上传/发布 API**。
与公众号不同（有 `cgi-bin/draft/add` 等完整 API），视频号只能通过：

1. 微信 App 内发布
2. 视频号创作者中心网页版（channels.weixin.qq.com）

因此我们采用 CDP（Chrome DevTools Protocol）浏览器自动化方案，
复用项目已有的 CDP 基础设施（`auto_session.py` 模式、Chrome DevTool 配置）。

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 执行方式：SubAgent 委托

本 Skill 涉及浏览器自动化操作，执行时间约 2-5 分钟，**建议通过 SubAgent 委托执行**。

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行
                          ├── Phase 1: 连接视频号创作者中心（CDP）
                          ├── Phase 2: 上传视频文件
                          ├── Phase 3: AI 生成元数据 + 填写表单
                          ├── Phase 4: 保存草稿
                          └── 完成后向用户汇报结果
```

### 前置检查

```bash
# Chrome Remote Debugging
curl -s http://127.0.0.1:9222/json/version 2>/dev/null && echo "✓ CDP" || echo "✗ CDP 未就绪"

# websocket-client
python3 -c "import websocket" 2>/dev/null && echo "✓ websocket-client" || echo "✗ pip install websocket-client"

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
F7 ChannelsPublisher
  ├── Phase 1: CDP 连接
  │     ├── 查找 channels.weixin.qq.com 标签页
  │     └── 如未打开 → 导航到创作者中心
  │
  ├── Phase 2: 上传视频
  │     ├── 点击「发表视频」
  │     ├── 通过 input[type=file] 注入视频文件路径
  │     └── 等待上传完成（轮询进度）
  │
  ├── Phase 3: 填写元数据
  │     ├── AI 生成标题（≤30字，Kiro CLI）
  │     ├── AI 生成描述（≤1000字，含 #话题标签）
  │     ├── 选择封面（上传自定义封面 或 使用视频截图）
  │     └── 设置分类、位置等可选项
  │
  └── Phase 4: 保存草稿 / 发布
        ├── 默认: 保存草稿（用户到创作者中心确认后手动发布）
        └── 可选: 直接发布（--publish 参数）
```

---

## 二、模块说明

```
channels-publisher/
├── SKILL.md                    # Agent 执行指南
├── main.py                     # 入口脚本
├── cdp_client.py               # CDP 客户端（复用 auto_session.py 模式）
├── channels_uploader.py        # 视频号上传自动化核心逻辑
├── metadata_generator.py       # AI 生成标题/描述/标签
├── video_cover.py              # 智能视频封面截取（与 F8 共享）
└── config.json                 # 配置
```

| 模块 | 职责 |
|------|------|
| `cdp_client.py` | CDP WebSocket 客户端，查找/连接标签页，执行 JS |
| `channels_uploader.py` | 视频号创作者中心页面自动化（上传、填表、提交） |
| `metadata_generator.py` | 调用 Kiro CLI 生成视频标题、描述、话题标签 |
| `main.py` | 流程编排入口 |

---

## 三、使用方法

```bash
# 基本用法：上传视频并保存为草稿
python3 main.py /path/to/video.mp4

# 指定原始文章（用于 AI 生成更好的标题/描述）
python3 main.py /path/to/video.mp4 --article /path/to/article.md

# 自定义封面
python3 main.py /path/to/video.mp4 --cover /path/to/cover.jpg

# 指定 CDP 端口
python3 main.py /path/to/video.mp4 --cdp-url http://127.0.0.1:18800

# 直接发布（不仅保存草稿）
python3 main.py /path/to/video.mp4 --publish
```

### CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `video` | 视频文件路径（必填） | — |
| `--article` | 原始文章路径（用于 AI 生成元数据） | — |
| `--cover` | 自定义封面图路径（留空则智能截取） | 智能截取 |
| `--no-auto-cover` | 禁用智能封面截取 | `false` |
| `--title` | 手动指定标题（跳过 AI 生成） | AI 生成 |
| `--desc` | 手动指定描述 | AI 生成 |
| `--cdp-url` | CDP 地址 | `http://127.0.0.1:9222` |
| `--publish` | 直接发布（默认仅保存草稿） | `false` |

---

## 四、关键实现细节

### 4.1 智能封面截取（video_cover.py）

当用户未指定 `--cover` 时，自动从视频中智能截取最佳封面：

```
视频文件
  │
  ├── Step 1: 跳过片头(10%)片尾(8%)，在正文段提取 8 个候选帧
  │     ├── 优先方案: ffmpeg scene 滤镜检测场景变化点
  │     └── 回退方案: 均匀时间采样
  │
  ├── Step 2: AI 评分选择最佳帧
  │     ├── Kiro CLI 评分（信息密度、视觉吸引力）
  │     └── 回退: 启发式选择（文件最大 = 内容最丰富）
  │
  └── Step 3: ffmpeg 裁剪到目标比例
        ├── 视频号: 16:9 或 1:1
        └── B站: 16:10
```

独立使用：

```bash
python3 video_cover.py video.mp4 --ratio 16:9 --title "文章标题" -o cover.jpg
```

### 4.2 视频文件上传

视频号创作者中心使用 `<input type="file">` 元素接收视频文件。
通过 CDP 的 `DOM.setFileInputFiles` 方法直接注入文件路径，无需模拟拖拽：

```python
# 1. 找到 file input 元素
node_id = cdp.send("DOM.querySelector", {
    "nodeId": root_node_id,
    "selector": "input[type='file'][accept*='video']"
})

# 2. 注入文件路径
cdp.send("DOM.setFileInputFiles", {
    "nodeId": node_id,
    "files": ["/absolute/path/to/video.mp4"]
})
```

### 4.2 等待上传完成

上传进度通过轮询页面元素判断：

```python
# 轮询上传进度
while True:
    progress = cdp.evaluate("""
        (() => {
            // 查找进度条或上传完成标识
            const progress = document.querySelector('.upload-progress');
            const done = document.querySelector('.upload-success, .upload-done');
            if (done) return JSON.stringify({status: 'done'});
            if (progress) return JSON.stringify({
                status: 'uploading',
                percent: progress.textContent
            });
            return JSON.stringify({status: 'waiting'});
        })()
    """)
    if progress['status'] == 'done':
        break
    time.sleep(2)
```

### 4.3 AI 元数据生成

复用 Kiro CLI 模式（与 F4 cover_generator.py 一致）：

```python
# 生成视频标题（≤30字）
kiro-cli chat --no-interactive --trust-all-tools \
  "请为以下文章生成一个适合微信视频号的标题，要求：
   1. 不超过30个中文字
   2. 有吸引力，能引发好奇心
   3. 适合短视频平台风格
   只输出标题文本：\n\n{article_content}"

# 生成描述 + 话题标签
kiro-cli chat --no-interactive --trust-all-tools \
  "请为以下文章生成微信视频号的描述文案，要求：
   1. 200字以内的描述
   2. 末尾附加 3-5 个 #话题标签
   3. 风格：专业但不枯燥
   只输出描述文本：\n\n{article_content}"
```

---

## 五、与现有模块的复用关系

| 复用来源 | 复用内容 |
|---------|---------|
| `2. Chrome_DevTool` | CDP 基础设施、Remote Debugging 配置 |
| `9. F5-WexinArchiver/auto_session.py` | CDPClient 类、标签页查找模式 |
| `8. F4-WexinPublisher/cover_generator.py` | Kiro CLI 调用模式、AI 文本生成 |
| `10. F6-Article2Video` | 视频文件输入（output-compressed.mp4） |

---

## 六、已知限制与注意事项

| 限制 | 说明 |
|------|------|
| 需要浏览器已登录 | 用户必须先在 Chrome 中登录 channels.weixin.qq.com |
| 页面结构可能变化 | 微信前端更新可能导致选择器失效，需定期维护 |
| 视频大小限制 | 视频号限制单个视频 ≤4GB，时长 ≤30 分钟 |
| 不支持 headless | 视频号创作者中心可能检测 headless 模式，建议 headed + DCV |
| Session 有效期 | 浏览器 session 约 2 小时过期，需重新登录 |

---

## 七、在流水线中的位置

```
F1 采集 → F2 写作 → F4 发布微信公众号 → F5 归档
                  └──→ F6 短视频生成
                           └──→ F7 发布视频号 ← 本模块
```

一篇文章，文字版走公众号（F4），视频版走视频号（F7），一鱼多吃。
