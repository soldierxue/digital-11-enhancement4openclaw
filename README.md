# OpenClaw 增强套件 — digital-11-enhancement4openclaw

> 基于 [sample-OpenClaw-on-AWS-with-Bedrock](https://github.com/aws-samples/sample-OpenClaw-on-AWS-with-Bedrock/blob/main/clawdbot-bedrock.yaml) 环境的一系列增强模块与自动化 Skill，将 OpenClaw 从基础 AI 助手升级为具备远程桌面、浏览器自动化、多 Agent 协作、自愈运维能力的全栈个人 AI 工作站。

---

## ⚠️ 环境前提

本项目的所有增强模块均基于以下 AWS 环境搭建：

```
https://github.com/aws-samples/sample-OpenClaw-on-AWS-with-Bedrock/blob/main/clawdbot-bedrock.yaml
```

请先通过该 CloudFormation 模板完成 OpenClaw + Bedrock 的基础部署，确保 OpenClaw Gateway 正常运行后，再按需安装下列增强模块。

> 部分模块可脱离 AWS 环境独立使用，详见下方「非 AWS 环境适用性」章节。

---

## 模块总览

| 编号 | 模块 | 一句话简介 | 核心价值 |
|------|------|-----------|----------|
| 0 | [Base](#0-base--核心增强) | 配置安全防护 · Skill 安全审查 · Bedrock Embeddings 记忆搜索 | 安全基座 |
| 1 | [DCV_on_Ubuntu](#1-dcv_on_ubuntu--远程桌面) | Amazon DCV Server 一键部署，SSM 端口转发安全访问 | 图形桌面 |
| 2 | [Chrome_DevTool](#2-chrome_devtool--浏览器自动化) | Chrome/Chromium 安装 + OpenClaw Browser CDP 集成 + web-article-saver Skill | 浏览器能力 |
| 3 | [KiroCLI](#3-kirocli--kiro-cli-集成) | Kiro CLI 安装登录 · ACP 协议集成 · MCP 扩展（Exa + AWS Docs） | 编码加速，降本 60-80% |
| 4 | [AutoFix](#4-autofix--自愈机制) | systemd OnFailure 自动修复 + 依赖服务健康检查 + HEARTBEAT 主动巡检 | 无人值守运维 |
| 5 | [F1-TechUpdate](#5-f1-techupdate--ai-资讯采集) | tech-updates-collector Skill — 每日 AI 资讯自动采集，6 大主题，增量去重 | 信息输入 |
| 6 | [F2-TechWriter](#6-f2-techwriter--多-agent-协作写作) | tech-updates-writer Skill — Orchestrator Agent 协调的 Phase 0-10 写作流水线 | 内容产出 |
| 7 | [F3-ExpenseDownloader](#7-f3-expensedownloader--发票自动下载) | 浏览器自动化邮箱发票/水单下载，AI 识别分类归档 | 报销自动化 |
| 8 | [F4-WeixinPublisher](#8-f4-weixinpublisher--微信公众号发布) | 博客文章自动发布微信公众号，AI 封面生成，两阶段发布 | 内容分发 |
| 9 | [F5-WexinArchiver](#9-f5-wexinarchiver--微信公众号归档) | 微信公众号文章索引与内容备份，CDP 自动提取 Session | 内容归档 |
| 10 | [F6-Article2Video](#10-f6-article2video--文章转短视频) | 博客文章自动转 3-5 分钟短视频，横竖屏双模板，虚拟人物出镜 | 视频生产 |
| 11 | [F7-ChannelsPublisher](#11-f7-channelspublisher--视频号发布) | CDP 浏览器自动化发布视频到微信视频号创作者中心 | 视频分发 |
| 12 | [F8-BiliPublisher](#12-f8-bilipublisher--b站投稿) | B站 API 自动投稿，AI 生成标题/标签/简介 | 视频分发 |
| 13 | [F9-Article2Podcast](#13-f9-article2podcast--文章转播客) | 博客文章自动转多人对话播客音频，支持 RSS Feed 发布 | 音频生产 |
| 15 | [F11-ViMax-A2V](#15-f11-vimax-a2v--多平台视频流水线) | 一条命令文章转三平台差异化视频，多智能体架构，断点恢复 | 视频流水线 |

---

## 模块详情

### 0. Base — 核心增强

配置安全、Skill 安全审查、记忆搜索三合一基座模块。

- **配置安全防护**：在 MEMORY.md 写入硬规则，修改 `openclaw.json` 前必须查手册、备份、验证 JSON、告知用户
- **skill-vetter 审查**：安装第三方 Skill 前自动扫描 System Prompt Override、权限范围、数据外传、危险命令
- **skill-registry.json**：Skill 来源注册表，HEARTBEAT 心跳时基于 git 检查更新
- **Memory Search**：通过 LiteLLM Proxy 接入 Amazon Nova Multimodal Embeddings，实现语义记忆搜索（~$0.00014/1K tokens，AWS Credits 可抵扣）

### 1. DCV_on_Ubuntu — 远程桌面

在 Ubuntu 24.04 上一键部署 Amazon DCV Server，通过 SSM Port Forwarding 安全访问远程桌面。

- 一键安装脚本 `install-dcv-ubuntu24.sh`，支持 GPU/非 GPU 实例
- 无需开放安全组端口，全程 SSM 加密隧道
- 支持 x86_64 和 ARM64（Graviton）架构
- 为模块 2（Chrome 桌面模式）和模块 7（发票下载）提供图形环境

### 2. Chrome_DevTool — 浏览器自动化

Chrome/Chromium 安装 + OpenClaw Browser 能力配置 + 双 Profile 管理。

- 环境自动检测脚本 `detect-display-env.sh`，智能选择 headed/headless/ARM64 attachOnly 模式
- 一键配置脚本 `setup-devtools-mcp.sh`，自动写入 `openclaw.json` browser 配置
- 双 Profile：`user`（连接用户正在使用的 Chrome）+ `openclaw`（Agent 独立实例）
- 附带 **web-article-saver** Skill：Scrapling + CDP 双引擎网页文章抓取，支持微信公众号防盗链

### 3. KiroCLI — Kiro CLI 集成

将 Kiro CLI 作为 OpenClaw 的 Peer Agent，通过 ACP 协议路由编码任务。

- **ACP 集成**：编码任务路由到 Kiro CLI（独立 Kiro Credits 计费），OpenClaw 每次仅消耗 ~600-2,000 Token 做意图识别，Claude API 用量降低 60-80%
- **MCP 扩展**：Exa Search（高级搜索 + 日期过滤 + 公司调研）+ AWS Documentation Server
- 零依赖 ACP 客户端 `acp_client.py` + 生产级封装 `kiro_bridge.py` + 双轨计费追踪 `usage_tracker.py`

### 4. AutoFix — 自愈机制

基于 systemd 的三层自愈体系，Kiro CLI 替代 Claude Code 降低运维成本。

- **被动修复**：Gateway 60 秒内崩溃 5 次 → OnFailure 触发 → 收集日志 → 检查依赖服务 → Kiro CLI 分析修复
- **依赖服务健康检查**：解析 `openclaw.json` 自动发现 LiteLLM、Chromium 等依赖，HTTP 健康检查 + 自动重启
- **HEARTBEAT 主动巡检**：每 30 分钟检查依赖服务，在 Gateway 崩溃前提前修复
- 修复使用 Kiro Credits 独立计费，不消耗 Claude API Token

### 5. F1-TechUpdate — AI 资讯采集

tech-updates-collector Skill，每日自动采集 AI 领域资讯。

- 6 大主题：OpenClaw、AI 组织架构、Agentic 案例、Agentic 商业、企业 AI、AI 开发生命周期
- 通过 Kiro CLI 调用 Exa MCP `web_search_advanced_exa` 实现日期精确过滤
- 增量追加去重模式：按 URL 去重，多次执行只追加新条目
- 搜索窗口：增量（lastCheck → now），首次/宕机恢复兜底 24h
- 输出 `output/YYYY-MM-DD.md` 结构化日报，供 F2 写作系统消费

### 6. F2-TechWriter — 多 Agent 协作写作

tech-updates-writer Skill（虾群协作写作系统），v2.0 Orchestrator 架构。

- **Orchestrator Agent**：通过 `sessions_spawn` 独立运行，不占用 OpenClaw 主 Agent 资源
- **Phase 0-10 流水线**：话题池 → 选题 → 创作 → 评审 → 修正 → 最终选择 → 发布评估 → GitHub Pages 发布 → 总结 → 质量检查
- **Phase 2-4 流水线并行**：7 批 × 3 篇，同时最多 2 个 Batch 执行，内嵌质量门禁
- **Checkpoint + 断点恢复**：每个 Phase 完成后写入 checkpoint，失败自动重试（最多 3 次），3 次仍失败暂停等待人工介入
- **看门狗监控**：主 Agent 每小时检查 Orchestrator 健康状态，超 3 小时无响应判定僵死
- 预估执行时间从 ~110 分钟优化至 70-80 分钟

### 7. F3-ExpenseDownloader — 发票自动下载

expense-downloader Skill，基于浏览器自动化的邮箱发票/水单下载与分类。

- 支持 Gmail 和 163 邮箱，利用用户已登录的浏览器会话（无需 OAuth/API 配置）
- 4 阶段流程：扫描邮件列表 → AI 语义识别 Expense 邮件 → 下载附件/链接 → 分类归档
- 复用 gmail-invoice-downloader 的搜索关键词体系、决策树、中国发票平台模式
- 自动分类：交通、住宿、餐饮、通讯、办公等，智能重命名 `YYYYMMDD_类型_金额_地点_供应商.pdf`
- 当前状态：设计方案完成，脚本框架已搭建

### 8. F4-WeixinPublisher — 微信公众号发布

weixin-publisher Skill，从博客 URL 或本地 Markdown 自动发布微信公众号图文消息。

- **两阶段发布**：Phase 1 快速出草稿（~10 秒）→ Phase 2 AI 封面生成 + 更新草稿（~2 分钟）
- **AI 封面生成**：Kiro CLI 生成文生图 prompt → Bedrock SD3.5 Large 出图，5 种风格（赛博朋克/科幻/像素/漫画/浮世绘）
- **AI 引言**：Kiro CLI 生成 100 字以内吸引读者的摘要
- **扩展阅读推荐**：从公众号已发布文章中语义匹配 5+ 篇相关历史文章
- **资源去重**：封面/文中图片/草稿均通过 registry 跳过重复上传
- SubAgent 委托执行，不阻塞主 Agent

### 9. F5-WexinArchiver — 微信公众号归档

weixin-indexer Skill，微信公众号文章索引与内容备份。

- 从微信公众号拉取全量已发布文章索引（API + 管理后台双通道）
- 文章正文下载备份为本地 Markdown 文件（readability + html2text）
- CDP 自动提取微信后台 Session（cookie + token），免手动复制
- 文章分类索引、摘要与金句提取
- 为 F4（扩展阅读推荐）和 F6/F11（视频选题）提供数据源

### 10. F6-Article2Video — 文章转短视频

article2video Skill，从博客文章自动生成 3-5 分钟短视频。

- 全流程自动化：文章 → AI 演讲稿 → TTS 语音合成 → 视觉幻灯片渲染 → FFmpeg 合成
- 横屏（1920×1080）和竖屏（720×1280）双模板
- 虚拟人物形象出镜 + Ken Burns 动效 + 5 种结构化数据布局（stats/list/comparison/quote/grid）
- Remotion 渲染引擎 + 原生 JSX 字幕
- SubAgent 委托执行（约 40 分钟），不阻塞主 Agent

### 11. F7-ChannelsPublisher — 视频号发布

channels-publisher Skill，通过 CDP 浏览器自动化发布视频到微信视频号。

- 利用用户已登录的微信视频号创作者中心浏览器会话
- CDP 自动化完成：上传视频 → 填写标题/描述/标签 → AI 生成封面 → 发布
- AI 元数据生成：Kiro CLI 生成标题、描述、标签
- 依赖 DCV 远程桌面 + Chrome headed 模式

### 12. F8-BiliPublisher — B站投稿

bili-publisher Skill，通过 B站 API 自动投稿视频。

- B站 API 投稿：分片上传 → 创建稿件 → AI 生成标题/标签/简介
- AI 元数据生成：Kiro CLI 生成符合 B站风格的标题、标签、简介
- AI 封面生成：Bedrock SD3.5 Large 生成竖版封面
- 支持自定义分区、标签、转载声明

### 13. F9-Article2Podcast — 文章转播客

article2podcast Skill，从博客文章自动生成多人对话播客音频。

- 全流程：文章 → AI 生成多人对话脚本 → TTS 多角色语音合成 → 音频拼接 → 元数据生成
- 支持多角色对话（主持人 + 嘉宾），edge-tts 多声线
- AI 生成播客封面（Bedrock SD3.5 Large）
- RSS Feed 生成，支持 Apple Podcasts / Spotify 等平台分发
- 断点恢复：checkpoint 机制，失败后可从中断处继续

### 15. F11-ViMax-A2V — 多平台视频流水线

vimax-a2v Skill，一条命令将文章转化为微信视频号、B站、小红书三平台差异化视频。

- 整合 F10 十一个版本迭代的最佳实践，重构为多智能体自动化流水线
- ScriptWriter + IllustrationWriter 真正实现的 Agent 层（非 NotImplementedError）
- 多视频风格：Style A（横屏）+ Style B（竖屏）+ Style C（Claude 信息图竖屏）+ B站版
- 断点恢复：`checkpoint.json` + `--resume`，Nova Reel 滑动窗口并发控制
- `run.sh` 环境隔离，一条命令完成全流程

---

## 模块依赖关系

```
                    ┌──────────────┐
                    │  0. Base     │  安全基座（所有模块推荐）
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
  ┌───────────────┐ ┌────────────┐ ┌───────────────┐
  │ 1. DCV_on_    │ │ 3. KiroCLI │ │ 2. Chrome_    │
  │    Ubuntu     │ │            │ │    DevTool    │
  │  (远程桌面)    │ │ (Kiro CLI) │ │  (浏览器)     │
  └───────┬───────┘ └──┬─────┬──┘ └───────┬───────┘
          │            │     │             │
          ▼            ▼     ▼             ▼
  ┌───────────────┐ ┌──────────┐ ┌───────────────┐
  │ 2. Chrome     │ │ 4. Auto  │ │ 9. F5-Weixin  │
  │ (headed 模式)  │ │    Fix   │ │   Archiver    │
  └───────┬───────┘ └──────────┘ │  (公众号归档)  │
          │                      └───────┬───────┘
          │                              │
          ▼                              │
  ┌───────────────┐              ┌───────┴───────┐
  │ 7. F3-Expense │              │ 5. F1-Tech    │
  │  Downloader   │              │    Update     │
  │  (发票下载)    │              │  (资讯采集)    │
  └───────────────┘              └───────┬───────┘
                                         │
          ┌──────────────────────────────┤
          │                              │
          ▼                              ▼
  ┌───────────────┐              ┌───────────────┐
  │ 8. F4-Weixin  │              │ 6. F2-Tech    │
  │  Publisher    │              │    Writer     │
  │ (公众号发布)   │              │  (协作写作)    │
  └───────────────┘              └───────┬───────┘
                                         │
                    ┌────────────────────┤
                    │                    │
                    ▼                    ▼
          ┌───────────────┐    ┌─────────────────┐
          │ 10. F6-A2V    │    │ 13. F9-A2P      │
          │ (文章转视频)   │    │ (文章转播客)     │
          └───────┬───────┘    └─────────────────┘
                  │
          ┌───────┼───────┐
          │       │       │
          ▼       ▼       ▼
  ┌────────┐ ┌────────┐ ┌─────────────────┐
  │11. F7  │ │12. F8  │ │ 15. F11-ViMax   │
  │视频号   │ │ B站    │ │  (多平台流水线)  │
  └────────┘ └────────┘ └─────────────────┘
```

**关键依赖链**：

| 依赖路径 | 说明 |
|----------|------|
| 1 → 2 (headed) | DCV 远程桌面为 Chrome headed 模式提供图形环境 |
| 3 → 4 | AutoFix 使用 Kiro CLI 作为自动修复引擎 |
| 3 → 5 | F1 采集通过 Kiro CLI 调用 Exa MCP 搜索 |
| 2 → 9 | F5 归档通过 CDP 自动提取微信后台 Session |
| 9 → 8 | F4 微信发布的扩展阅读功能读取 F5 的文章索引 |
| 5 → 6 | F2 写作系统的素材来源完全依赖 F1 采集的日报 |
| 3 + 6 → 8 | F4 微信发布依赖 Kiro CLI（AI 引言/封面）+ F2 产出的文章 |
| 6 → 10 | F6 视频生产消费 F2 写作产出的博客文章 |
| 6 → 13 | F9 播客生产消费 F2 写作产出的博客文章 |
| 10 → 11 | F7 视频号发布消费 F6 生成的视频 |
| 10 → 12 | F8 B站投稿消费 F6 生成的视频 |
| 10 → 15 | F11 ViMax 整合 F6 能力，一条命令输出三平台视频 |
| 1 + 2 → 7 | F3 发票下载需要 DCV 桌面 + Chrome CDP 能力 |
| 1 + 2 → 11 | F7 视频号发布需要 DCV 桌面 + Chrome CDP 能力 |

> 模块 2 的 headless 模式不依赖模块 1，可在无桌面服务器上独立运行。

---

## 非 AWS 环境适用性

以下评估各模块在非 AWS OpenClaw 环境（如本地 Mac/Linux、其他云平台）中的可用性：

| 模块 | 适用性 | 说明 |
|------|--------|------|
| 0. Base | ⚠️ 部分可用 | skill-vetter 审查、配置安全规则完全可用；Memory Search 需替换 Bedrock Embeddings 为其他 Embedding 提供商（OpenAI、Cohere 等），LiteLLM Proxy 本身支持多后端 |
| 1. DCV_on_Ubuntu | ❌ AWS 专属 | Amazon DCV 仅在 EC2 上免费使用；替代方案：VNC、noVNC、RDP、Tailscale 等远程桌面 |
| 2. Chrome_DevTool | ✅ 完全可用 | Chrome 安装、CDP 配置、双 Profile、web-article-saver 均不依赖 AWS |
| 3. KiroCLI | ✅ 完全可用 | Kiro CLI、ACP 协议、Exa MCP、AWS Docs MCP 均为独立工具 |
| 4. AutoFix | ⚠️ 部分可用 | systemd 自愈机制 + Kiro CLI 修复完全可用；依赖服务健康检查需根据实际部署调整服务名 |
| 5. F1-TechUpdate | ✅ 完全可用 | 仅依赖 Kiro CLI + Exa MCP，与云平台无关 |
| 6. F2-TechWriter | ✅ 完全可用 | 纯 Agent 协作流水线，不依赖任何 AWS 服务 |
| 7. F3-ExpenseDownloader | ⚠️ 需要桌面 | 需要任意图形桌面 + Chrome CDP，不限于 DCV；Mac/Linux 本地桌面即可 |
| 8. F4-WeixinPublisher | ⚠️ 部分可用 | Kiro CLI + 微信 API 不依赖 AWS；AI 封面生成依赖 Bedrock SD3.5（可替换为其他文生图 API） |
| 9. F5-WexinArchiver | ✅ 完全可用 | 微信 API + CDP Session 提取，不依赖 AWS |
| 10. F6-Article2Video | ⚠️ 部分可用 | Remotion + FFmpeg + TTS 不依赖 AWS；AI 演讲稿生成可用 LiteLLM 切换后端；AI 生图依赖 Bedrock（可替换） |
| 11. F7-ChannelsPublisher | ⚠️ 需要桌面 | 需要图形桌面 + Chrome CDP；Mac/Linux 本地桌面即可 |
| 12. F8-BiliPublisher | ✅ 完全可用 | B站 API + Kiro CLI，不依赖 AWS；封面生成依赖 Bedrock（可替换） |
| 13. F9-Article2Podcast | ✅ 完全可用 | edge-tts + FFmpeg，不依赖 AWS；封面生成依赖 Bedrock（可替换） |
| 15. F11-ViMax-A2V | ⚠️ 部分可用 | 核心流程不依赖 AWS；Nova Reel 视频片段和 AI 生图依赖 Bedrock |

**快速上手建议（非 AWS 环境）**：
1. 从模块 3（KiroCLI）开始，获得 ACP 编码加速能力
2. 安装模块 2（Chrome_DevTool）的 headless 模式，获得浏览器自动化
3. 安装模块 5 + 6（F1 + F2），搭建 AI 资讯采集 → 写作的完整流水线
4. 安装模块 8 + 9（F4 + F5），实现博客文章 → 微信公众号的自动发布
5. 安装模块 10 + 13（F6 + F9），将文章转化为短视频和播客音频

---

## 目录结构

```
digital-11-enhancement4openclaw/
├── README.md                          # 本文件
├── 0. Base/                           # 核心增强（配置安全 · Skill 审查 · 记忆搜索）
├── 1. DCV_on_Ubuntu/                  # Amazon DCV 远程桌面部署
├── 2. Chrome_DevTool/                 # Chrome + CDP + web-article-saver
├── 3. KiroCLI/                        # Kiro CLI 安装 · ACP · MCP
├── 4. AutoFix/                        # systemd 自愈 + 依赖健康检查
├── 5. F1-TechUpdate/                  # AI 资讯采集 Skill
├── 6. F2-TechWriter/                  # 多 Agent 协作写作 Skill
├── 7. F3-ExpenseDownloader/           # 发票自动下载 Skill
├── 8. F4-WeixinPublisher/             # 微信公众号自动发布 Skill
├── 9. F5-WexinArchiver/              # 微信公众号文章索引与备份 Skill
├── 10. F6-Article2Video/              # 博客文章转短视频 Skill
├── 11. F7-ChannelsPublisher/          # 微信视频号自动发布 Skill
├── 12. F8-BiliPublisher/              # B站视频自动投稿 Skill
├── 13. F9-Article2Podcast/            # 博客文章转播客 Skill
└── 15. F11-ViMax-A2V/                 # 多平台视频流水线 Skill
```

每个模块目录下的 `README.md` 均为 Agent 可执行文档（供 OpenClaw 读取并自动执行），包含完整的环境检测、分阶段安装、幂等性保证和故障排查。

---

## 设计原则

- **幂等性**：所有操作执行前先检查状态，已存在的配置只验证不重复写入
- **分阶段执行**：每个模块拆分为多个阶段，每阶段完成后汇报结果再继续
- **先诊断后执行**：不跳过环境检查直接修改配置
- **高质量不降级**：失败 → 重试 → 仍失败 → 暂停等待人工介入，不做降级处理
- **独立 Agent 协调**：长流程任务（如 F2 写作）由 Orchestrator Agent 独立执行，不占用主 Agent 资源

---

**版本**: v2.0
**更新时间**: 2026-04-04
