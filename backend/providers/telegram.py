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


async def alert_daily_summary(pnl: float, trades: int, scalps: int, wins: int, losses: int, best: float, worst: float):
    emoji = "📈" if pnl >= 0 else "📉"
    await send(
        f"{emoji} <b>Daily Summary — 3:50 PM ET</b>\n"
        f"Net P&amp;L: <b>${pnl:+.0f}</b>\n"
        f"ICT swings: {trades} trades ({wins}W/{losses}L)\n"
        f"Scalps: {scalps}\n"
        f"Best trade: <b>${best:+.0f}</b>  |  Worst: <b>${worst:+.0f}</b>\n"
        f"Bot going flat — resumes 6 PM ET"
    )


async def alert_bot_started():
    await send("🤖 <b>MFA Bot started</b> — 22-hr coverage active\nTarget: $500+ | Limit: $1,000 loss")


async def alert_bot_stopped():
    await send("⏹ <b>MFA Bot stopped</b>")


async def alert_trade_rating_prompt(trade_ref: str, sym: str, direction: str, pnl: float):
    """Send a rating prompt after a trade closes. User replies 👍/👎/skip."""
    side = "LONG" if direction == "bullish" else "SHORT"
    emoji = "✅" if pnl >= 0 else "❌"
    await send(
        f"{emoji} <b>Rate this trade</b> (helps the bot learn)\n"
        f"{sym} {side}  P&amp;L: <b>${pnl:+.0f}</b>\n"
        f"Reply <b>👍</b> good setup  |  <b>👎</b> bad setup  |  <b>skip</b>\n"
        f"<code>ref:{trade_ref}</code>"
    )


# ── Rating reply poller ───────────────────────────────────────────────────────

_last_update_id: int = 0


async def poll_ratings():
    """Background task — polls Telegram for rating replies and writes to learning DB.
    Runs every 60s. Only processes messages containing 👍/👎 that quote a ref: tag."""
    global _last_update_id
    if not is_configured():
        return
    token, _ = _cfg()
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"offset": _last_update_id + 1, "limit": 20})
            data = resp.json()
        updates = data.get("result", [])
        for upd in updates:
            _last_update_id = upd["update_id"]
            msg = upd.get("message", {})
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            # Look for rating + ref tag in reply chain
            reply = msg.get("reply_to_message", {})
            ref_text = (reply.get("text") or "") + text
            import re
            ref_match = re.search(r"ref:(\S+)", ref_text)
            if not ref_match:
                continue
            trade_ref = ref_match.group(1)
            if "👍" in text:
                rating = 1
            elif "👎" in text:
                rating = -1
            else:
                continue
            try:
                from engines.learning import set_user_rating
                set_user_rating(trade_ref, rating)
                await send(f"✓ Rating saved for <code>{trade_ref}</code>: {'👍 good' if rating == 1 else '👎 bad'}")
            except Exception as e:
                logger.warning(f"Rating save failed: {e}")
    except Exception as e:
        logger.warning(f"poll_ratings error: {e}")
