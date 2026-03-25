# F4-WeixinPublisher — 博客文章自动发布微信公众号

> 从个人博客 URL 或本地 Markdown 文件，自动转换格式、生成 AI 封面、通过微信公众号 API 发布为图文消息。支持图文混排。

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | 运行环境 |
| 微信公众号 | 已认证，到 https://developers.weixin.qq.com/ 获取 AppID/AppSecret，IP 白名单已配置 |
| Kiro CLI | AI 文本智能（引言 + 摘要 + prompt 生成） |
| AWS Bedrock | SD3.5 Large 模型访问权限（us-west-2） |
| AWS 凭证 | `~/.aws/credentials` 或环境变量 |

Python 依赖：

```
requests
beautifulsoup4
readability-lxml
html2text
markdown
pyyaml
lxml
boto3
```

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 执行方式：SubAgent 委托

本 Skill 执行时间较长（Phase 1 ~10 秒 + Phase 2 封面生成 ~2 分钟），**必须通过 SubAgent 委托执行**，避免阻塞主 Agent。

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行完整流程
                          ├── Phase 1: 快速出草稿（~10 秒）
                          ├── Phase 2: AI 封面生成 + 更新草稿（~2 分钟）
                          └── 完成后向用户汇报结果
```

启动 SubAgent 的 prompt：

```
sessions_spawn:
  prompt: |
    你是微信公众号文章发布 Agent。
    请读取 skills/weixin-publisher/SKILL.md 了解你的职责和执行流程。
    用户要求发布的文章: <URL 或 .md 路径>
    发布模式: draft
    开始执行。
```

### 主 Agent 职责

1. 确认用户意图（发布哪篇文章、draft 还是 publish）
2. 启动 SubAgent（sessions_spawn）
3. 等待 SubAgent 完成，向用户汇报结果

**不要**在主 Agent 中直接运行 `main.py`，那会阻塞 2+ 分钟。

### 进度汇报规范

SubAgent 在执行过程中**必须定期向用户汇报进度**，不能静默执行到结束。

阶段性汇报节点：

| 节点 | 汇报内容 |
|------|----------|
| Step 1 完成 | 📄 文章已加载：标题、字数、图片数量 |
| Step 2 完成 | ✍️ AI 引言已生成（显示引言内容） |
| Step 3.5 完成 | 🖼️ 文中图片上传情况（N/M 张成功） |
| Phase 1 结束 | ✅ 草稿已创建/更新，草稿 ID，可到微信后台预览 |
| 每张封面生成后 | 🎨 封面生成进度（如 "3/5 已生成"） |
| Phase 2 结束 | ✅ 已选封面风格，草稿已更新 |

全部完成后输出结构化总结：标题、作者、字数、图片数、引言内容、封面风格、草稿 ID、HTML 大小、发布模式、状态。详见 SKILL.md「进度汇报规范」。

### 前置检查（启动前快速验证）

```bash
# 微信凭证
[ -n "$WEIXIN_APPID" ] && echo "✓ APPID" || echo "✗ WEIXIN_APPID 未设置"
[ -n "$WEIXIN_SECRET" ] && echo "✓ SECRET" || echo "✗ WEIXIN_SECRET 未设置"

# Kiro CLI（AI 文本智能）
kiro-cli --version 2>/dev/null && echo "✓ Kiro CLI" || echo "✗ Kiro CLI 未安装"

# AWS Bedrock（封面图生成）
aws sts get-caller-identity 2>/dev/null && echo "✓ AWS 凭证" || echo "✗ AWS 凭证不可用"
```

如有缺失，参考本文档开头「前置条件」章节补齐后再启动 SubAgent。

---

## 一、功能概述

将博客文章自动发布到微信公众号，完整流程：

```
博客文章 URL ──┐                    ┌─ AI 引言（Kiro CLI）
               ├─► 统一 Markdown ──►├─ 文中图片上传（微信 CDN）
本地 MD 文件 ──┘                    ├─ Markdown → 微信 HTML（inline style）
                                    ├─ 默认封面 → 创建草稿（Phase 1，~10秒）
                                    └─ AI 封面生成 → 更新草稿（Phase 2，~2分钟）
```

### 已实现功能

| 功能 | 状态 | 说明 |
|------|------|------|
| URL 抓取 → Markdown | ✅ | readability + html2text |
| 本地 .md 文件读取 | ✅ | 支持 YAML front-matter 和 `[date]_[title].md` 文件名格式 |
| AI 引言生成 | ✅ | Kiro CLI，100 字以内吸引读者的摘要 |
| 文中图片上传 | ✅ | 本地/URL 图片 → 微信 uploadimg API → CDN URL 替换 |
| Markdown → 微信 HTML | ✅ | BeautifulSoup 后处理，全量 inline style |
| AI 封面生成（5 风格） | ✅ | Kiro CLI 生成 prompt → Bedrock SD3.5 Large 出图 |
| 两阶段发布 | ✅ | Phase 1 快速草稿 + Phase 2 封面优化 |
| 草稿更新（非重复创建） | ✅ | registry 记录 draft_media_id，已有则 update |
| 资源去重 | ✅ | 封面/文中图片/草稿均通过 registry 跳过重复上传 |
| 扩展阅读推荐 | ✅ | 从公众号已发布文章中语义匹配 5+ 篇相关文章，插入文末 |

---

## 二、两阶段发布流程

### Phase 1: 快速出草稿（~10 秒）

```
Step 1  加载文章（URL 抓取 或 本地 MD 读取）
Step 2  AI 生成引言（Kiro CLI，100 字以内）
Step 3  保存/读取草稿 Markdown（草稿记录/ 目录）
Step 3.5 上传文中图片到微信 CDN（跳过已上传的）
Step 4  Markdown → 微信 HTML（inline style + 图片 URL 替换）
Step 4.5 扩展阅读推荐（同步已发布文章索引 → Kiro CLI 语义匹配 → 生成推荐 HTML）
Step 5  上传默认封面 → 创建/更新草稿
→ 用户可立即到微信后台预览
```

### Phase 2: AI 封面生成 + 更新草稿（~2 分钟）

```
Step 6  Kiro CLI 生成 300 字摘要
Step 7  Kiro CLI 生成 5 风格文生图 prompt
Step 8  Bedrock SD3.5 Large 生成封面图（3:2 比例）
Step 9  上传所有封面 → 用户选择
Step 10 draft/update 更新草稿封面
```

---

## 三、架构与模块

> `main.py` 是唯一入口，包含完整的两阶段发布流程（`publish_article()` 函数）。无需任何额外脚本。

```
weixin-publisher/
├── SKILL.md                 # Agent 执行指南（SubAgent 委托执行）
├── main.py                  # 唯一入口（两阶段流程编排，python main.py <文章路径>）
├── input_handler.py         # 统一输入层（URL / .md → Markdown + 元数据）
├── cover_generator.py       # AI 封面生成（Kiro CLI + Bedrock SD3.5 Large）
├── md2weixin.py             # Markdown → 微信 HTML（inline style）
├── related_reading.py       # 扩展阅读推荐（读取 weixin-indexer 索引 + Kiro CLI 语义匹配）
├── weixin_publish.py        # 微信 API 客户端（发布相关接口）
├── config.json              # 非敏感配置
├── requirements.txt         # Python 依赖
├── articles_index.json      # 文章索引本地回退（主索引在 F5-WexinArchiver）
├── assets/
│   └── default_cover.jpg    # 默认封面
├── markdown_html_template/
│   ├── disclaimer.html      # 文末标准声明（自动追加到所有文章）
│   └── weixin-inline-template.html  # 样式参考模板
└── 草稿记录/
    ├── [date]_[title].md    # 草稿 Markdown
    ├── [date]_[title].html  # 转换后的微信 HTML
    ├── [title]-[style].png  # AI 生成的封面图（5 风格）
    └── cover_registry.json  # 资源注册表（封面/图片/草稿去重）
```

### 3.1 input_handler.py — 统一输入层

- URL 输入：`requests` → `readability-lxml` 提取正文 → `html2text` 转 Markdown
- 本地 .md 输入：读取文件 → 解析 YAML front-matter → 分离元数据和正文
- 标题提取优先级：front-matter `title` → 正文第一个 `#` 标题 → 文件名 `[date]_[title].md` 格式解析
- 统一输出 `dict`：title, author, date, content_md, digest, source_url, images, word_count, front_matter

### 3.2 cover_generator.py — AI 封面图生成

```
文章正文 → Kiro CLI 生成 300 字摘要
         → Kiro CLI 生成 5 风格英文 prompt（JSON 格式）
         → Bedrock SD3.5 Large 出图（3:2 比例）
         → 用户交互选择
```

- 5 种预定义风格：赛博朋克 / 科幻 / 像素风 / 漫画风 / 浮世绘
- Kiro CLI 调用：`kiro-cli chat --no-interactive --trust-all-tools "prompt"`
- ANSI 转义序列自动清理（Kiro CLI 输出中的终端颜色代码）
- AI 引言生成：100 字以内，用于微信 digest 字段
- 单张生成失败静默跳过，全部失败兜底使用默认封面

### 3.3 md2weixin.py — Markdown → 微信 HTML

- `markdown` 库渲染 HTML → `BeautifulSoup` 后处理添加 inline style
- 样式覆盖：h1~h4、p、blockquote、pre/code、ul/ol/li、table、img、hr、a、strong、del
- 图片 URL 替换：通过 `image_map` 参数将本地/外部图片路径替换为微信 CDN URL
- `related_html` 参数：原始 HTML 直接拼接在 disclaimer 之前，不经过 Markdown 渲染
- `disclaimer.html` 模板自动追加到所有文章末尾
- 输出包裹在 `<section>` 容器中，max-width 680px

> ⚠️ **已知问题：`nl2br` 扩展与有序列表的兼容性**
>
> `md2weixin.py` 使用了 `nl2br` Markdown 扩展（将换行转为 `<br>`），这会导致有序列表项之间如果有空行，
> 渲染出的 `<li>` 内部嵌套 `<p>` 标签。微信手机端渲染器对 `<li><p>...</p></li>` 的处理有 bug，
> 会导致奇数项显示为空行。
>
> **解决方案**：对于参考资料等有序列表，应在 Markdown 转换前将其从正文中分离，
> 单独构建干净的 `<ol><li>` HTML（不嵌套 `<p>`），再通过 `related_html` 参数拼接到最终输出。

### 3.4 related_reading.py — 扩展阅读推荐

从公众号已发布文章中，基于当前文章内容语义匹配相关历史文章，生成推荐列表插入文末。

> 注意：文章索引同步逻辑已拆分到 **F5-WexinArchiver/weixin-indexer**，本模块仅负责读取索引 + 语义推荐 + 生成 HTML。

```
weixin-indexer 的 articles_index.json（全量索引）
                         │
                         ▼
当前文章内容 → Kiro CLI 语义匹配 → 推荐 5+ 篇 → 生成 HTML 块
```

- `load_articles_index()` — 优先从 weixin-indexer 读取索引，回退到本地
- `recommend_related(content_md, title, articles_index, count)` — 调用 Kiro CLI 对当前文章与历史文章做语义匹配，返回推荐列表
- `build_related_reading_html(recommendations)` — 生成带 inline style 的扩展阅读 HTML 块（📄 图标 + 蓝色链接卡片）

索引同步请使用 F5-WexinArchiver 的 `sync_articles.py`：

```bash
cd ../9.\ F5-WexinArchiver/weixin-indexer/
python sync_articles.py
```

### 3.5 weixin_publish.py — 微信 API 客户端

- AppID/Secret 从环境变量 `WEIXIN_APPID` / `WEIXIN_SECRET` 获取
- access_token 本地缓存，提前 5 分钟刷新
- 字段截断按字符数：title ≤ 64、digest ≤ 120、author ≤ 8
- API 方法（仅发布相关）：
  - `get_access_token()` — 获取/刷新 token
  - `upload_permanent_image()` — 上传永久素材（封面），返回 media_id
  - `upload_content_image()` — 上传正文图片（支持本地路径和 URL），返回微信 CDN URL
  - `create_draft()` — 创建草稿
  - `update_draft()` — 更新已有草稿
  - `publish()` — 发布草稿
  - `get_publish_status()` — 查询发布状态

> 文章索引相关 API（`get_published_articles`、`get_admin_articles`、`get_freepublish_articles`）已拆分到 F5-WexinArchiver/weixin-indexer 的 `weixin_client.py`。

### 3.6 cover_registry.json — 资源注册表

统一记录每篇文章的所有上传资源，避免重复上传：

```json
{
  "文章标题": {
    "title": "...",
    "date": "2026-03-21",
    "covers": {
      "default": { "local_path": "...", "media_id": "...", "uploaded_at": "..." },
      "cyberpunk": { "local_path": "...", "media_id": "...", "uploaded_at": "..." },
      ...
    },
    "content_images": {
      "../assets/sample_image.png": {
        "local_path": "/absolute/path/to/image.png",
        "weixin_url": "http://mmbiz.qpic.cn/...",
        "uploaded_at": "2026-03-21"
      }
    },
    "selected_style": "cyberpunk",
    "selected_media_id": "...",
    "draft_media_id": "...",
    "draft_created_at": "2026-03-21",
    "draft_updated_at": "2026-03-21"
  }
}
```

去重检查点：
- 文中图片：`content_images[img_ref].weixin_url` 存在 → 跳过上传，直接用已有 URL
- 默认封面：`covers.default.media_id` 存在 → 跳过上传
- AI 封面：`covers[style].media_id` 存在 → 跳过生成和上传
- 草稿：`draft_media_id` 存在 → `update_draft()` 而非 `create_draft()`

---

## 四、使用方法

### 4.1 环境准备

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 设置微信凭证（环境变量，不保存在本地文件）
export WEIXIN_APPID="your_appid"
export WEIXIN_SECRET="your_secret"

# 3. 确认 Kiro CLI 可用（AI 引言 + 封面 prompt 生成）
kiro-cli --version
kiro-cli whoami

# 4. 确认 AWS Bedrock 凭证（封面图生成）
# 需要 us-west-2 区域的 stability.sd3-5-large-v1:0 模型访问权限
aws bedrock list-foundation-models --region us-west-2 | grep sd3
```

### 4.2 运行

`main.py` 是唯一入口，包含完整的两阶段发布流程。无需创建任何额外脚本。

```bash
# 从 URL 抓取并创建草稿
python main.py https://example.com/article

# 从本地 MD 文件创建草稿
python main.py /path/to/article.md

# 创建草稿并发布
python main.py https://example.com/article --mode publish
```

**pyenv 环境兼容写法**（Agent 执行时推荐）：

```bash
env -i HOME="$HOME" \
  PATH="/usr/bin:/usr/local/bin:/opt/homebrew/bin:/bin:$HOME/.local/bin" \
  WEIXIN_APPID="your_appid" WEIXIN_SECRET="your_secret" \
  AWS_SHARED_CREDENTIALS_FILE="$HOME/.aws/credentials" \
  AWS_CONFIG_FILE="$HOME/.aws/config" \
  python3 "digital-11-enhancement4openclaw/8. F4-WexinPublisher/weixin-publisher/main.py" \
  "/path/to/article.md"
```

> `main.py` 的 `publish_article()` 函数会自动完成全部流程：加载文章 → 生成引言 → 上传图片 → 扩展阅读 → 生成 HTML → 创建草稿 → AI 封面生成 → 用户选择封面 → 更新草稿。

### 4.3 配置文件 config.json

```json
{
  "default_author": "薛以致用",
  "default_cover": "assets/default_cover.jpg",
  "cover_styles": ["cyberpunk", "scifi", "pixel", "comic", "ukiyoe"],
  "bedrock_region": "us-west-2",
  "need_open_comment": 1,
  "only_fans_can_comment": 0,
  "publish_mode": "draft",
  "related_reading_count": 5
}
```

---

## 五、微信公众号 API 参考

| 步骤 | API | 说明 |
|------|-----|------|
| 获取 token | `GET /cgi-bin/token` | 有效期 2h，本地缓存 |
| 上传封面 | `POST /cgi-bin/material/add_material` | 永久素材，返回 media_id |
| 上传正文图片 | `POST /cgi-bin/media/uploadimg` | 返回微信 CDN URL |
| 创建草稿 | `POST /cgi-bin/draft/add` | 返回 draft media_id |
| 更新草稿 | `POST /cgi-bin/draft/update` | 更新已有草稿内容/封面 |
| 发布 | `POST /cgi-bin/freepublish/submit` | 返回 publish_id |

> 文章索引相关 API 参考请见 F5-WexinArchiver 的 README.md。

字段限制（字符数）：title ≤ 64、digest ≤ 120、author ≤ 8、content ≤ 20000 字符 / 1MB

---

## 六、文章索引与内容备份

文章索引同步和内容备份功能已拆分为独立 Skill：**F5-WexinArchiver/weixin-indexer**。

详见 `../9. F5-WexinArchiver/README.md`。

本 Skill 的扩展阅读功能会自动从 weixin-indexer 的 `articles_index.json` 读取候选文章列表。
如需刷新索引，请运行：

```bash
cd ../9.\ F5-WexinArchiver/weixin-indexer/
export WEIXIN_APPID="your_appid" WEIXIN_SECRET="your_secret"
python sync_articles.py
```

---

## 七、已知问题与注意事项

### 7.1 `nl2br` 扩展导致有序列表在微信手机端渲染异常

`md2weixin.py` 使用 `nl2br` Markdown 扩展（将换行转为 `<br>`），这在大多数场景下改善了微信端的排版。但当 Markdown 中的有序列表项之间存在空行时，`nl2br` 会导致 `<li>` 内部嵌套 `<p>` 标签：

```html
<!-- 异常结构 -->
<ol>
  <li><p>第一项</p></li>
  <li><p>第二项</p></li>
</ol>
```

微信手机端渲染器对这种嵌套结构处理有 bug，会导致奇数项显示为空行。

**解决方案**：对于参考资料等有序列表，在 Markdown 转换前将其从正文中分离，单独构建干净的 `<ol><li>` HTML（不嵌套 `<p>`），再通过 `md_to_weixin_html()` 的 `related_html` 参数拼接到最终输出。

### 7.2 pyenv 环境兼容性

在配置了 pyenv 的系统上，通过 Agent 执行 `python3` 可能触发 `bash: pyenv: command not found` 错误（因为 Agent 的 shell 环境未加载 `.bashrc` 中的 pyenv init）。

**解决方案**：

```bash
# 方案 1：使用 command 前缀绕过 shell function
command /usr/bin/python3 main.py <args>

# 方案 2：使用干净的 PATH 环境
env -i HOME="$HOME" PATH="/usr/bin:/bin:/usr/local/bin" /usr/bin/python3 main.py <args>

# 方案 3：在命令前设置 PATH
export PATH="/usr/bin:/usr/local/bin:/opt/homebrew/bin:$PATH" && python3 main.py <args>
```

### 7.3 扩展阅读 HTML 提取注意事项

从已有 HTML 文件中提取扩展阅读部分时，需注意正则匹配范围。文章整体包裹在 `<section>` 容器中，扩展阅读也使用 `<section>` 标签，简单的 `<section>.*</section>` 正则会匹配到外层容器导致内容重复。建议通过扩展阅读的特征样式（如 `border-left: 4px solid #0969da`）或标题文本（`📚 扩展阅读`）来精确定位。

### 7.4 微信 HTML 内容大小限制

微信公众号 API 对 `content` 字段有 20000 字符 / 1MB 的限制。脚本在超过 2 万字符时会打印警告，但不会阻止提交。超长内容可能被微信截断。


