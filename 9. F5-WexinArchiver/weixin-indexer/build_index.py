#!/usr/bin/env python3
"""
重建 文章分类索引.md，在分类表格中为每篇文章增加
到 文章摘要与金句.md 对应锚点的链接。

用法: python3 build_index.py
"""
import os
import re
import json
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUOTES_FILE = os.path.join(BASE_DIR, "文章摘要与金句.md")
INDEX_FILE = os.path.join(BASE_DIR, "articles_index.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "文章分类索引.md")


def make_anchor(heading_text):
    """
    将 Markdown 二级标题文本转为 GitHub/VSCode 兼容的锚点 ID。
    规则: 小写, 空格转-, 去除特殊字符(中文保留), 去除连续-
    """
    text = heading_text.strip().lower()
    # 去除 markdown 格式
    text = re.sub(r'[*_`]', '', text)
    # 保留中文、字母、数字、空格、连字符
    result = []
    for ch in text:
        if ch == ' ':
            result.append('-')
        elif ch == '-':
            result.append('-')
        elif ch.isalnum() or unicodedata.category(ch).startswith('Lo'):
            # Lo = Letter, other (包括中文)
            result.append(ch)
        # 其他字符跳过
    anchor = ''.join(result)
    # 去除连续 -
    anchor = re.sub(r'-+', '-', anchor)
    anchor = anchor.strip('-')
    return anchor


def build_anchor_map():
    """从 文章摘要与金句.md 中提取所有二级标题，建立 (标题前缀, 日期) -> 锚点 的映射。"""
    anchor_map = {}
    with open(QUOTES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('## '):
                # 格式: ## 1. 标题（日期）
                heading = line[3:].strip()
                anchor = make_anchor(heading)

                # 提取标题和日期
                m = re.match(r'\d+\.\s*(.+?)（(\d{4}-\d{2}-\d{2})）', heading)
                if m:
                    title = m.group(1).strip()
                    date = m.group(2)
                    # 用标题前10字+日期作为key
                    key = f"{title[:10]}|{date}"
                    anchor_map[key] = anchor
                    # 也用完整标题
                    anchor_map[f"{title}|{date}"] = anchor

    return anchor_map


def find_anchor(title, date, anchor_map):
    """查找文章对应的锚点。"""
    # 精确匹配
    key = f"{title}|{date}"
    if key in anchor_map:
        return anchor_map[key]
    # 前缀匹配
    key = f"{title[:10]}|{date}"
    if key in anchor_map:
        return anchor_map[key]
    # 模糊匹配
    for k, v in anchor_map.items():
        k_title = k.split('|')[0]
        k_date = k.split('|')[1] if '|' in k else ''
        if k_date == date and (k_title[:8] in title or title[:8] in k_title):
            return v
    return None


# ============================================================
# 文章分类定义
# 每个分类: (分类名, 描述, 匹配函数)
# 匹配函数接收 (title, digest, date) 返回 True/False
# ============================================================

def kw_match(title, digest, keywords):
    text = (title + ' ' + digest).lower()
    return any(k.lower() in text for k in keywords)


CATEGORIES = [
    {
        'name': '科技（AI/芯片/云计算/前沿技术）',
        'keywords': [
            'AI', 'Agent', 'GPT', 'LLM', '大模型', '芯片', 'GPU', 'Trainium',
            'NVIDIA', '黄仁勋', 'OpenAI', 'Anthropic', 'Claude', 'DeepSeek',
            'Sora', 'Token', '推理', '训练', 'Transformer', '注意力机制',
            'GenAI', 'Agentic', '智能体', '机器人', 'MWC', 'GTC',
            'OpenClaw', 'Clawdbot', 'Kiro', 'MCP', 'Bedrock',
            'Apple', 'Meta', 'Manus', 'Perplexity', 'LangChain', 'AutoGPT', 'CrewAI',
            'GEO', '生成式', 'RDMA', 'SRD', 'RoCE', 'EFA',
            'Blackwell', 'GB200', 'H100', 'CPU', 'RISC-V',
            '数据中心', '算力', '电力', '多云', 'Interconnect',
            'Suno', 'NotebookLM', 'Gemini', 'DiT', 'Mooncake',
            'K2', 'MoonShot', '推荐系统', 'OneRec',
            'A16Z', '纳德拉', 'Notion CEO',
        ],
    },
    {
        'name': '职场（职业发展/个人成长/职场感悟）',
        'keywords': [
            '职场', '职业', '感悟', '反思', '成长', '心路',
            '十年', '八年', '五年', '四年', '两年', 'Last Day',
            '裁员', '出发', '再次出发', '工程师', '分化', '突围',
            '政治', '囚徒', '生存', '摸鱼', '探索指南',
            '低处飞行', '飞蓬', '且尽手中杯', '熵增',
            'Meta 职场', '西游记', '梯子怎么爬',
            '招聘', '架构师团队',
        ],
    },
    {
        'name': '管理（组织管理/领导力/企业战略）',
        'keywords': [
            '管理', '领导力', '战略', '组织', 'CEO', 'CFO',
            'S-Team', '亚马逊组织', '底层原则', '数据辅助决策',
            '研发效能', '快手万人', 'Rewired', '数智化转型',
            '领导力不是', '战略是研究', '敢问路在何方',
            '克伯勒-罗斯', '变革', '1 on 1', '反馈管理',
            '学习型管理', '最佳实践', '良好的愿望',
            'Builder Experience', '开发者体验',
            'Notion CEO', '重塑', '未来工作',
        ],
    },
    {
        'name': '案例（企业案例/财报分析/行业分析）',
        'keywords': [
            '财报', 'Walmart', 'Amazon', 'TikTok', 'Shopify',
            'Google Cloud', 'Snowflake', 'Databricks',
            '阿里', '快手', '携程', '货拉拉', '美团', '蒙牛',
            'Airbnb', 'Mercado', 'SEA', 'Block',
            '零售', '电商', 'FBA', 'DTC', 'PrimeDay',
            '收购', 'Manus', '智谱', '车展', '汽车',
            '云厂商', '增长', '市值', '营收',
            '腾讯云', 'Google云', '删库',
            '字节', '女装', '独立站',
            'Anthropic Enterprise',
        ],
    },
    {
        'name': '动手实践（技术实操/工具体验/教程）',
        'keywords': [
            '一周一练', '动手', '体验', '教程', '保姆级',
            '初体验', 'Battle', '代码编写', '自动执行',
            'Claude3 可以帮助', '架构图', 'PPT',
            'MCP 搭建', 'VSCode', 'Cline',
            '报销', '偷懒', '网站',
            'Lambda 支持容器', 'EMR', 'Spark',
            'S3 CLI', '红包封面', 'SunoAI',
            'ChatGPT 的', '如何使用',
            'Kiro CLI Bot', 'OpenClaw快速创造',
            '虾群协作', '血泪史',
            'DeepSeek-R1', '部署和优化',
            '入门', '生成式 AI 如何入门',
        ],
    },
    {
        'name': '架构与云原生（系统架构/可靠性/成本优化/云基础设施）',
        'keywords': [
            '架构', '可靠性', '韧性', '故障', '高可用',
            '俭约', 'FinOps', '成本', '降本', '流量成本',
            '容量管理', '精益', '缓存', '事务',
            'Werner', 'CTO', 'Spanner', 'DynamoDB',
            'S3', '强一致性', '时钟同步', '微秒',
            '云原生', 'Proton', 'OAM', 'CDN',
            'TCP', '边缘', '加速', '带宽',
            '转码', '混沌工程', '事件驱动',
            '多可用区', '数据湖', 'Paimon',
            '双塔', '召回', '索引', 'MySQL',
            '云数仓', 'Benchmark', 'Redis',
            'Firecracker', 'Serverless',
            '技术选型', 'HN 千赞',
            '数据中心', '建一个',
        ],
    },
    {
        'name': '年度回顾与感悟（个人总结/大会感受/书评/投资）',
        'keywords': [
            '回顾', '记忆', '废话', '告别', '走进',
            '文艺复兴', '开发者', '明天',
            'reInvent', 're:Invent', 'Day2', '主题演讲',
            '一年一度', '峰会', '参会有感',
            '蓄力和发力', 'Kindle', '情怀',
            '李飞飞', '我看见的世界', '巴菲特',
            '马斯克演讲', '濮存昕',
            '趋势', '预言', '私房菜',
            '云服务创新', '技术变化',
            '除夕', '快乐', '新年', '龙年', '马年',
            '红包', '抽奖',
            'A股', '诺亚效应', '博通', 'AI硬件',
            '谷歌罗曼蒂克',
            '又一年', '观自在',
        ],
    },
]


def classify_article(title, digest):
    """返回文章所属的分类名列表。"""
    cats = []
    for cat in CATEGORIES:
        if kw_match(title, digest, cat['keywords']):
            cats.append(cat['name'])
    return cats


def main():
    # 加载索引
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    # 构建锚点映射
    anchor_map = build_anchor_map()

    # 构建文章 -> md 文件路径映射
    import glob
    MD_DIR = os.path.join(BASE_DIR, "历史备份_md")
    md_path_map = {}  # (date, title_prefix) -> relative_path
    for md_path in glob.glob(os.path.join(MD_DIR, '**', '*.md'), recursive=True):
        fname = os.path.basename(md_path)
        m = re.match(r'(\d{4}-\d{2}-\d{2})_(.+)\.md$', fname)
        if m:
            rel = os.path.relpath(md_path, BASE_DIR)
            md_path_map[f"{m.group(1)}|{m.group(2)[:8]}"] = rel

    def find_md_path(title, date):
        """查找文章对应的 Markdown 文件相对路径。"""
        # 标准化比较：去除特殊字符
        def normalize(s):
            return re.sub(r'[|｜/\\:*?"<>\s_]', '', s)
        title_norm = normalize(title[:12])
        for key, path in md_path_map.items():
            k_date, k_prefix = key.split('|', 1)
            if k_date == date:
                k_norm = normalize(k_prefix)
                if k_norm[:6] in title_norm or title_norm[:6] in k_norm:
                    return path
        return None

    # 分类
    categorized = {cat['name']: [] for cat in CATEGORIES}
    for art in articles:
        title = art['title']
        digest = art.get('digest', '')
        date = art['date']
        cats = classify_article(title, digest)
        if not cats:
            cats = ['未分类']
            if '未分类' not in categorized:
                categorized['未分类'] = []

        anchor = find_anchor(title, date, anchor_map)
        md_path = find_md_path(title, date)
        for c in cats:
            categorized[c].append({
                'title': title,
                'date': date,
                'anchor': anchor,
                'md_path': md_path,
            })

    # 生成 Markdown
    lines = []
    lines.append("# 微信公众号「薛以致用」文章分类索引\n")
    lines.append("> 基于 F5-WexinArchiver 中归档的全部微信文章，按标题和正文内容进行分类。")
    lines.append("> 同一篇文章可能归属多个分类。")
    lines.append("> 点击「摘要与金句」列的链接可跳转到对应文章的 Executive Summary 和金句摘录。\n")
    lines.append("---\n")

    cat_num = 0
    for cat in CATEGORIES:
        name = cat['name']
        items = categorized.get(name, [])
        if not items:
            continue
        cat_num += 1

        # 按日期倒序
        items.sort(key=lambda x: x['date'], reverse=True)

        lines.append(f"## {_cn_num(cat_num)}、{name}\n")
        lines.append("| # | 标题 | 日期 | 原文 | 摘要与金句 |")
        lines.append("|---|------|------|------|-----------|")

        for i, item in enumerate(items, 1):
            title = item['title'].replace('|', '｜')
            date = item['date']
            anchor = item['anchor']
            md_path = item.get('md_path')
            if md_path:
                art_link = f"[📄 阅读]({md_path})"
            else:
                art_link = "—"
            if anchor:
                quote_link = f"[📝 查看](文章摘要与金句.md#{anchor})"
            else:
                quote_link = "—"
            lines.append(f"| {i} | {title} | {date} | {art_link} | {quote_link} |")

        lines.append("")

    # 未分类
    uncategorized = categorized.get('未分类', [])
    if uncategorized:
        uncategorized.sort(key=lambda x: x['date'], reverse=True)
        lines.append(f"## 其他（未分类）\n")
        lines.append("| # | 标题 | 日期 | 原文 | 摘要与金句 |")
        lines.append("|---|------|------|------|-----------|")
        for i, item in enumerate(uncategorized, 1):
            title = item['title'].replace('|', '｜')
            date = item['date']
            anchor = item['anchor']
            md_path = item.get('md_path')
            if md_path:
                art_link = f"[📄 阅读]({md_path})"
            else:
                art_link = "—"
            if anchor:
                quote_link = f"[📝 查看](文章摘要与金句.md#{anchor})"
            else:
                quote_link = "—"
            lines.append(f"| {i} | {title} | {date} | {art_link} | {quote_link} |")
        lines.append("")

    # 统计
    total = len(articles)
    cat_counts = {cat['name']: len(categorized.get(cat['name'], [])) for cat in CATEGORIES}
    lines.append("---\n")
    lines.append("## 统计\n")
    lines.append(f"- 文章总数: {total}")
    for cat in CATEGORIES:
        name = cat['name']
        count = cat_counts.get(name, 0)
        lines.append(f"- {name}: {count} 篇")
    if uncategorized:
        lines.append(f"- 未分类: {len(uncategorized)} 篇")
    lines.append("")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"完成！输出: {OUTPUT_FILE}")
    print(f"文章总数: {total}")
    for cat in CATEGORIES:
        print(f"  {cat['name']}: {cat_counts.get(cat['name'], 0)} 篇")
    if uncategorized:
        print(f"  未分类: {len(uncategorized)} 篇")


def _cn_num(n):
    cn = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
    if n <= 10:
        return cn[n]
    return str(n)


if __name__ == '__main__':
    main()
