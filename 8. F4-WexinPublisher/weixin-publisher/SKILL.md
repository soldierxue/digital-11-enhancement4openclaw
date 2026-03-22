---
name: weixin-publisher
description: >
  将博客文章（URL 或本地 Markdown）自动转换格式、生成 AI 封面、通过微信公众号 API 发布为图文消息。
  支持图文混排、文中图片上传微信 CDN、AI 引言生成、5 风格 AI 封面、两阶段发布（快速草稿 + 封面优化）。
  本 Skill 执行时间较长（Phase 2 封面生成约 2 分钟），建议 OpenClaw 主 Agent 通过 SubAgent 委托执行。
  Activate when: 用户要求发布文章到微信, 微信公众号发布, 发布博客, 推送公众号,
  weixin publish, wechat article, 公众号草稿, 微信发文, 发微信文章,
  publish to wechat, 博客转公众号, markdown to wechat。
---

# Weixin Publisher — 微信公众号文章发布

将博客文章（URL 或本地 Markdown）自动发布到微信公众号，包含 AI 引言、图文混排、AI 封面生成。

## 执行架构

本 Skill 执行时间较长（Phase 1 ~10 秒 + Phase 2 ~2 分钟），建议通过 SubAgent 委托执行：

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 独立执行 Phase 1 + Phase 2
                          ├── Phase 1: 快速出草稿（~10 秒）
                          ├── Phase 2: AI 封面生成 + 更新草稿（~2 分钟）
                          └── 完成后向用户汇报结果
```

主 Agent 启动 SubAgent 时的 prompt 示例：

```
sessions_spawn:
  prompt: |
    你是微信公众号文章发布 Agent。
    请读取 SKILL_DIR/SKILL.md 了解执行流程。
    用户要求发布的文章: <URL 或 .md 路径>
    发布模式: draft（默认）
    开始执行。
```

主 Agent 只负责：确认用户意图 → 启动 SubAgent → 等待完成通知。

## 进度汇报规范

SubAgent 在执行过程中**必须定期向用户汇报进度**，不能静默执行到结束。

### 阶段性汇报（执行中）

在以下节点向用户输出进度：

| 节点 | 汇报内容 |
|------|----------|
| Step 1 完成 | 📄 文章已加载：标题、字数、图片数量 |
| Step 2 完成 | ✍️ AI 引言已生成（显示引言内容） |
| Step 3.5 完成 | 🖼️ 文中图片上传情况（N/M 张成功） |
| Step 4.5 完成 | 📚 扩展阅读：推荐 N 篇相关文章（显示标题列表） |
| Step 5 完成（Phase 1 结束） | ✅ Phase 1 完成：草稿已创建/更新，草稿 ID，可到微信后台预览 |
| Step 8 每张封面生成后 | 🎨 封面生成进度（如 "3/5 已生成"） |
| Step 10 完成（Phase 2 结束） | ✅ Phase 2 完成：已选封面风格，草稿已更新 |

### 最终总结（执行结束后）

全部流程完成后，输出一段结构化的草稿总结：

```
📋 微信草稿发布总结
━━━━━━━━━━━━━━━━━━━━
标题：<文章标题>
作者：<作者>
字数：<正文字数>
图片：<文中图片数量> 张（已上传微信 CDN）
引言：<AI 生成的 digest 内容>
封面：<选中的封面风格>（如 pixel / cyberpunk / 默认封面）
草稿 ID：<draft_media_id>
HTML 大小：<N> 字符
发布模式：draft / publish
状态：✅ 草稿已就绪，请到微信公众号后台查看
━━━━━━━━━━━━━━━━━━━━
```

如有异常（图片上传失败、封面生成失败等），在总结中一并说明。

## Prerequisites

- 环境变量 `WEIXIN_APPID` / `WEIXIN_SECRET` 已设置
  - 从 https://developers.weixin.qq.com/ 获取 AppID 和 Secret
  - IP 白名单已在微信后台配置
- Kiro CLI 已安装并可用（`kiro-cli --version`）
  - 用于 AI 文本智能：引言生成、摘要生成、文生图 prompt 生成
  - 调用方式：`kiro-cli chat --no-interactive --trust-all-tools "prompt"`
- AWS Bedrock 凭证可用
  - 用于 SD3.5 Large 封面图生成（us-west-2 区域）
  - 模型 ID：`stability.sd3-5-large-v1:0`
- Python 依赖已安装（`pip install -r SKILL_DIR/requirements.txt`）

验证命令：
```bash
# 微信凭证
echo $WEIXIN_APPID && echo $WEIXIN_SECRET

# Kiro CLI
kiro-cli --version
kiro-cli whoami

# AWS Bedrock
aws bedrock list-foundation-models --region us-west-2 | grep sd3
```

## Workflow

### Phase 1: 快速出草稿（~10 秒）

1. 确认输入源：用户提供的 URL 或本地 `.md` 文件路径
2. 运行发布脚本：
   ```bash
   command /usr/bin/python3 SKILL_DIR/main.py <URL 或 .md 路径>
   ```
3. 脚本自动执行：
   - Step 1: 加载文章（URL 抓取 或 本地 MD 读取）
   - Step 2: Kiro CLI 生成 AI 引言（100 字以内）
   - Step 3: 保存草稿 Markdown 到 `草稿记录/`（已有则读取，支持手动编辑后重跑）
   - Step 3.5: 上传文中图片到微信 CDN（已上传的自动跳过）
   - Step 4: Markdown → 微信 HTML（inline style + 图片 URL 替换）
   - Step 4.5: 扩展阅读推荐（从 weixin-indexer 读取文章索引 → Kiro CLI 语义匹配 → 生成推荐 HTML 插入文末）
   - Step 5: 上传默认封面 → 创建/更新草稿
4. Phase 1 完成后，用户可立即到微信后台预览草稿

### Phase 2: AI 封面生成 + 更新草稿（~2 分钟）

5. 脚本继续执行：
   - Step 6-7: Kiro CLI 生成 300 字摘要 → 5 风格文生图 prompt
   - Step 8: Bedrock SD3.5 Large 生成封面图（3:2 比例）
   - Step 9: 上传所有封面到微信（已上传的自动跳过）
   - Step 10: 用户交互选择封面 → update_draft 更新草稿封面
6. 如需发布（而非仅草稿），添加 `--mode publish` 参数

### 资源去重

脚本通过 `草稿记录/cover_registry.json` 自动管理去重：
- 文中图片：`content_images[img_ref].weixin_url` 存在 → 跳过上传
- 默认封面：`covers.default.media_id` 存在 → 跳过上传
- AI 封面：`covers[style].media_id` 存在 → 跳过生成和上传
- 草稿：`draft_media_id` 存在 → `update_draft()` 而非 `create_draft()`
- 重复运行同一篇文章不会产生重复上传

### 异常处理

| 场景 | 处理 |
|------|------|
| Kiro CLI 不可用 | 使用默认摘要，跳过 AI 封面生成 |
| 单张封面生成失败 | 静默跳过，其余继续 |
| 全部封面生成失败 | 保持默认封面 |
| 草稿更新失败 | 自动回退为新建草稿 |
| 文中图片上传失败 | 跳过该图片，HTML 中保留原始路径 |
| HTML 超过 2 万字符 | 打印警告，继续（可能被微信截断） |

## Configuration

配置文件：`SKILL_DIR/config.json`

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

## Troubleshooting

| 问题 | 处理 |
|------|------|
| `WEIXIN_APPID` 未设置 | `export WEIXIN_APPID="..." WEIXIN_SECRET="..."`，从 https://developers.weixin.qq.com/ 获取 |
| 微信 API 返回 IP 不在白名单 | 到微信公众号后台 → 开发 → 基本配置 → IP 白名单，添加当前 IP |
| access_token 获取失败 | 检查 AppID/Secret 是否正确；检查网络连接 |
| Kiro CLI 输出含 ANSI 转义码 | 脚本已内置 `_ANSI_RE` 正则自动清理 |
| 封面图比例不对 | 检查 `cover_generator.py` 中 Bedrock 参数，应为 3:2（如 1440×960） |
| `command /usr/bin/python3` 报错 | Shell 有 pyenv init 问题，`command` 前缀绕过 |
| 草稿标题被截断 | 微信限制 title ≤ 64 字符，脚本已自动截断 |
| 图片上传返回空 URL | 检查图片格式（支持 jpg/png/gif），文件大小 ≤ 10MB |

## 已知问题与注意事项

### nl2br 与有序列表的微信手机端渲染 Bug

`md2weixin.py` 使用 `nl2br` Markdown 扩展，当有序列表项之间有空行时，会导致 `<li>` 内嵌套 `<p>` 标签。微信手机端对此渲染异常（奇数项显示为空行）。

**处理方式**：对参考资料等有序列表，在 Markdown 转换前分离出来，单独构建 `<ol><li>` HTML（不嵌套 `<p>`），通过 `related_html` 参数拼接。不要将有序列表放在 Markdown 正文中经过 `nl2br` 处理。

### pyenv 环境下的 Python 执行

Agent 的 shell 环境可能未加载 `.bashrc` 中的 pyenv init，导致 `python3` 命令失败。

**处理方式**：使用 `command /usr/bin/python3` 或 `env -i HOME="$HOME" PATH="/usr/bin:/bin" /usr/bin/python3` 执行脚本。

### 扩展阅读 HTML 的提取与拼接

- `related_html` 是原始 HTML，直接拼接在 disclaimer 之前，不经过 Markdown 渲染
- 从已有 HTML 提取扩展阅读时，注意正则不要匹配到外层 `<section>` 容器，应通过特征样式（`border-left: 4px solid #0969da`）或标题文本（`📚 扩展阅读`）精确定位
- `disclaimer.html` 模板会自动追加到所有文章末尾

### 文章索引来源

扩展阅读的候选文章来自 `articles_index.json`：
- 主索引：`../9. F5-WexinArchiver/weixin-indexer/articles_index.json`（由 F5 的 `sync_articles.py` 维护）
- 本地回退：`SKILL_DIR/articles_index.json`
- 如推荐结果不理想，先检查索引是否已同步最新发布的文章
