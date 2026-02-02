# Kalshi Deployment Checklist

**Problem this solves:** Built new features but forgot to wire them into production.

**Example incident (2026-02-02):**
- Built dynamic_trader.py with news verification
- Built improved notify.py with URLs and scoring
- **But forgot:** Hourly cron still using old notify.py output format
- **Result:** User got incomplete reports

---

## Pre-Deployment Checklist

Before marking any feature "done", verify:

### 1. Code Changes
- [ ] New code written/modified
- [ ] Tests pass (manual or automated)
- [ ] No hardcoded secrets (run `bash check-secrets.sh`)

### 2. Integration Points
- [ ] **Identify all entry points** (cron jobs, APIs, user commands)
- [ ] **Update all entry points** to use new code
- [ ] **Verify old code is replaced** (not running in parallel)

### 3. Configuration
- [ ] Config files updated (if needed)
- [ ] Environment variables set (if needed)
- [ ] Documentation updated

### 4. End-to-End Test
- [ ] **Run the actual production flow** (not just the function)
- [ ] **Verify user-facing output** (what they see, not logs)
- [ ] **Check all edge cases** (empty results, errors, etc.)

### 5. Monitoring
- [ ] Logs in place
- [ ] Error alerts configured
- [ ] Success metrics defined

---

## Post-Deployment Verification

Within 24h of deploying:

- [ ] **Monitor first real run** (cron, webhook, whatever)
- [ ] **Check user feedback** (did they receive expected output?)
- [ ] **Review logs** (any errors/warnings?)
- [ ] **Verify metrics** (is it working as expected?)

---

## Kalshi-Specific Integration Points

When changing Kalshi scanner/trader:

### Scanner Changes
Entry points to check:
1. `send_hourly_scan.sh` (hourly DM reports)
2. Heartbeat integration (DM delivery)
3. Any manual commands users run

Verification steps:
```bash
# 1. Run the script that generates user-facing output
bash kalshi/send_hourly_scan.sh

# 2. Check the actual output file
cat /tmp/kalshi_hourly_scan_dm.txt | head -50

# 3. Simulate what user receives (send to yourself first)
clawdbot message send --target YOUR_USER_ID --message "$(cat /tmp/kalshi_hourly_scan_dm.txt)"

# 4. Verify format, links, content
```

### Trader Changes
Entry points to check:
1. `dynamic_trader.py monitor` (manual checks)
2. `alert_trader.sh` (2h cron monitoring)
3. Paper trade recording

Verification steps:
```bash
# 1. Run monitor
cd kalshi && python3 dynamic_trader.py monitor

# 2. Check alerts generated
bash kalshi/alert_trader.sh

# 3. Verify DM sent correctly
# (check your Telegram)
```

---

## Lessons Learned (Incident Log)

### 2026-02-02: Incomplete Hourly Reports

**Symptom:** User reported missing titles, URLs, news verification in hourly scans.

**Root cause:** Built new `notify.py` with features, but:
- `send_hourly_scan.sh` uses `notify.py`
- New features were in the code
- **But output format assumptions were wrong**
- Didn't test end-to-end (script → file → DM → user)

**Fix:**
1. Run actual production flow: `bash send_hourly_scan.sh`
2. Check output: `cat /tmp/kalshi_hourly_scan_dm.txt`
3. Verify user receives complete report
4. Test URL links actually work

**Prevention (added to checklist):**
- [x] Always test the FULL production flow, not just the function
- [x] Verify user-facing output, not internal logs
- [x] Check ALL integration points when changing core modules

### [Future incidents go here]

---

## Automation (TODO)

**Goal:** Make this checklist mechanical, not manual.

**Phase 1: Pre-commit hook**
```bash
# Block commits if deployment checklist not marked complete
# (when DEPLOYMENT-CHECKLIST.md has unchecked boxes)
```

**Phase 2: CI/CD pipeline**
```bash
# On merge to main:
# 1. Run integration tests
# 2. Deploy to staging
# 3. Run end-to-end tests
# 4. Deploy to production
# 5. Monitor first run
```

**Phase 3: Self-verification agent**
```bash
# After any code change:
# 1. Agent identifies integration points
# 2. Agent tests each point
# 3. Agent reports verification status
# 4. Block deploy if any point fails
```

---

## When to Use This Checklist

**Every time you:**
- Add a new feature
- Modify existing functionality
- Change output format
- Update dependencies
- Refactor code that's used in production

**Especially when:**
- User-facing output changes
- Cron jobs involved
- Multiple entry points exist
- Previous similar issue occurred

---

**Remember:** A feature isn't "done" until users receive the intended benefit.
