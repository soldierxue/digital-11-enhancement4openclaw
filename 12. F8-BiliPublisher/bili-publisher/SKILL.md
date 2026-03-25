---
name: bili-publisher
description: >
  将视频文件通过 bilitool 自动投稿到 Bilibili（B站）。
  支持自动上传视频、AI 生成标题/描述/标签、封面上传、分区选择、分P投稿。
  Activate when: 用户要求发布视频到B站, B站投稿, bilibili上传, 发布到哔哩哔哩,
  bilibili publish, bilibili upload, B站发视频, 投稿B站,
  publish to bilibili, 视频转B站。
---

# Bili Publisher — B站视频投稿

通过 bilitool Python 库将视频投稿到 Bilibili。

## 前置条件

1. `pip install bilitool`
2. `bilitool login`（扫码登录，cookie 持久化）
3. Kiro CLI（AI 生成标题/描述/标签，可选）

## 执行流程

```
Phase 1: 检查 bilitool 安装 + 登录状态
Phase 2: AI 生成元数据（标题/描述/标签）
Phase 3: bilitool upload 上传视频
Phase 4: 返回 BV 号 + 视频链接
```

## 使用方法

```bash
# 基本用法（AI 生成元数据）
python3 main.py /path/to/video.mp4 --article /path/to/article.md

# 手动指定
python3 main.py /path/to/video.mp4 --title "标题" --tags "AI,科技" --tid 232

# 分P追加
python3 main.py /path/to/part2.mp4 --append BV1xx411x7xx
```

## 常用分区 tid

| 分区 | tid |
|------|-----|
| 科技杂谈 | 232 |
| 计算机技术 | 231 |
| 软件应用 | 230 |
| 科学科普 | 201 |
| 数码 | 95 |

## 进度汇报

| 节点 | 汇报内容 |
|------|----------|
| Phase 1 完成 | ✓ bilitool 已安装，已登录 |
| Phase 2 完成 | ✍️ 元数据已生成（标题、标签） |
| Phase 3 完成 | 📺 视频上传完成（BV号、链接） |
