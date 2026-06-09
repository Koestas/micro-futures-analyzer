"""Telegram alert provider.

Setup (one-time, 2 minutes):
  1. Message @BotFather on Telegram → /newbot → name it anything → get TOKEN
  2. Message your new bot once (any text)
  3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates → copy chat.id
  4. Add to backend/.env:
       TELEGRAM_BOT_TOKEN=7123456789:AAF...
       TELEGRAM_CHAT_ID=123456789

All alert functions are fire-and-forget — they never raise, never block the bot.
"""

import os
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/sendMessage"
_enabled: bool | None = None   # None = not yet checked


def _cfg() -> tuple[str, str]:
    return os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    global _enabled
    if _enabled is None:
        t, c = _cfg()
        _enabled = bool(t and c)
    return _enabled


async def send(text: str) -> bool:
    if not is_configured():
        return False
    token, chat_id = _cfg()
    url = _BASE.format(token=token)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(url, json={
                "chat_id":    chat_id,
                "text":       text,
                "parse_mode": "HTML",
            })
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


# ── Pre-formatted alert helpers ──────────────────────────────────────────────

async def alert_trade_opened(setup: dict):
    sym  = setup.get("instrument", "?")
    side = "🟢 LONG" if setup.get("direction") == "bullish" else "🔴 SHORT"
    ct   = setup.get("contracts", 1)
    entry = setup.get("entry_price", 0)
    sl    = setup.get("sl_price", 0)
    tp    = setup.get("tp_price", 0)
    score = setup.get("score", 0)
    sess  = setup.get("session", "")
    risk  = setup.get("usd_risk", 0)
    r2    = setup.get("usd_2r", 0)
    await send(
        f"{side} <b>{sym}</b> ×{ct}\n"
        f"Entry: <code>{entry:.2f}</code>\n"
        f"Stop:  <code>{sl:.2f}</code>  (−${risk:.0f})\n"
        f"2R TP: <code>{tp:.2f}</code>  (+${r2:.0f})\n"
        f"Score: {score}/100 | {sess}"
    )


async def alert_partial_close(sym: str, closed: int, remaining: int, locked_pnl: float):
    await send(
        f"🟡 <b>PARTIAL CLOSE</b> {sym}\n"
        f"Closed {closed} contracts — {remaining} runners left\n"
        f"Gain locked: ~${locked_pnl:.0f}"
    )


async def alert_trail_activated(total_pnl: float, floor: float):
    await send(
        f"⚡ <b>TRAIL MODE ON</b>\n"
        f"Daily P&amp;L: <b>${total_pnl:.0f}</b>\n"
        f"Floor locked at: ${floor:.0f}\n"
        f"Runners still open — stop moving up every $50"
    )


async def alert_stop_trailed(sym: str, new_stop: float, floor: float):
    await send(
        f"📈 Stop trailed → <b>{sym}</b> @ <code>{new_stop:.2f}</code>\n"
        f"P&amp;L floor now: ${floor:.0f}"
    )


async def alert_trade_closed(sym: str, direction: str, pnl: float, daily_pnl: float, session: str):
    emoji = "✅" if pnl > 0 else "❌"
    result = "WIN" if pnl > 0 else "LOSS"
    await send(
        f"{emoji} <b>TRADE CLOSED — {result}</b>\n"
        f"{sym} {'LONG' if direction == 'bullish' else 'SHORT'}\n"
        f"Trade P&amp;L: <b>${pnl:+.0f}</b>\n"
        f"Daily total: <b>${daily_pnl:+.0f}</b> | {session}"
    )


async def alert_daily_target(daily_pnl: float):
    await send(
        f"🎯 <b>DAILY TARGET HIT — ${daily_pnl:.0f}</b>\n"
        f"Bot switching to trail mode.\n"
        f"Runners active. Stop protecting ${daily_pnl:.0f} floor."
    )


async def alert_daily_halt(daily_pnl: float, limit: float):
    await send(
        f"🛑 <b>DAILY LOSS LIMIT HIT</b>\n"
        f"Loss: ${abs(daily_pnl):.0f} / limit ${limit:.0f}\n"
        f"Bot halted for today. Resumes 6:15 PM ET tomorrow."
    )


async def alert_news_block(event: str, minutes: int, session: str):
    await send(
        f"📰 <b>NEWS BLOCK — skipping trade</b>\n"
        f"<b>{event}</b> in {minutes} min\n"
        f"Session: {session} — will resume after event"
    )


async def alert_bot_started():
    await send("🤖 <b>MFA Bot started</b> — 22-hr coverage active\nTarget: $800/day | Limit: $1,000 loss")


async def alert_bot_stopped():
    await send("⏹ <b>MFA Bot stopped</b>")
