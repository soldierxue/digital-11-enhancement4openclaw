#!/usr/bin/env python3
"""
classify_expense.py — 将下载的 Expense 材料按费用类型分类归档。

根据邮件元数据（发件人、主题）和文件名模式，将发票/水单/收据
分类到对应目录。对每个发票文件，尝试从邮件元数据提取日期、类型、
金额、地点等信息组合成新文件名；如果信息不足，调用 Kiro CLI
进行发票内容识别（OCR/AI）。

用法:
    python3 classify_expense.py [选项]

选项:
    --input-dir DIR       待分类文件目录（RAW 文件夹路径）
    --output-dir DIR      归档根目录 (默认: ~/Expenses)
    --scan-result PATH    scan_inbox.py 输出的 JSON（辅助分类）
    --download-result PATH  download_expense.py 输出的 JSON
    --no-ocr              禁用 Kiro CLI 发票识别
"""

import json
import os
import sys
import re
import shutil
import argparse
import subprocess
from datetime import datetime, date


# ============================================================
# 分类规则
# ============================================================

# 规则 1: 发件人精确匹配（最高优先级）
SENDER_RULES = [
    # 交通 — 网约车
    (r"didifapiao@", "transport_didi"),
    (r"@t3go\.cn", "transport_didi"),
    (r"@caocao", "transport_didi"),
    # 交通 — 航空
    (r"@airchina\.com", "transport_flight"),
    (r"@csair\.com", "transport_flight"),
    (r"@ceair\.com", "transport_flight"),
    (r"etravelnotice", "transport_flight"),
    # 通讯
    (r"10086@139\.com", "telecom"),
    (r"@chinaunicom", "telecom"),
    (r"@189\.cn", "telecom"),
    # 住宿
    (r"mhrs\..*\.gsm@marriott\.com", "accommodation"),
    (r"@hilton\.com", "accommodation"),
    (r"@hyatt\.com", "accommodation"),
    (r"@ihg\.com", "accommodation"),
    (r"@accor\.com", "accommodation"),
    (r"@starwood", "accommodation"),
    # 餐饮
    (r"Invoice@store\.timschina\.com", "dining"),
    (r"@starbucks", "dining"),
    (r"@mcd", "dining"),
]

# 规则 2: 邮件主题关键词匹配
SUBJECT_RULES = [
    # 交通
    (["行程单", "航班", "机票", "flight", "boarding", "航空"], "transport_flight"),
    (["火车票", "高铁", "动车", "12306", "铁路"], "transport_train"),
    (["打车", "出行", "行程", "网约车", "滴滴", "快车", "专车"], "transport_didi"),
    # 住宿
    (["酒店", "hotel", "水单", "folio", "住宿", "入住", "客房"], "accommodation"),
    # 餐饮
    (["餐饮", "餐厅", "restaurant", "外卖", "美团", "饿了么"], "dining"),
    # 通讯
    (["话费", "流量", "通讯", "月结", "中国移动", "中国联通", "中国电信"], "telecom"),
    # 办公
    (["办公", "文具", "打印", "耗材", "office"], "office"),
]

# 规则 3: 文件名模式匹配
FILENAME_RULES = [
    (r"滴滴|DiDi|didi", "transport_didi"),
    (r"行程单|itinerary|boarding", "transport_flight"),
    (r"火车票|12306|railway", "transport_train"),
    (r"水单|folio|hotel|酒店", "accommodation"),
    (r"中国移动|China\s*Mobile|10086", "telecom"),
    (r"中国联通|China\s*Unicom", "telecom"),
    (r"中国电信|China\s*Telecom", "telecom"),
]

# 分类 → 目录映射
CATEGORY_DIRS = {
    "transport_didi": "transport/didi",
    "transport_flight": "transport/flight",
    "transport_train": "transport/train",
    "transport_other": "transport/other",
    "accommodation": "accommodation",
    "dining": "dining",
    "telecom": "telecom",
    "office": "office",
    "other": "other",
}

CATEGORY_LABELS = {
    "transport_didi": "🚗 网约车",
    "transport_flight": "✈️ 航空",
    "transport_train": "🚄 火车",
    "transport_other": "🚌 其他交通",
    "accommodation": "🏨 住宿",
    "dining": "🍽️ 餐饮",
    "telecom": "📱 通讯",
    "office": "💻 办公",
    "other": "📋 其他",
}


# ============================================================
# 分类逻辑
# ============================================================

def classify_by_sender(sender):
    """根据发件人分类"""
    if not sender:
        return None
    for pattern, category in SENDER_RULES:
        if re.search(pattern, sender, re.IGNORECASE):
            return category
    return None


def classify_by_subject(subject):
    """根据邮件主题分类"""
    if not subject:
        return None
    subject_lower = subject.lower()
    for keywords, category in SUBJECT_RULES:
        for kw in keywords:
            if kw.lower() in subject_lower:
                return category
    return None


def classify_by_filename(filename):
    """根据文件名分类"""
    if not filename:
        return None
    for pattern, category in FILENAME_RULES:
        if re.search(pattern, filename, re.IGNORECASE):
            return category
    return None


def classify_file(filename, sender="", subject=""):
    """综合分类（按优先级）"""
    # 优先级 1: 发件人
    cat = classify_by_sender(sender)
    if cat:
        return cat, "sender"

    # 优先级 2: 主题
    cat = classify_by_subject(subject)
    if cat:
        return cat, "subject"

    # 优先级 3: 文件名
    cat = classify_by_filename(filename)
    if cat:
        return cat, "filename"

    # 兜底
    return "other", "default"


# ============================================================
# Kiro CLI 发票内容识别（OCR/AI）
# ============================================================

def kiro_cli_recognize_invoice(file_path):
    """
    调用 Kiro CLI 对发票文件进行内容识别，提取结构化信息。
    返回 dict: {date, amount, vendor, location, type, raw_response}
    失败返回 None。
    """
    if not os.path.exists(file_path):
        return None

    prompt = (
        f"请识别这个发票/收据文件的内容，提取以下信息并以 JSON 格式返回"
        f"（只返回 JSON，不要其他文字）：\n"
        f'{{"date":"YYYY-MM-DD","amount":"金额数字","vendor":"供应商/商户名",'
        f'"location":"消费地点/城市","type":"发票类型(如:增值税电子普通发票/水单/行程单/收据)"}}\n'
        f"文件路径: {file_path}"
    )

    try:
        result = subprocess.run(
            ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools",
             "-p", prompt],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout.strip()
        if not output:
            return None

        # 尝试从输出中提取 JSON
        json_match = re.search(r'\{[^{}]*"date"[^{}]*\}', output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            data["raw_response"] = output[:500]
            return data

        # 兜底：尝试直接解析整个输出
        data = json.loads(output)
        data["raw_response"] = output[:500]
        return data

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"    ⚠️ Kiro CLI 识别失败: {e}")
        return None
    except Exception as e:
        print(f"    ⚠️ Kiro CLI 异常: {e}")
        return None


# ============================================================
# 文件命名（增强版：日期_类型_金额_地点_供应商）
# ============================================================

def extract_date_from_email(email_info):
    """从邮件元数据提取日期"""
    date_str = email_info.get("date", "")
    if not date_str:
        return None

    patterns = [
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
        r"(\d{4})年(\d{1,2})月(\d{1,2})日",
    ]
    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    for pat in patterns:
        m = re.search(pat, date_str)
        if m:
            groups = m.groups()
            return f"{groups[0]}{int(groups[1]):02d}{int(groups[2]):02d}"

    m = re.search(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
        date_str)
    if m:
        return f"{m.group(3)}{month_map[m.group(2)]:02d}{int(m.group(1)):02d}"

    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})",
        date_str)
    if m:
        return f"{m.group(3)}{month_map[m.group(1)]:02d}{int(m.group(2)):02d}"

    return None


def sanitize(s, max_len=20):
    """清理字符串用于文件名"""
    if not s:
        return ""
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', '', s).strip()
    s = re.sub(r'\s+', ' ', s)
    return s[:max_len]


def generate_filename(original_name, email_info, category, ocr_info=None):
    """
    生成增强版文件名。
    格式: YYYYMMDD_类型_金额_地点_供应商.ext
    各字段缺失时省略，保证文件名可读且信息丰富。
    """
    _, ext = os.path.splitext(original_name)
    ext = ext or ".pdf"

    # 收集各字段（优先 OCR 结果，其次邮件元数据）
    date_prefix = None
    inv_type = ""
    amount = ""
    location = ""
    vendor = ""

    # --- 从 OCR 结果提取 ---
    if ocr_info:
        ocr_date = ocr_info.get("date", "")
        if ocr_date:
            m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", ocr_date)
            if m:
                date_prefix = f"{m.group(1)}{m.group(2)}{m.group(3)}"

        raw_amount = ocr_info.get("amount", "")
        if raw_amount:
            # 提取数字部分
            amt_match = re.search(r"[\d,.]+", str(raw_amount))
            if amt_match:
                amount = amt_match.group().rstrip(".")

        vendor = sanitize(ocr_info.get("vendor", ""), 15)
        location = sanitize(ocr_info.get("location", ""), 10)
        inv_type = sanitize(ocr_info.get("type", ""), 15)

    # --- 从邮件元数据补充缺失字段 ---
    if not date_prefix:
        date_prefix = extract_date_from_email(email_info) or datetime.now().strftime("%Y%m%d")

    sender_name = email_info.get("senderName", "")
    subject = email_info.get("subject", "")

    if not vendor:
        if "滴滴" in sender_name or "didi" in sender_name.lower():
            vendor = "滴滴出行"
        elif "marriott" in sender_name.lower():
            vendor = "Marriott"
        elif "hilton" in sender_name.lower():
            vendor = "Hilton"
        elif "10086" in sender_name or "移动" in sender_name:
            vendor = "中国移动"
        elif "联通" in sender_name:
            vendor = "中国联通"
        elif "电信" in sender_name:
            vendor = "中国电信"
        elif sender_name:
            vendor = sanitize(sender_name, 12)

    if not inv_type:
        for kw, label in [
            ("发票", "发票"), ("invoice", "发票"),
            ("水单", "水单"), ("folio", "水单"),
            ("收据", "收据"), ("receipt", "收据"),
            ("行程单", "行程单"), ("账单", "账单"), ("bill", "账单"),
        ]:
            if kw in subject.lower():
                inv_type = label
                break
        if not inv_type:
            inv_type = "发票"

    # --- 组合文件名 ---
    parts = [date_prefix]
    if inv_type:
        parts.append(inv_type)
    if amount:
        parts.append(amount + "元")
    if location:
        parts.append(location)
    if vendor:
        parts.append(vendor)

    return "_".join(parts) + ext


# ============================================================
# 汇总报告
# ============================================================

def generate_summary_md(classified_files, failed_items, output_dir):
    """生成 Markdown 汇总报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 统计
    category_stats = {}
    for item in classified_files:
        cat = item["category"]
        if cat not in category_stats:
            category_stats[cat] = {"count": 0, "files": []}
        category_stats[cat]["count"] += 1
        category_stats[cat]["files"].append(item["newFilename"])

    lines = [
        f"# Expense 下载与分类汇总 — {now}\n",
        "## 📊 统计\n",
        f"- 成功分类: {len(classified_files)} 个文件",
        f"- 需人工处理: {len(failed_items)} 项\n",
        "## 📁 分类明细\n",
        "| 类别 | 数量 | 文件 |",
        "|------|------|------|",
    ]

    for cat_id in CATEGORY_DIRS:
        if cat_id in category_stats:
            stats = category_stats[cat_id]
            label = CATEGORY_LABELS.get(cat_id, cat_id)
            files_str = ", ".join(stats["files"][:5])
            if len(stats["files"]) > 5:
                files_str += f" ... +{len(stats['files'])-5}"
            lines.append(f"| {label} | {stats['count']} | {files_str} |")

    if failed_items:
        lines.append("\n## ⚠️ 需要人工处理\n")
        for item in failed_items:
            reason = item.get("reason", "未知原因")
            subject = item.get("subject", "")
            lines.append(f"- [{subject[:40]}] — {reason}")

    lines.append(f"\n---\n*生成时间: {now}*\n")
    return "\n".join(lines)


def generate_summary_json(classified_files, failed_items):
    """生成 JSON 汇总"""
    category_stats = {}
    for item in classified_files:
        cat = item["category"]
        if cat not in category_stats:
            category_stats[cat] = []
        category_stats[cat].append({
            "filename": item["newFilename"],
            "originalFilename": item["originalFilename"],
            "path": item["newPath"],
            "sender": item.get("sender", ""),
            "subject": item.get("subject", ""),
            "date": item.get("date", ""),
            "classifiedBy": item.get("classifiedBy", ""),
        })

    return {
        "generatedAt": datetime.now().isoformat(),
        "totalClassified": len(classified_files),
        "totalFailed": len(failed_items),
        "categories": category_stats,
        "failed": failed_items,
    }


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="分类归档 Expense 材料")
    parser.add_argument("--input-dir",
                        default=None,
                        help="待分类文件目录（RAW 文件夹路径）")
    parser.add_argument("--output-dir",
                        default=os.path.expanduser(
                            os.environ.get("EXPENSE_OUTPUT_DIR", "~/Expenses")),
                        help="归档根目录")
    parser.add_argument("--scan-result", default=None,
                        help="scan_inbox.py 输出的 JSON（辅助分类）")
    parser.add_argument("--download-result", default=None,
                        help="download_expense.py 输出的 JSON")
    parser.add_argument("--no-ocr", action="store_true",
                        help="禁用 Kiro CLI 发票内容识别")
    args = parser.parse_args()

    # 如果未指定 input-dir，尝试从 download-result 中获取 rawDir
    if not args.input_dir:
        if args.download_result and os.path.exists(args.download_result):
            with open(args.download_result, "r", encoding="utf-8") as f:
                dl_data = json.load(f)
            args.input_dir = dl_data.get("rawDir", "")
        if not args.input_dir:
            # 兜底：查找 ~/Expenses 下最新的 RAW 文件夹
            expenses_dir = os.path.expanduser("~/Expenses")
            if os.path.isdir(expenses_dir):
                raw_dirs = [d for d in os.listdir(expenses_dir)
                            if os.path.isdir(os.path.join(expenses_dir, d))
                            and d.startswith("[")]
                if raw_dirs:
                    raw_dirs.sort(key=lambda d: os.path.getmtime(
                        os.path.join(expenses_dir, d)), reverse=True)
                    args.input_dir = os.path.join(expenses_dir, raw_dirs[0])

    if not args.input_dir or not os.path.isdir(args.input_dir):
        print(f"✘ 输入目录不存在: {args.input_dir}")
        print("  请指定 --input-dir（RAW 文件夹路径）或 --download-result")
        sys.exit(1)

    # 加载邮件元数据（如果有）
    email_metadata = {}
    if args.scan_result and os.path.exists(args.scan_result):
        with open(args.scan_result, "r", encoding="utf-8") as f:
            scan_data = json.load(f)
        for email in scan_data.get("emails", []):
            idx = email.get("index")
            email_metadata[idx] = email

    # 加载下载结果（如果有）
    download_map = {}
    if args.download_result and os.path.exists(args.download_result):
        with open(args.download_result, "r", encoding="utf-8") as f:
            dl_data = json.load(f)
        for item in dl_data.get("downloaded", []):
            download_map[item.get("filename", "")] = item

    # 扫描待分类文件
    files = []
    for fname in os.listdir(args.input_dir):
        fpath = os.path.join(args.input_dir, fname)
        if os.path.isfile(fpath) and not fname.startswith(".") and fname != "download-result.json":
            files.append((fname, fpath))

    if not files:
        print(f"✘ 输入目录中没有文件: {args.input_dir}")
        sys.exit(1)

    print(f"▶ 待分类文件: {len(files)} 个")
    print(f"  输入: {args.input_dir}")
    print(f"  输出: {args.output_dir}")

    # 确定当前月份目录
    month_dir = datetime.now().strftime("%Y-%m")

    classified_files = []
    failed_items = []

    for fname, fpath in files:
        # 尝试从元数据获取邮件信息
        sender = ""
        subject = ""
        email_info = {}

        # 简单匹配：用文件名在 email_metadata 中查找
        for idx, meta in email_metadata.items():
            meta_subject = meta.get("subject", "")
            if meta_subject and (meta_subject[:10] in fname or fname[:10] in meta_subject):
                sender = meta.get("sender", "")
                subject = meta_subject
                email_info = meta
                break

        # 分类
        category, classified_by = classify_file(fname, sender, subject)
        label = CATEGORY_LABELS.get(category, category)

        # ============================================================
        # 发票内容识别（Kiro CLI OCR/AI）
        # 当邮件元数据不足以提取金额、地点等信息时，调用 Kiro CLI
        # ============================================================
        ocr_info = None
        need_ocr = (not args.no_ocr
                    and fname.lower().endswith((".pdf", ".jpg", ".jpeg", ".png"))
                    and not email_info.get("amount"))

        if need_ocr:
            print(f"  🔍 Kiro CLI 识别: {fname}...")
            ocr_info = kiro_cli_recognize_invoice(fpath)
            if ocr_info:
                print(f"    → 日期={ocr_info.get('date','?')} "
                      f"金额={ocr_info.get('amount','?')} "
                      f"供应商={ocr_info.get('vendor','?')} "
                      f"地点={ocr_info.get('location','?')}")

        # 生成新文件名（增强版：日期_类型_金额_地点_供应商）
        new_fname = generate_filename(fname, email_info, category, ocr_info)

        # 目标目录
        cat_dir = CATEGORY_DIRS.get(category, "other")
        target_dir = os.path.join(args.output_dir, month_dir, cat_dir)
        os.makedirs(target_dir, exist_ok=True)

        # 移动文件（处理重名）
        target_path = os.path.join(target_dir, new_fname)
        if os.path.exists(target_path):
            base, ext = os.path.splitext(new_fname)
            n = 1
            while os.path.exists(target_path):
                target_path = os.path.join(target_dir, f"{base} ({n}){ext}")
                n += 1

        shutil.move(fpath, target_path)

        print(f"  {label} {fname} → {os.path.relpath(target_path, args.output_dir)}"
              f"  (by {classified_by})")

        classified_files.append({
            "originalFilename": fname,
            "newFilename": os.path.basename(target_path),
            "newPath": target_path,
            "category": category,
            "classifiedBy": classified_by,
            "sender": sender,
            "subject": subject,
            "date": email_info.get("date", ""),
            "ocrInfo": ocr_info,
        })

    # 生成汇总报告
    print(f"\n▶ 生成汇总报告...")

    summary_md = generate_summary_md(classified_files, failed_items, args.output_dir)
    md_path = os.path.join(args.output_dir, "summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(summary_md)
    print(f"  📄 {md_path}")

    summary_json = generate_summary_json(classified_files, failed_items)
    json_path = os.path.join(args.output_dir, "summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_json, f, ensure_ascii=False, indent=2)
    print(f"  📄 {json_path}")

    # 统计输出
    print(f"\n{'='*60}")
    print(f"✅ 分类完成！")
    cat_counts = {}
    for item in classified_files:
        cat = item["category"]
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    for cat_id, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        label = CATEGORY_LABELS.get(cat_id, cat_id)
        print(f"  {label}: {count} 个文件")

    print(f"\n  归档目录: {args.output_dir}/{month_dir}/")

    result = {
        "totalClassified": len(classified_files),
        "totalFailed": len(failed_items),
        "outputDir": os.path.join(args.output_dir, month_dir),
        "summaryMd": md_path,
        "summaryJson": json_path,
    }
    print(f"\nRESULT_JSON:{json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
