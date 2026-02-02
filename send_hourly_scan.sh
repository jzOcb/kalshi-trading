#!/bin/bash
# Kalshi每小时扫描并发送到Jason的DM

cd /home/clawdbot/clawd

# 运行扫描
REPORT=$(python3 kalshi/notify.py 2>&1)

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
