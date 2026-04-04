---
name: weixin-indexer
description: >
  微信公众号历史文章索引同步与内容备份。三来源合并去重获取全量文章索引，
  并可将文章正文下载为本地 Markdown 备份。
  Activate when: 用户要求同步文章索引, 备份微信文章, 下载公众号文章,
  weixin index, wechat backup, 文章备份, 公众号备份, 同步文章,
  微信文章下载, article backup, sync articles, 文章索引。
---

# Weixin Indexer — 微信公众号文章索引与内容备份

从微信公众号拉取全量已发布文章索引（三来源合并去重），并可将文章正文下载备份为本地 Markdown。

## 执行架构

本 Skill 涉及大量网络请求，建议通过 SubAgent 委托执行：

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行
                          ├── Phase 1: 同步文章索引（~2 分钟）
                          ├── Phase 2: 下载文章正文备份（~15 分钟，可选）
                          └── 完成后向用户汇报结果
```

## Prerequisites

- 环境变量 `WEIXIN_APPID` / `WEIXIN_SECRET` 已设置
- Python 依赖已安装（`pip install -r SKILL_DIR/requirements.txt`）
- （可选）`weixin_admin_session.json` 已配置（获取全量文章索引）
- （可选）Chrome Remote Debugging 已启用（用于 CDP 自动提取 session）

验证命令：
```bash
echo $WEIXIN_APPID && echo $WEIXIN_SECRET
# 验证 CDP 连接（可选）
curl -s http://127.0.0.1:9222/json/version 2>/dev/null | head -1 || echo "CDP 未连接（可选）"
```

## Workflow

### Phase 1: 同步文章索引

```bash
export WEIXIN_APPID="your_appid" WEIXIN_SECRET="your_secret"
/usr/bin/python3 SKILL_DIR/sync_articles.py
```

三来源合并去重：
1. `material/batchget_material (type=news)` — 旧体系（~96 篇）
2. `freepublish/batchget` — 新体系（订阅号通常无权限，静默跳过）
3. `appmsg?action=list_ex` — 后台管理接口全量（需 cookie 认证）

输出：`SKILL_DIR/articles_index.json`

### Phase 2: 下载文章正文备份（可选）

```bash
/usr/bin/python3 SKILL_DIR/sync_articles.py --backup
```

或仅备份（使用已有索引）：

```bash
/usr/bin/python3 SKILL_DIR/sync_articles.py --backup-only
```

- 逐篇下载 → readability 提取正文 → html2text 转 Markdown
- 按年月归档到 `SKILL_DIR/备份/YYYY-MM/[title].md`
- 增量备份：跳过已存在的文件
- 限速 2 秒/篇，失败记录到 `backup_errors.json`

### 设置后台 Session

**方式一：CDP 自动提取（推荐）**

需要浏览器已启用 Remote Debugging 且已登录微信后台：

```bash
/usr/bin/python3 SKILL_DIR/sync_articles.py --auto-session
```

或单独提取 session：

```bash
/usr/bin/python3 SKILL_DIR/auto_session.py
```

ARM64 Snap Chromium 使用端口 18800：

```bash
/usr/bin/python3 SKILL_DIR/auto_session.py --cdp-url http://127.0.0.1:18800
```

前置条件：
- Chrome/Chromium 已启用 Remote Debugging（参见 `2. Chrome_DevTool/README.md` Part 3 Step 13）
- 用户已在浏览器中登录 https://mp.weixin.qq.com
- 建议先在后台点击「内容与互动」→「图文消息」，确保 URL 中包含 token 参数

**方式二：交互式手动设置**

```bash
/usr/bin/python3 SKILL_DIR/sync_articles.py --setup-admin
```

交互式输入 cookie + token，保存到 `weixin_admin_session.json`。

## 进度汇报规范

| 节点 | 汇报内容 |
|------|----------|
| 索引同步完成 | 📋 共同步 N 篇文章，日期范围 |
| 备份进度（每 20 篇） | 📥 进度 N/M（成功/跳过/失败） |
| 全部完成 | ✅ 索引 N 篇，备份成功 X 篇，跳过 Y 篇，失败 Z 篇 |

## Configuration

`SKILL_DIR/config.json`:

```json
{
  "backup_dir": "备份",
  "backup_delay_seconds": 2,
  "admin_page_size": 5,
  "admin_page_delay_seconds": 1
}
```

## 与 F4-WeixinPublisher 的关系

本 Skill 的 `articles_index.json` 被 F4 的 `related_reading.py` 读取，
用于扩展阅读推荐的候选文章列表。

## Troubleshooting

| 问题 | 处理 |
|------|------|
| `WEIXIN_APPID` 未设置 | `export WEIXIN_APPID="..." WEIXIN_SECRET="..."` |
| 后台接口 200013 | 频率限制，等待 1 分钟后重试 |
| Cookie 过期 | 重新提取：`--auto-session` 或 `--setup-admin` |
| CDP 连接失败 | 确认浏览器已启用 Remote Debugging（参见 Chrome_DevTool README） |
| CDP 未找到微信页面 | 先在浏览器中登录 mp.weixin.qq.com |
| CDP 提取不到 token | 在后台点击「图文消息」使 URL 包含 token 参数，再重试 |
| 备份下载失败 | 检查网络；失败记录在 `backup_errors.json`，重跑会自动重试 |
| freepublish 48001 | 订阅号无此权限，正常现象，使用后台接口替代 |
