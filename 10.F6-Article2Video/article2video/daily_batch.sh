#!/bin/bash
# daily_batch.sh — 批量生成当天发表文章的横版+竖版视频
# 由 OpenClaw Cron 每晚 22:00（北京时间）触发
# 
# 用法: bash daily_batch.sh [YYYY-MM-DD]
#   不传日期则使用当天（北京时间）

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
POSTS_DIR="/tmp/jason.xue/_posts"
OUTPUT_DIR="$HOME/.openclaw/workspace/output"
LOG_DIR="$HOME/.openclaw/workspace/output/video-batch-logs"
STATE_FILE="$HOME/.openclaw/workspace/output/video-batch-state.json"

# 日期（北京时间）
DATE="${1:-$(TZ=Asia/Shanghai date +%Y-%m-%d)}"
echo "📅 日期: $DATE"
echo "🕐 开始时间: $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')"

mkdir -p "$LOG_DIR"

# 查找当天文章
ARTICLES=($(ls "$POSTS_DIR"/${DATE}-*.md 2>/dev/null || true))
TOTAL=${#ARTICLES[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo "⚠️ 未找到 $DATE 的文章，跳过"
    exit 0
fi

echo "📝 找到 $TOTAL 篇文章"

# 初始化状态
python3 -c "
import json, os
state_file = '$STATE_FILE'
state = {}
if os.path.exists(state_file):
    with open(state_file) as f:
        state = json.load(f)
state['$DATE'] = {
    'total': $TOTAL,
    'completed': [],
    'failed': [],
    'status': 'running',
    'start_time': '$(TZ=Asia/Shanghai date -Iseconds)'
}
with open(state_file, 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
"

SUCCESS=0
FAIL=0

for ARTICLE in "${ARTICLES[@]}"; do
    BASENAME=$(basename "$ARTICLE" .md)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎬 处理: $BASENAME"
    echo "  开始: $(TZ=Asia/Shanghai date '+%H:%M:%S')"
    
    LOG_FILE="$LOG_DIR/${BASENAME}.log"
    
    # 检查是否已生成（跳过已完成的）
    LANDSCAPE_FILE="$OUTPUT_DIR/${BASENAME}-video.mp4"
    PORTRAIT_FILE="$OUTPUT_DIR/${BASENAME}-video-portrait.mp4"
    
    if [ -f "$LANDSCAPE_FILE" ] && [ -f "$PORTRAIT_FILE" ]; then
        echo "  ⏭️ 横版+竖版已存在，跳过"
        SUCCESS=$((SUCCESS + 1))
        python3 -c "
import json
with open('$STATE_FILE') as f: state = json.load(f)
state['$DATE']['completed'].append('$BASENAME')
with open('$STATE_FILE', 'w') as f: json.dump(state, f, ensure_ascii=False, indent=2)
"
        continue
    fi
    
    # 生成横版+竖版（--format both）
    if python3 "$SKILL_DIR/main.py" "$ARTICLE" \
        --format both \
        --style photo \
        --slides 10 \
        > "$LOG_FILE" 2>&1; then
        
        echo "  ✅ 完成: $(TZ=Asia/Shanghai date '+%H:%M:%S')"
        SUCCESS=$((SUCCESS + 1))
        
        # 更新状态
        python3 -c "
import json
with open('$STATE_FILE') as f: state = json.load(f)
state['$DATE']['completed'].append('$BASENAME')
with open('$STATE_FILE', 'w') as f: json.dump(state, f, ensure_ascii=False, indent=2)
"
    else
        echo "  ❌ 失败! 查看日志: $LOG_FILE"
        FAIL=$((FAIL + 1))
        
        python3 -c "
import json
with open('$STATE_FILE') as f: state = json.load(f)
state['$DATE']['failed'].append('$BASENAME')
with open('$STATE_FILE', 'w') as f: json.dump(state, f, ensure_ascii=False, indent=2)
"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 批量生成完成"
echo "  总计: $TOTAL 篇"
echo "  成功: $SUCCESS 篇"
echo "  失败: $FAIL 篇"
echo "  结束: $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')"

# 最终状态
python3 -c "
import json
with open('$STATE_FILE') as f: state = json.load(f)
state['$DATE']['status'] = 'completed' if $FAIL == 0 else 'partial'
state['$DATE']['end_time'] = '$(TZ=Asia/Shanghai date -Iseconds)'
state['$DATE']['success'] = $SUCCESS
state['$DATE']['failed_count'] = $FAIL
with open('$STATE_FILE', 'w') as f: json.dump(state, f, ensure_ascii=False, indent=2)
"

# 列出生成的视频
echo ""
echo "🎥 生成的视频文件:"
ls -lh "$OUTPUT_DIR"/${DATE}-*-video*.mp4 2>/dev/null || echo "  (无)"
