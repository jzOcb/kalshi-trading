# Kalshi Trading - Cron Setup Examples

## Quick Start

### Daily Morning Scan (9 AM)
```bash
clawdbot cron add \
  --name "Kalshi daily scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram \
  --deliver
```

## Common Patterns

### 1. Daily Scan with Summary
Run scan + show paper trading stats:
```bash
clawdbot cron add \
  --name "Kalshi morning report" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py && echo '---' && python3 paper_trading.py summary" \
  --channel telegram \
  --deliver
```

### 2. Multi-time Scan (Morning + Evening)
```bash
# Morning scan
clawdbot cron add \
  --name "Kalshi AM scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram \
  --deliver

# Evening check
clawdbot cron add \
  --name "Kalshi PM check" \
  --cron "0 18 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 paper_trading.py summary" \
  --channel telegram \
  --deliver
```

### 3. Settlement Day Reminders
```bash
# CPI settlement reminder (Feb 11)
clawdbot cron add \
  --name "CPI settlement check" \
  --at "2026-02-11T14:00:00Z" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 paper_trading.py summary && echo 'CPI data released - check settlements!'" \
  --channel telegram \
  --deliver \
  --delete-after-run

# GDP settlement reminder (Feb 20)
clawdbot cron add \
  --name "GDP settlement check" \
  --at "2026-02-20T14:00:00Z" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 paper_trading.py summary && echo 'GDP data released - check settlements!'" \
  --channel telegram \
  --deliver \
  --delete-after-run
```

### 4. Quick Alert (20 minutes)
```bash
clawdbot cron add \
  --name "Kalshi quick scan" \
  --at "20m" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram \
  --deliver \
  --delete-after-run
```

### 5. Weekday-Only Scan
```bash
# Monday to Friday at 9 AM
clawdbot cron add \
  --name "Kalshi weekday scan" \
  --cron "0 9 * * 1-5" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram \
  --deliver
```

### 6. Discord Delivery
```bash
clawdbot cron add \
  --name "Kalshi to Discord" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel discord \
  --to "channel:1234567890" \
  --deliver
```

### 7. WhatsApp Delivery
```bash
clawdbot cron add \
  --name "Kalshi to WhatsApp" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel whatsapp \
  --to "+15551234567" \
  --deliver
```

## Managing Cron Jobs

### List all jobs
```bash
clawdbot cron list
```

### View job details
```bash
clawdbot cron show <job-id>
```

### Delete a job
```bash
clawdbot cron remove <job-id>
```

### Test a job immediately
```bash
clawdbot cron run <job-id>
```

## Cron Expression Reference

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday=0)
│ │ │ │ │
* * * * *
```

**Examples:**
- `0 9 * * *` - Every day at 9 AM
- `0 9,18 * * *` - Every day at 9 AM and 6 PM
- `0 9 * * 1-5` - Weekdays at 9 AM
- `0 0 1 * *` - First day of every month at midnight
- `*/30 * * * *` - Every 30 minutes

## Delivery Targets

### Telegram
```bash
--channel telegram --to "-1001234567890"  # Group
--channel telegram --to "123456789"       # Direct message
--channel telegram --to "-1001234567890:topic:123"  # Forum topic
```

### Discord
```bash
--channel discord --to "channel:1234567890"  # Channel
--channel discord --to "user:1234567890"     # DM
```

### Slack
```bash
--channel slack --to "channel:C1234567890"  # Channel
--channel slack --to "user:U1234567890"     # DM
```

### WhatsApp
```bash
--channel whatsapp --to "+15551234567"  # E.164 format
```

### Last Channel
```bash
--channel last  # Delivers to last active channel
```

## Advanced Options

### Custom Model (Haiku for speed)
```bash
clawdbot cron add \
  --name "Fast scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --model "anthropic/claude-haiku-4-5" \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --deliver
```

### Timeout Override
```bash
clawdbot cron add \
  --name "Long scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --timeout 300 \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --deliver
```

### Best-Effort Delivery
Doesn't fail the job if delivery fails:
```bash
clawdbot cron add \
  --name "Resilient scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram \
  --best-effort-deliver
```

## Timezone Notes

- Cron expressions use **Gateway host timezone** (unless specified)
- ISO timestamps (`--at`) are treated as **UTC** unless timezone is included
- To use a specific timezone with cron expressions, add TZ= prefix:
  ```bash
  --cron "TZ=America/New_York 0 9 * * *"
  ```

## Troubleshooting

### Job doesn't run
```bash
# Check job status
clawdbot cron list

# Check run history
clawdbot cron runs <job-id>

# Test manually
clawdbot cron run <job-id>
```

### Output not delivered
- Check `--deliver` flag is set
- Verify channel name (telegram, discord, etc.)
- Check `--to` target format
- Try `--best-effort-deliver` for resilience

### Script fails
- Test script manually first: `cd ~/clawd/kalshi && python3 report_v2.py`
- Check working directory in job message
- Verify file permissions

---

For more cron options: `clawdbot cron --help`
