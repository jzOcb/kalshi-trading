#!/bin/bash
# Kalshi每小时扫描并发送到Jason的DM

cd /home/clawdbot/clawd

# 运行扫描 (report_v2: 全量扫描551+市场，详细评分+链接)
REPORT=$(cd kalshi && timeout 180 python3 -c "
import sys, io
sys.stdout = io.StringIO()
from report_v2 import scan_and_decide
result = scan_and_decide()
sys.stdout = sys.__stdout__
print(result)
" 2>/dev/null)

# 更新heartbeat state
python3 -c "
import json, time
try:
    with open('memory/heartbeat-state.json') as f:
        data = json.load(f)
    data['lastChecks']['kalshi_scan'] = int(time.time())
    with open('memory/heartbeat-state.json', 'w') as f:
        json.dump(data, f, indent=2)
except: pass
"

# 保存到临时文件（给heartbeat发送到DM用）
echo "$REPORT" > /tmp/kalshi_hourly_scan_dm.txt

# 标记给heartbeat检测
touch /tmp/kalshi_hourly_scan_dm_ready.flag

echo "✅ Kalshi scan completed, report saved for DM delivery"
