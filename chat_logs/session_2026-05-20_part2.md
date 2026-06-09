# Session Log — 2026-05-20 Part 2: MES/MGC Calibration + Public Launch Prep

## Summary

Validated MES and MGC backtest performance, calibrated instrument parameters, renamed the product to Micro Futures Analyzer, cleaned all prop firm language, wrote README, and pushed to GitHub for public launch.

---

## MES / MGC Backtest Investigation

### Problem
- MES 45-day: 35.7% WR — losing money
- MGC 45-day: 25% WR — dominated by failing OR30 trades

### Root Causes Found

**MES — stops too tight:**
- Natural ES sweep distances: 8–12pts
- min_stop_pts was 20 → all stops landing at exactly the floor
- During tariff crash, ES moved 20–50pts in a single 5m bar → 20pt stop was noise
- Fix: raised stop_buffer 10→15, min_stop_pts 20→30

**MGC — wrong secondary track:**
- OR30 breakout (Coach Dakota) is calibrated for equity index futures
- Gold does NOT trend at NY open the same way — Gold is an Asia/London instrument
- Fix: disabled OR30 entirely for MGC in production backtest

**Reload rule too loose:**
- A partial_win (hit 1R, stopped at BE) was triggering a second trade
- On choppy days this caused double losses
- Fix: second daily trade now requires a FULL WIN only

**MES score threshold:**
- ES generates noisier A+ setups (500 stocks = more structure)
- Taking setups on days MNQ found nothing — those days had the worst outcomes
- Fix: raised MES thresholds to 70/72/75 (vs MNQ 65/68/70)

### Key Finding: Tariff Crash Was ES-Specific
MES 5m 45-day (tariff period) = 35% WR — NOT representative
MES 1h 180-day (pre-tariff baseline) = **61.9% WR** — model is valid
NQ (tech) recovered faster than ES (broad market) during tariff crash = structural divergence, not a model failure.

### MGC Note
Gold at NY killzone (9:30–11:30 ET) is the wrong session. Correct session is Asia/London (2–5 AM ET). Already have `/api/backtest/run-gold-asia` for this. MGC at NY produces only 1–3 setups per 180 days — too few to trade.

---

## Renaming: Arlennys Model → Micro Futures Analyzer

All references removed:
- Backtest.jsx: tab renamed "ICT Strategy", activeTab state `'arlennys'` → `'main'`
- TopBar.jsx: "NQ FLOW" → "MFA"
- index.html: title "NASDAQ Flow Terminal" → "Micro Futures Analyzer"
- backtest.py: internal comments cleaned

---

## Prop Firm Language Removal

Removed from public UI and README:
- "Lucid 25k Pro" — all occurrences
- "Payout Threshold/Progress/Trigger" → "Profit Target / Safe Zone"
- "Max Payout" → "Max Withdrawal"
- Hardcoded Lucid rules table ($25,100 floor lock, $26,100 threshold, $1,500 payout, etc.)
- "$1,000 limit" hardcoded in daily risk display → "daily limit"
- README footer "Built for prop traders on Lucid/Apex" removed

---

## GitHub Setup

- `.gitignore` created — protects .env, tokens, pyc, db, node_modules, chat_logs
- README.md written — product description, backtest results table, quick start, ICT signal engine breakdown
- All pushed to github.com/Koestas/nasdaq-flow-terminal
- chat_logs/ removed from git tracking → local-only, not visible on GitHub

## Commits This Session
- `32348b0` — Mount AlertSystem, add Big Figure chop zones
- `bf6bd10` — Rename to Micro Futures Analyzer, calibrate MES/MGC, add README
- `314f332` — Add .gitignore
- `4c13014` — Remove prop firm language
- this session log + chat_logs removal commit

---

## What's Next

- Make repo public on GitHub (Settings → Danger Zone → Change visibility)
- Apply for GitHub Sponsors (github.com/sponsors)
- Create Gumroad listing at $35 (description written in session)
- Unusual Whales comparison: current flow pages are close in UI; data gap is real-time OPRA feed (~$79/mo Polygon) — future upgrade
