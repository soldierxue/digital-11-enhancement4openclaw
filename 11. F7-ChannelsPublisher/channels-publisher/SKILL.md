---
name: channels-publisher
description: >
  将视频文件通过 CDP 浏览器自动化发布到微信视频号创作者中心。
  支持自动上传视频、AI 生成标题/描述/标签、自定义封面、保存草稿或直接发布。
  Activate when: 用户要求发布视频到视频号, 视频号发布, 发布短视频, 上传视频号,
  channels publish, wechat channels, 视频号草稿, 发视频号,
  publish to channels, 视频转视频号。
---

# Channels Publisher — 微信视频号发布

通过 CDP 浏览器自动化将视频发布到微信视频号创作者中心（channels.weixin.qq.com）。

## 前置条件

1. Chrome/Chromium 已启用 Remote Debugging（参见 `2. Chrome_DevTool/README.md`）
2. 用户已在浏览器中登录 channels.weixin.qq.com
3. `pip install websocket-client`

## 执行流程

```
Phase 1: CDP 连接视频号创作者中心
  └── 查找/导航到 channels.weixin.qq.com

Phase 2: 上传视频
  └── DOM.setFileInputFiles 注入视频文件
  └── 轮询等待上传完成（超时 5 分钟）

Phase 3: 填写元数据
  ├── AI 生成标题（≤30字，需 --article 参数）
  ├── AI 生成描述 + #话题标签
  └── 上传自定义封面（可选）

Phase 4: 保存草稿 / 发布
  └── 默认保存草稿，--publish 直接发布
```

## 使用方法

```bash
# 基本用法
python3 main.py /path/to/video.mp4

# 带文章（AI 生成更好的标题/描述）
python3 main.py /path/to/video.mp4 --article /path/to/article.md

# 自定义封面 + 直接发布
python3 main.py /path/to/video.mp4 --cover /path/to/cover.jpg --publish
```

## 选择器维护

视频号创作者中心的前端结构可能随微信更新而变化。
`channels_uploader.py` 中的 `discover_upload_selectors()` 方法可帮助发现新的页面元素。
如果上传或填表失败，运行该方法查看当前页面结构，更新对应选择器。

## 进度汇报

| 节点 | 汇报内容 |
|------|----------|
| Phase 1 完成 | 🔗 已连接视频号创作者中心 |
| Phase 2 完成 | 📹 视频上传完成（文件大小、耗时） |
| Phase 3 完成 | ✍️ 元数据已填写（标题、描述摘要） |
| Phase 4 完成 | ✅ 草稿已保存 / 视频已发布 |
