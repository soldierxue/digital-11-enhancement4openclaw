# F5-WexinArchiver — 微信公众号文章索引与内容备份

> 独立 Skill：从微信公众号拉取全量已发布文章索引，并将文章正文下载备份为本地 Markdown 文件。

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | 运行环境 |
| 微信公众号 | 已认证，到 https://developers.weixin.qq.com/ 获取 AppID/AppSecret，IP 白名单已配置 |
| 微信后台 Session | 通过 CDP 自动提取（推荐）或从浏览器手动获取 cookie + token |
| Chrome Remote Debugging | （可选）用于 CDP 自动提取 session，参见 `2. Chrome_DevTool/README.md` |

Python 依赖：

```
requests
readability-lxml
html2text
lxml
websocket-client
```

---

## ⚙️ Agent 执行指引（OpenClaw 请先读此段）

> **本段是给你（执行 Agent）的操作规范，不是给人类用户看的文档。请严格遵循。**

### 执行方式：SubAgent 委托

本 Skill 涉及大量网络请求（索引同步 + 内容下载），执行时间较长（全量备份 280 篇约 15-20 分钟），**建议通过 SubAgent 委托执行**。

```
OpenClaw 主 Agent
  └── 用户触发 → sessions_spawn 启动 SubAgent
                    └── SubAgent 读取 SKILL.md → 独立执行
                          ├── Phase 1: 同步文章索引（~2 分钟）
                          ├── Phase 2: 下载文章正文备份（~15 分钟）
                          └── 完成后向用户汇报结果
```

### 前置检查

```bash
# 微信凭证
[ -n "$WEIXIN_APPID" ] && echo "✓ APPID" || echo "✗ WEIXIN_APPID 未设置"
[ -n "$WEIXIN_SECRET" ] && echo "✓ SECRET" || echo "✗ WEIXIN_SECRET 未设置"
```

---

## 一、功能概述

```
微信公众号 API ──┐
                 ├─► 三来源合并去重 → articles_index.json（全量索引）
后台管理接口 ────┘
       ▲                 │
       │                 ▼
  CDP 自动提取      逐篇下载正文 → readability 提取 → html2text 转 Markdown
  cookie+token           │
  (auto_session.py)      ▼
       ▲           备份/ 目录（按年月归档）
       │
  Chrome 浏览器
  (Remote Debugging)
```

### 已实现功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 旧体系文章索引 | ✅ | `material/batchget_material (type=news)`，~96 篇 |
| 新体系文章索引 | ✅ | `freepublish/batchget`（订阅号通常无权限，静默跳过） |
| 后台全量索引 | ✅ | `appmsg?action=list_ex`，需 cookie 认证，覆盖最全 |
| CDP 自动提取 Session | ✅ | 通过 Chrome DevTools Protocol 自动获取 cookie + token |
| 三来源合并去重 | ✅ | 以 URL 为主键，admin > freepublish > material |
| 文章正文备份 | ✅ | requests + readability + html2text → Markdown |
| 增量备份 | ✅ | 跳过已备份文章，支持断点续传 |
| 按年月归档 | ✅ | `备份/YYYY-MM/[title].md` |

---

## 二、架构与模块

```
weixin-indexer/
├── SKILL.md                        # Agent 执行指南
├── sync_articles.py                # 入口脚本：同步索引 + 内容备份
├── weixin_client.py                # 微信 API 客户端（索引相关接口）
├── article_backup.py               # 文章正文下载与备份
├── auto_session.py                 # CDP 自动提取微信后台 cookie + token
├── config.json                     # 非敏感配置
├── requirements.txt                # Python 依赖
├── weixin_admin_session.json       # 微信后台 session（cookie+token，.gitignore）
├── weixin_admin_session.example.json # session 示例文件
├── articles_index.json             # 全量文章索引（title + url + date + digest）
└── 备份/                            # 文章正文 Markdown 备份
    ├── 2026-03/
    │   ├── 亚麻十年：班味、人味和下一个十年.md
    │   └── ...
    ├── 2026-02/
    └── ...
```

### 2.1 weixin_client.py — 微信 API 客户端

从 F4 weixin-publisher 提取的索引相关 API 方法：

- `get_access_token()` — 获取/刷新 token（本地缓存，提前 5 分钟刷新）
- `get_published_articles(offset, count)` — 旧体系 `material/batchget_material (type=news)`
- `get_freepublish_articles(offset, count)` — 新体系 `freepublish/batchget`
- `get_admin_articles(cookie, token, fakeid, begin, count)` — 后台管理接口全量文章

AppID/Secret 从环境变量 `WEIXIN_APPID` / `WEIXIN_SECRET` 获取。

### 2.2 sync_articles.py — 索引同步入口

三来源合并去重策略（后者覆盖前者）：

| 来源 | API | 覆盖范围 | 权限要求 |
|------|-----|----------|----------|
| 1. 旧体系素材 | `material/batchget_material (type=news)` | 2019-2021 旧图文素材（~96 篇） | 普通订阅号可用 |
| 2. 新体系发布 | `freepublish/batchget` | 2021+ 已发布文章 | 仅服务号（订阅号 48001 无权限） |
| 3. 后台管理接口 | `mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex` | 全量文章（新旧体系均可） | 需浏览器 cookie 认证 |

命令行用法：

```bash
# 同步索引（所有可用来源）
python sync_articles.py

# 交互式设置后台 session
python sync_articles.py --setup-admin

# 同步索引 + 下载正文备份
python sync_articles.py --backup

# 仅下载正文备份（使用已有索引）
python sync_articles.py --backup-only
```

### 2.3 article_backup.py — 文章正文备份

- 遍历 `articles_index.json` 中的文章 URL
- `requests` 下载 HTML → `readability-lxml` 提取正文 → `html2text` 转 Markdown
- 按年月归档到 `备份/YYYY-MM/[title].md`
- 增量备份：跳过已存在的文件
- 限速：每篇间隔 2-3 秒，避免被封
- 失败静默跳过，记录到 `backup_errors.json`

### 2.4 auto_session.py — CDP 自动提取后台 Session

通过 Chrome DevTools Protocol (CDP) 自动从浏览器中提取微信后台的 cookie + token，替代手动复制粘贴。

工作流程：
1. 连接 Chrome Remote Debugging 端口（默认 9222，ARM64 Snap 为 18800）
2. 在浏览器标签页中查找 `mp.weixin.qq.com` 页面
3. 通过 `Runtime.evaluate` 执行 `document.cookie` 获取 cookie
4. 从 URL 参数、页面链接、script 标签中提取 token
5. 保存到 `weixin_admin_session.json`

前置条件：
- Chrome/Chromium 已启用 Remote Debugging（参见 `2. Chrome_DevTool/README.md` Part 3 Step 13）
- 用户已在浏览器中登录微信公众号后台

### 2.4 articles_index.json — 文章索引格式

```json
[
  {
    "title": "文章标题",
    "url": "http://mp.weixin.qq.com/s?...",
    "date": "2026-03-20",
    "digest": "文章摘要..."
  }
]
```

---

## 三、获取全量文章索引（后台管理接口）

微信公众号 API 对订阅号有权限限制：
- `material/batchget_material (type=news)` 只能获取旧体系图文素材（2019-2021，约 96 篇）
- `freepublish/batchget` 需要"已发布文章管理"权限，订阅号无此权限（errcode 48001）

要获取全部文章，需要使用微信后台管理页面的内部接口 `appmsg?action=list_ex`。

### 3.1 获取 Cookie + Token

**方式一：CDP 自动提取（推荐）**

利用 Chrome DevTools Protocol 自动从浏览器中提取，无需手动操作：

```bash
# 前置：浏览器已启用 Remote Debugging 且已登录 mp.weixin.qq.com
python auto_session.py

# ARM64 Snap Chromium
python auto_session.py --cdp-url http://127.0.0.1:18800

# 或在同步时自动提取
python sync_articles.py --auto-session
python sync_articles.py --auto-session --backup
```

> 建议先在浏览器后台点击「内容与互动」→「图文消息」，确保 URL 中包含 token 参数。

**方式二：手动从浏览器获取**

1. 用浏览器登录 https://mp.weixin.qq.com
2. 打开开发者工具（F12）→ Network 选项卡
3. 在后台左侧菜单点击「内容与互动」→「图文消息」
4. 在 Network 中找到 `appmsg?action=list_ex` 请求
5. 从请求头（Request Headers）中复制完整 Cookie
6. 从请求 URL 参数中复制 `token`

### 3.2 保存 Session

方式一：交互式设置

```bash
python sync_articles.py --setup-admin
```

方式二：手动创建 `weixin_admin_session.json`

```json
{
  "cookie": "从浏览器复制的完整 Cookie 字符串",
  "token": "1234567890"
}
```

注意：Cookie 有效期约 2 小时，过期后需重新从浏览器获取。`weixin_admin_session.json` 已加入 `.gitignore`。

---

## 四、使用方法

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置微信凭证
export WEIXIN_APPID="your_appid"
export WEIXIN_SECRET="your_secret"

# 3. 设置后台 session（二选一）
python auto_session.py                     # CDP 自动提取（推荐）
python sync_articles.py --setup-admin      # 手动输入

# 4. 同步文章索引
python sync_articles.py

# 5. 自动提取 session + 同步索引（一步完成）
python sync_articles.py --auto-session

# 6. 同步索引 + 下载正文备份
python sync_articles.py --backup

# 7. 仅下载正文备份（使用已有索引）
python sync_articles.py --backup-only
```

---

## 五、与 F4-WeixinPublisher 的关系

本 Skill 从 F4-WeixinPublisher 中拆分而来，专注于文章索引和内容备份。

- **weixin-indexer（本 Skill）**：负责文章索引同步 + 正文备份
- **weixin-publisher（F4）**：负责文章发布，通过读取本 Skill 的 `articles_index.json` 获取扩展阅读候选列表

F4 的 `related_reading.py` 中 `load_articles_index()` 会从本 Skill 的输出路径读取索引文件。

---

## 六、微信 API 参考

| 步骤 | API | 说明 |
|------|-----|------|
| 获取 token | `GET /cgi-bin/token` | 有效期 2h，本地缓存 |
| 获取旧体系文章 | `POST /cgi-bin/material/batchget_material` | type=news，分页拉取旧图文素材 |
| 获取新体系文章 | `POST /cgi-bin/freepublish/batchget` | 仅服务号可用，订阅号返回 48001 |
| 获取全量文章 | `GET mp.weixin.qq.com/cgi-bin/appmsg` | 后台管理接口，需 cookie 认证 |
