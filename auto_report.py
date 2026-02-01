exec(open('/tmp/sandbox_bootstrap.py').read())

"""
Automated Kalshi Report + Paper Trading
Runs scan, generates report, records BUY recommendations to paper trading
"""

import json
import os
from datetime import datetime, timezone
from report_v2 import scan_and_decide
from paper_trading import record_recommendation

def parse_opportunities(report_text):
    """Parse BUY recommendations from report text"""
    buys = []
    lines = report_text.split('\n')
    
    current = {}
    for line in lines:
        line = line.strip()
        
        # Detect BUY header
        if '🟢 BUY' in line and '评分' in line:
            if current:
                buys.append(current)
            current = {'line': line}
        
        # Parse details
        elif current:
            if '👉' in line and '@' in line:
                # Extract side and price
                import re
                match = re.search(r'(YES|NO)\s*@\s*(\d+)¢.*仓位\s*\$(\d+)', line)
                if match:
                    current['side'] = match.group(1)
                    current['price'] = int(match.group(2))
                    current['position'] = int(match.group(3))
            elif '📊' in line:
                # Extract yield and days
                import re
                match = re.search(r'(\d+)%\s*年化\s*\((\d+)天\)', line)
                if match:
                    current['ann_yield'] = int(match.group(1))
                    current['days'] = int(match.group(2))
                match2 = re.search(r'spread\s*(\d+)¢', line)
                if match2:
                    current['spread'] = int(match2.group(1))
            elif '💡' in line:
                # Reasons
                current['reasons'] = line.replace('💡', '').strip().split(' | ')
            elif 'https://kalshi.com' in line:
                # URL and ticker
                current['url'] = line.replace('🔗', '').strip()
                import re
                match = re.search(r'/markets/([a-z0-9\-]+)', current['url'])
                if match:
                    current['ticker'] = match.group(1).upper()
    
    if current:
        buys.append(current)
    
    return buys

def run_daily_report():
    """Run scan, generate report, record trades"""
    print("="*70)
    print("🤖 AUTOMATED KALSHI REPORT")
    print(f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*70)
    print()
    
    # Run scan
    print("🔍 Scanning markets...")
    report = scan_and_decide()
    
    print("\n" + "="*70)
    print(report)
    print("="*70)
    
    # Parse and record BUY recommendations
    buys = parse_opportunities(report)
    
    if buys:
        print(f"\n📝 Recording {len(buys)} BUY recommendations to paper trading...")
        for i, buy in enumerate(buys, 1):
            if all(k in buy for k in ['ticker', 'side', 'price', 'position']):
                # Record to paper trading
                trade_id = record_recommendation(
                    ticker=buy['ticker'],
                    title=buy.get('title', buy['ticker']),
                    decision="BUY",
                    side=buy['side'],
                    price=buy['price'],
                    position=buy['position'],
                    score=buy.get('score', 0),
                    reasons=buy.get('reasons', []),
                    expiration=f"Unknown+{buy.get('days', 0)}d",
                    url=buy['url']
                )
                print(f"  #{i}: Trade #{trade_id} - {buy['ticker']}")
            else:
                print(f"  #{i}: ⚠️ Incomplete data, skipped")
    else:
        print("\n📝 No BUY recommendations to record")
    
    # Save report to file
    report_file = os.path.join(os.path.dirname(__file__), f"reports/report-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.txt")
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"\n💾 Report saved to: {report_file}")
    
    return report

if __name__ == "__main__":
    run_daily_report()
