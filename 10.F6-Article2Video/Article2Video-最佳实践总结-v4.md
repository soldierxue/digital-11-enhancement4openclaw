# Article2Video — 最佳实践总结 v4

> 更新于 2026-04-26，新增 Ken Burns 背景图铺满修复（D5）+ 图片风格一致性优化

## 完整管道架构

```
博客文章 (.md / URL)
  │
  ├─ Phase 1: 内容拆分（AI）
  │    └─ 文章 → 10 段演讲稿 + 结构化数据（key_facts）
  │    └─ 输出: speech-script.json
  │
  ├─ Phase 2A: 语音合成 + 逐词时间戳（并行）
  │    └─ Edge TTS (zh-CN-YunyangNeural, rate=-5%)
  │    └─ 输出: audio/slide-{01-10}.mp3 + slide-{01-10}.json + timing.json
  │
  ├─ Phase 2B: 视觉素材（并行）
  │    ├─ 方案 A（推荐）: Unsplash 真实照片（$0）
  │    ├─ 方案 B: Bedrock Nova Canvas AI 生图（$0.08/张）
  │    └─ 输出: images/slide-{01-10}.jpg
  │
  ├─ Phase 3: 字幕生成
  │    └─ 主方案: TTS 逐词时间戳 + 原文拼接（零错别字，<1秒）
  │    └─ 备选: whisper.cpp 语音识别（有同音字错误风险，~8分钟）
  │    └─ 输出: subtitles.json
  │
  ├─ Phase 4: 视频渲染（Remotion）
  │    └─ 双模板：横屏 1920×1080 + 竖屏 720×1280
  │    └─ 五层合成：背景图(Ken Burns) + 暗叠层 + 结构化内容 + 字幕 + 虚拟人物
  │    └─ 输出: output.mp4
  │
  └─ Phase 5: 压缩与交付
       └─ FFmpeg CRF 压缩至 ≤20MB
       └─ 输出: output-compressed.mp4
```

## 结构化数据内容（v4 新增，方案 A）

### 设计理念

之前的通用模板正文 slides 只有「照片 + 标题 + 字幕」，信息密度低，观众只能听不能看。方案 A 在 Phase 1 拆分时让 AI 额外输出每个 slide 的结构化数据（`key_facts`），Remotion 模板根据数据类型自动选择视觉布局。

### key_facts 数据格式

```json
{
  "slide": 2,
  "title": "传统开发模式已过时",
  "speech": "...",
  "visual": "...",
  "key_facts": {
    "type": "stats",
    "items": [
      {"value": "1.2亿", "label": "年化 Sales Pipeline", "color": "#22d3ee"},
      {"value": "90%", "label": "试点项目用错误方法", "color": "#fb923c"},
      {"value": "29,000", "label": "Agentforce 签约数", "color": "#4ade80"}
    ]
  }
}
```

### 五种布局类型

| 类型 | 用途 | items 结构 | 最佳数量 |
|------|------|-----------|---------|
| **stats** | 大数字卡片 | `{value, label, color}` | 2-4 个 |
| **list** | 图标列表 | `{icon, title, desc, color}` | 3-5 条 |
| **comparison** | A vs B 对比 | `{left, right, label}` | 2-4 行 |
| **quote** | 关键引言 | `{text, source}` | 1 条 |
| **grid** | 2×2 概念网格 | `{icon, title, desc, color}` | 4 个 |

### 布局渲染风格

**通用卡片样式**：
```css
background: rgba(10, 14, 39, 0.75);
border-radius: 16px;
padding: 20px 24px;
backdrop-filter: blur(8px);
```

**stats 数字卡片**：
- 数字：60px 加粗 + 主题色 + `text-shadow: 0 0 20px {color}40`
- 标签：16-18px，`rgba(255,255,255,0.6)`
- 水平排列，等宽分栏

**list 图标列表**：
- 左侧彩色边框：`border-left: 4px solid {color}`
- emoji icon 40px + 标题 21px 粗体 + 描述 16px
- 垂直堆叠，间距 24px

**comparison 对比视图**：
- 左右两列（A vs B），中间分隔线
- 左侧旧/前，右侧新/后
- 对比色：红/灰 vs 绿/青

**quote 引言**：
- 大引号装饰（80px 半透明）
- 引言文字：28px 斜体
- 来源：16px 灰色

**grid 2×2 网格**：
- `display: grid; grid-template-columns: 1fr 1fr; gap: 20px`
- 每格带彩色边框和 emoji icon

### 布局区域约束

**横屏**：内容区 padding-right 预留 300px 给右下角人物出镜
**竖屏**：内容区 padding-bottom 预留 350px 给底部字幕和人物

### Phase 1 Prompt 改动

split_article.py 的 AI Prompt 新增：

```
每个 slide 必须包含 key_facts 字段（第 1 个和最后一个 slide 除外），格式如下：
- type: 从 stats/list/comparison/quote/grid 中选择最匹配当前内容的类型
- items: 从演讲文本中提取具体的数据点、事实、对比项
  - stats: [{value: "数字", label: "说明", color: "#hex"}]  // 2-4个
  - list: [{icon: "emoji", title: "标题", desc: "描述", color: "#hex"}]  // 3-5条
  - comparison: [{left: "A", right: "B", label: "维度"}]  // 2-4行
  - quote: [{text: "引言内容", source: "来源"}]  // 1条
  - grid: [{icon: "emoji", title: "标题", desc: "描述", color: "#hex"}]  // 4个

选择原则：
- 有具体数字 → stats
- 有多个并列要点 → list
- 有前后/AB对比 → comparison
- 有名人名言或关键判断 → quote
- 有4个并列维度/概念 → grid
颜色推荐：#22d3ee(青), #fb923c(橙), #4ade80(绿), #f87171(红), #60a5fa(蓝), #c084fc(紫), #facc15(黄)
```

## 虚拟人物形象方案

### 素材

| 素材 | 路径 | 尺寸 | 用途 |
|------|------|------|------|
| 半身像（rembg 抠图）| `assets/avatar/presenter-half-nobg.png` | 727×1290 | 片头卡片 + 正文出镜 |
| 半身像原图 | `assets/avatar/presenter-half-original.jpg` | 727×1290 | 备份 |
| 坐姿全身（抠图）| `assets/avatar/presenter-sitting-nobg.png` | 1079×1434 | 备用 |
| 坐姿全身原图 | `assets/avatar/presenter-sitting-original.jpg` | 1079×1434 | 备份 |

**抠图方案**: `rembg`（u2net 深度学习模型）>> 像素阈值抠图

### 横屏方案（landscape, 1920×1080）

**五层合成 + 三段式结构**：

| Slide | 模式 | 层次 |
|-------|------|------|
| 第 1 个（片头）| 模式 1 | 深色背景 + 虚拟白板(标题) + 半身人物 |
| 第 2 到 N-1（正文）| 模式 3 v3 | 照片(Ken Burns) + 暗叠层 + 结构化内容 + 字幕 + 人物出镜 |
| 第 N 个（片尾）| 模式 1 | 深色背景 + 结束语 + 半身人物 |

**模式 1 虚拟白板参数**：
- 尺寸: 880×560，圆角 12px
- 外框: `rgba(160, 210, 235, 0.63)` 2px
- 外发光: 12 层 `rgba(140, 220, 245)` 渐变
- 四角光点: 半径 6px
- 面板渐变: `rgb(238,242,250)` → `rgb(246,248,246)`
- 底部金属夹: 30×8px
- 倾斜: -1.5°
- 文字: 标题 62-68pt Bold / 副标题 36-44pt / 品牌 26-30pt

**模式 3 v3 正文出镜**：
- 人物高度: ~280px（横屏）/ ~320px（竖屏）
- 位置: 右下角，opacity 0.85
- 阴影: `drop-shadow(0 2px 12px rgba(0,0,0,0.6))`

### 竖屏方案（portrait, 720×1280）
- 全程模式 3 v3 + 结构化内容
- 内容区上方，字幕和人物在下方

## 开场白定制（v4 新增）

**标准开场白**：
> 大家好，我是薛以致用，科技有深度，职场有办法，管理有温度，更多内容请关注公众号军见数科。

Phase 1 拆分时 Prompt 中固定第一段 speech 的开头为此标准开场白。

**配置方式**（config.json）：
```json
{
  "opening_line": "大家好，我是薛以致用，科技有深度，职场有办法，管理有温度，更多内容请关注公众号军见数科。",
  "branding": "薛以致用 · AI 洞察",
  "channel_name": "军见数科"
}
```

## 各阶段关键参数与踩坑

### Phase 1: 内容拆分

**输入**: Markdown 文章（3000-7000 字）
**输出**: `speech-script.json` — 10 段演讲脚本 + 结构化数据

```json
[
  {
    "slide": 1,
    "title": "Salesforce ADLC",
    "speech": "大家好，我是薛以致用，科技有深度...",
    "visual": "Salesforce 办公大楼",
    "key_facts": null
  },
  {
    "slide": 2,
    "title": "传统开发模式已过时",
    "speech": "你知道现在90%的AI Agent产品...",
    "visual": "coding vs AI agent",
    "key_facts": {
      "type": "stats",
      "items": [
        {"value": "1.2亿", "label": "年化 Sales Pipeline", "color": "#22d3ee"},
        {"value": "90%", "label": "用错误方法", "color": "#fb923c"}
      ]
    }
  }
]
```

### Phase 2A: 语音合成 + 时间戳 (Edge TTS)

**关键**：`edge_tts 7.x` 必须显式传 `boundary="WordBoundary"`，默认是 SentenceBoundary。
- offset/duration 单位: 100 纳秒，除以 10000 转毫秒
- 用 `communicate.stream()` 不能用 `communicate.save()`

### Phase 2B: 视觉素材

推荐 Unsplash 真实照片。AI 生图文字乱码，叙事连贯性差。

#### 图片风格一致性优化（D5 新增）

**问题**：之前 `fetch_images.py` 为每张 slide 独立生成 Unsplash URL，没有全局视觉约束，导致 10 张图风格、色调、主题跳跃很大。

**解决方案**：在 AI prompt 中注入文章主题上下文 + 全局风格一致性要求：

- **统一色调**：要求所有图片共享相似的主色调（如都是冷蓝科技风或暖琥珀色调），避免混搭不同色温
- **统一主题域**：限定在文章领域内选图（如芯片文章只选数据中心/电路板/服务器），不混入无关素材
- **统一摄影风格**：保持相似的光影氛围和构图风格，避免微距和航拍随机混搭
- **叙事流畅性**：相邻 slide 的视觉过渡要自然

同样的优化也应用到了 `generate_ai_images.py`（AI 生图模式）：先用 AI 根据整篇文章定义统一的色彩/画风/光影/视觉母题，再将这个 style 前缀注入到每张图的 prompt 中。

### Phase 3: 字幕生成

TTS 逐词时间戳 + 原文直出 = 零错别字，<1 秒生成。Whisper 降为备选。

### Phase 4: 视频渲染 (Remotion)

**双模板 + 结构化内容**：

| 模板 | Composition ID | 分辨率 | 内容层 |
|------|---------------|--------|--------|
| 横屏 | `AgentVideo` | 1920×1080 | 片头白板 + 结构化内容 + 人物出镜 |
| 竖屏 | `AgentVideoPortrait` | 720×1280 | 结构化内容 + 人物出镜 |

#### ⚠️ Ken Burns 背景图铺满问题（D5 踩坑记录）

**问题现象**：竖屏模板中，部分 slide 的 16:9 背景图（1920×1080）没有铺满 9:16 画布（720×1280），图片缩成一小块浮在中间，而其他 slide 正常铺满。同样的代码、同样尺寸的图片，不同 slide 表现不一致。

**排查过程**：

1. 最初怀疑 Remotion `<Img>` 的 `objectFit: 'cover'` 不生效 → 换 `background-image` + `background-size: cover` → 仍然不一致
2. 交换两个 slide 的图片文件 → 问题跟着 slide index 走，不跟图片走 → 排除图片本身的问题
3. 去掉 CSS `transform` 后所有 slide 都 100% 铺满 → 确认 `transform` 是罪魁祸首
4. 硬编码 `width: 2276, height: 1280` 无 transform → 100% 铺满 → 确认 `<Img>` 本身没问题
5. 恢复动态计算的 `interpolate()` 值 → 部分 slide 又出问题 → 定位到浮点精度

**根因**：

Ken Burns 动效使用 `transform: scale(N) translate(Xpx, Ypx)` 实现缩放和平移。在 Remotion 的 headless Chrome 中，`transform` 会导致以下问题：

- **浮点精度**：当 zoom 最小值为 1.0 时，`interpolate()` 在某些帧返回 0.9999... 而非 1.0，导致 `imgH = Math.round(1280 * 0.9999) = 1279`，产生 1px 间隙
- **transform 与 background-size 冲突**：CSS `transform: scale()` 改变元素的视觉尺寸但不改变布局尺寸，`background-size: cover` 基于布局尺寸计算，导致缩放后图片不再覆盖可视区域
- **translate 导致露边**：`translate()` 将整个元素（包括 overflow:hidden 容器）移动，导致部分画布区域没有图片覆盖
- **不同 slide 表现不一致**：不同 Ken Burns 方向（dirs 数组的 5 种模式）的 scale/translate 组合不同，某些组合恰好不触发问题（如 scale 始终 ≥ 1.05），某些组合在 scale 接近 1.0 时暴露问题

**解决方案（D5 定稿）**：

完全放弃 CSS `transform`，改用 `<Img>` 的像素级 `width/height/top/left` 直接定位：

```jsx
function KenBurnsImage({src, durationFrames, index}) {
  const {width: compW, height: compH} = useVideoConfig();
  const progress = frame / durationFrames;
  const imgAspect = 16 / 9;

  // 1. zoom 最小值 1.02（不是 1.0），避免浮点精度导致 imgH < compH
  const dirs = [
    {zf: 1.02, zt: 1.08, panXf: 0.50, panXt: 0.48, panYf: 0.50, panYt: 0.48},
    // ... 5 种方向
  ];

  // 2. interpolate 加 clamp 防止外推
  const zoom = interpolate(progress, [0, 1], [d.zf, d.zt],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // 3. cover 基线：匹配容器高度，宽度溢出
  const baseH = compH;
  const baseW = Math.ceil(baseH * imgAspect);  // ceil 确保 ≥ 需要的宽度

  // 4. Math.ceil 确保图片尺寸始终 ≥ 容器
  const imgW = Math.ceil(baseW * zoom);
  const imgH = Math.ceil(baseH * zoom);

  // 5. Math.floor 确保负偏移足够大（不会露出右/下边缘）
  const overflowX = imgW - compW;
  const overflowY = imgH - compH;
  const left = Math.floor(-(overflowX * panX));
  const top = Math.floor(-(overflowY * panY));

  // 6. 不用 transform，直接像素定位
  return (
    <div style={{position: 'absolute', top: 0, left: 0,
                 width: compW, height: compH, overflow: 'hidden'}}>
      <Img src={src} style={{
        position: 'absolute', top, left, width: imgW, height: imgH,
      }} />
    </div>
  );
}
```

**关键约束**：
- zoom 最小值必须 > 1.0（推荐 1.02），绝不能等于 1.0
- pan 范围 0.48-0.52（保守），确保在最小 zoom 下不露边
- 必须用 `Math.ceil` / `Math.floor` 消除亚像素间隙
- 必须用 Remotion `<Img>`（不能用原生 `<img>` 或 CSS `background-image`），因为 `<Img>` 内部有 `delayRender` 保证图片加载完成后才截图

**渲染性能（ARM64 c7g.large）**：

| 对比 | 横屏 1920×1080 | 竖屏 720×1280 |
|------|---------------|---------------|
| 渲染速度 | ~8 fps (~27 分钟) | ~13 fps (~14 分钟) |
| 原始文件 | ~80-110MB | ~30-50MB |

### Phase 5: 压缩

```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -profile:v baseline -level 3.1 -pix_fmt yuv420p \
  -crf 28 -preset medium \
  -c:a aac -b:a 96k -ar 44100 \
  output-compressed.mp4
```

## 版本迭代经验

| 版本 | 方案 | 改进 |
|------|------|------|
| A | FFmpeg 静态拼接 | → B |
| B | Remotion + AI 图 | → C |
| C | Remotion + 照片 + Slidev 叠层 | → D |
| D | 原生 JSX + TTS 字幕 | → D2 |
| D2 | + 竖屏模板 | → D3 |
| D3 | + 虚拟人物形象（片头白板 + 正文出镜）| → D4 |
| D4 | + 结构化数据内容 + 标准开场白 | → D5 |
| **D5 ✅** | **+ Ken Burns 像素定位修复 + 图片风格一致性** | **当前版本** |

**关键洞察**：
1. **原生 JSX >> PNG 叠层** — 清晰度质的飞跃
2. **真实照片 >> AI 生图** — 叙事性和自然度
3. **TTS 时间戳 >> whisper** — 零错别字 + 省时 8 分钟
4. **竖屏独立设计** — 布局必须重排
5. **虚拟白板代码绘制 >> 原图写字** — 完全可控
6. **rembg >> 像素阈值** — 深色背景下差距巨大
7. **结构化数据 >> 纯标题** — 信息密度翻倍，观众能"看到"数据（v4 新增）
8. **AI 自动选布局 >> 手动 Slidev** — 全自动，无需人工排版（v4 新增）
9. **像素定位 >> CSS transform** — Remotion headless Chrome 中 transform 对 `<Img>` 的渲染不一致，zoom 最小值必须 > 1.0 避免浮点精度问题（D5 新增）
10. **全局风格约束 >> 逐张独立选图** — 在 AI prompt 中注入文章主题上下文，确保 10 张图色调/主题/风格统一（D5 新增）

## 成本与耗时

| 项目 | 成本 | 耗时 |
|------|------|------|
| AI 拆分演讲稿 + key_facts | ~$0.08 (Claude) | 45 秒 |
| Edge TTS 语音 + 时间戳 | $0 | 1 分钟 |
| 照片下载 | $0 | 15 秒 |
| TTS 字幕生成 | $0 | <1 秒 |
| Remotion 渲染（横屏） | $0 | 27 分钟 (ARM64) |
| Remotion 渲染（竖屏） | $0 | 14 分钟 (ARM64) |
| FFmpeg 压缩 | $0 | 2 分钟 |
| **总计（横屏）** | **$0.08** | **~31 分钟** |
| **总计（竖屏）** | **$0.08** | **~18 分钟** |
| **总计（双版本）** | **$0.08** | **~45 分钟** |

## Skill 文件结构

```
~/.openclaw/skills/article2video/
├── SKILL.md                              ← 主文档
├── main.py                               ← 主入口
├── config.json                           ← 默认配置（含开场白、品牌）
├── requirements.txt                      ← Python 依赖
├── assets/
│   └── avatar/
│       ├── presenter-half-nobg.png       ← 半身像 rembg 抠图
│       ├── presenter-half-original.jpg
│       ├── presenter-sitting-nobg.png    ← 坐姿全身（备用）
│       └── presenter-sitting-original.jpg
├── scripts/
│   ├── split_article.py                  ← Phase 1: AI 拆分 + key_facts 提取
│   ├── generate_audio.py                 ← Phase 2A: TTS + 时间戳
│   ├── fetch_images.py                   ← Phase 2B: Unsplash 照片
│   ├── generate_ai_images.py             ← Phase 2B 备选: AI 生图
│   ├── extract_subtitles.py              ← Phase 3: 字幕
│   ├── prepare_remotion.py               ← Phase 4 前置: data.json（含 key_facts）
│   └── compress_video.py                 ← Phase 5: 压缩
└── remotion-template/
    ├── package.json
    ├── src/
    │   ├── index.js
    │   ├── Root.jsx                      ← 双 Composition 注册
    │   ├── VideoComposition.jsx          ← 横屏（片头白板 + 结构化内容 + 人物）
    │   └── VideoCompositionPortrait.jsx  ← 竖屏（结构化内容 + 人物）
    └── public/
        └── presenter-half.png
```

## CLI 用法

```bash
# 横屏（电脑/大屏）
python3 main.py ./article.md --format landscape

# 竖屏（手机/短视频）
python3 main.py ./article.md --format portrait

# 双版本
python3 main.py ./article.md --format both

# 自定义
python3 main.py ./article.md --format both --style photo --slides 10 --voice zh-CN-YunyangNeural
```

## 迭代历程总览

### 抠图迭代（v1→v13）

| 版本 | 思路 | 结论 |
|------|------|------|
| v1-v6 | 在原图白板上写字 | ❌ 透视对齐困难 |
| v7-v8 | 虚拟白板 + rembg 连白板一起抠 | ❌ |
| v9 | 裁切分离 + 阈值抠图 | ⚠️ 边缘粗糙 |
| v10-v12 | 新形象 + 阈值抠图 | ⚠️ 白色残留 |
| **v13 ✅** | **rembg 抠图 + 虚拟白板** | **✅ 定稿** |

### 视频管道迭代（A→D4）

| 版本 | 方案 | 核心改进 |
|------|------|---------|
| A | FFmpeg 硬切 | 基础版 |
| B | Remotion + AI 图 | Ken Burns 动效 |
| C | + Slidev 叠层 | 结构化文本（手动） |
| D | 原生 JSX | 清晰度飞跃 |
| D2 | + 竖屏模板 + TTS 字幕 | 零错别字 |
| D3 | + 虚拟人物形象 | 品牌感 |
| D4 | + 结构化数据(自动) + 开场白 | 信息密度 + 品牌统一 |
| **D5 ✅** | **+ Ken Burns 像素定位 + 图片风格一致性** | **竖屏铺满修复 + 视觉连贯** |
