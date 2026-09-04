"""Telegram adapter: owner-locked chat, approval buttons, durable outbox drain.

Manual PTB lifecycle (initialize/start/start_polling) so it shares the one
asyncio loop with DBOS and FastAPI. Callback data stays under 64 bytes:
``t:<ticket_uuid>:a`` / ``t:<ticket_uuid>:d``.

Self-healing: a failed ``start`` (for example a Telegram timeout right after a
restart) does not disable the channel for good. ``ensure_started`` retries
with exponential backoff (30 s, 60 s, 120 s ... up to 10 min) and is called
from ``drain_outbox``, which the engine ticks every minute, so queued outbox
rows go out as soon as Telegram is reachable again.
"""

from __future__ import annotations

import json
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from hq import board, db, engagement
from hq.config import settings
from hq.dbos_app import DBOS

log = logging.getLogger(__name__)
_app: Application | None = None
REPLY_CHUNK = 3500  # Telegram caps a message at 4096 chars

# Reconnect state (module-level so any caller sees the same backoff).
RETRY_BASE_S = 30.0
RETRY_MAX_S = 600.0
attempts: int = 0            # consecutive failed start attempts
next_retry_at: float = 0.0   # time.monotonic() before which no retry happens
last_error: str | None = None
_starting: bool = False      # re-entrancy guard: one start at a time


def _owner_only(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.id == settings().owner_chat_id


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _owner_only(update) or not update.message or not update.message.text:
        return
    from hq import engine  # late import to avoid cycles

    text = update.message.text.strip()
    session = await _session_for(update)
    await engagement.record_owner_action(
        "telegram", "command" if text.startswith("/") else "message")

    if text.startswith("/"):
        reply = await _command(text, session)
        for chunk in _chunks(reply, REPLY_CHUNK):
            await update.message.reply_text(chunk)
        return

    agent = session["agent"]
    if text.startswith("@"):
        first, _, rest = text.partition(" ")
        candidate = first[1:]
        if candidate in engine.registered_agents():
            agent = candidate
            text = rest.strip() or "hello"
            await db.execute("UPDATE hq.sessions SET agent = %s WHERE id = %s",
                             (agent, session["id"]))
    # Telegram message ids are unique per chat, so a redelivered update maps
    # to the same workflow id and cannot start a second run.
    await engine.enqueue_chat(
        str(session["id"]), text,
        client_id=f"tg-{update.message.chat_id}-{update.message.message_id}",
    )


async def _command(text: str, session: dict) -> str:
    from hq import engine, safety

    cmd, _, arg = text.partition(" ")
    arg = arg.strip()
    if cmd == "/board":
        rows = await db.fetch(
            "SELECT title, agent, status FROM hq.tasks WHERE status NOT IN ('done','failed')"
            " ORDER BY updated_at DESC LIMIT 15"
        )
        return "\n".join(f"[{r['status']}] {r['agent']}: {r['title'][:60]}" for r in rows) or "board empty"
    if cmd == "/tickets":
        rows = await db.fetch(
            "SELECT id::text, tool_name FROM hq.tickets WHERE status = 'pending'")
        return "\n".join(f"{r['id'][:8]}… {r['tool_name']}" for r in rows) or "no pending tickets"
    if cmd == "/pause" and arg:
        await safety.set_agent_paused(arg, True)
        return f"paused {arg}"
    if cmd == "/resume" and arg:
        await safety.set_agent_paused(arg, False)
        return f"resumed {arg}"
    if cmd == "/costs":
        spend = await safety.spend_today_usd()
        return f"today: ${spend:.2f} of ${settings().daily_spend_cap_usd:.2f} cap"
    if cmd == "/agents":
        return "\n".join(sorted(engine.registered_agents()))
    if cmd == "/digest":
        from hq import digest

        return await digest.build_digest(None) or "nothing to report since the last digest"
    if cmd == "/week":
        # Shows the value-week status; starts the week if nobody did yet.
        await engagement.start_value_week()
        return engagement.format_report(await engagement.value_week_status())
    if cmd == "/drafts":
        import asyncio

        from hq.tools import factory_tools

        drafts = await asyncio.to_thread(factory_tools.list_drafts)
        return "\n".join(
            f"{d['name']}: {d['description'][:80]} | tools: {', '.join(d['tools'])}"
            f" | cron: {d['cron'][0]['schedule'] if d['cron'] else 'none'}"
            for d in drafts
        ) or "no drafts (the factory agent creates them; activate with /activate <name>)"
    if cmd == "/activate" and arg:
        import asyncio

        from hq.tools import factory_tools

        try:
            reply = await asyncio.to_thread(factory_tools.activate_agent, arg)
        except (FileNotFoundError, ValueError) as exc:
            return f"not activated: {exc}"
        factory_tools.schedule_restart()  # 2 s delay: the reply goes out first; launchd restarts us
        return reply
    return (
        "commands: /board /tickets /costs /agents /digest /week /drafts"
        " /pause <agent> /resume <agent> /activate <agent>"
    )


def _chunks(text: str, size: int) -> list[str]:
    """Split a reply into Telegram-sized pieces, preferring line breaks."""
    out: list[str] = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut <= 0:
            cut = size
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text:
        out.append(text)
    return out


async def _on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()  # required or the client spins
    if not _owner_only(update):
        return
    try:
        _, ticket_id, code = (query.data or "").split(":")
    except ValueError:
        return
    verdict = "approved" if code == "a" else "denied"
    await engagement.record_owner_action(
        "telegram", "approve" if verdict == "approved" else "deny")
    row = await board.resolve_ticket(ticket_id, verdict, via="telegram")
    if row is None:
        await query.edit_message_text(f"(already resolved) ticket {ticket_id[:8]}…")
        return
    await DBOS.send_async(row["wf_id"], f"{ticket_id}:{verdict}", topic="approval")
    await query.edit_message_text(f"{verdict}: {row['tool_name']} (ticket {ticket_id[:8]}…)")


async def _session_for(update: Update) -> dict:
    assert update.effective_chat is not None  # _owner_only already checked
    chat_id = str(update.effective_chat.id)
    row = await db.fetchone(
        """
        INSERT INTO hq.sessions (channel, channel_user_id, thread_id)
        VALUES ('telegram', %s, '')
        ON CONFLICT (channel, channel_user_id, thread_id)
        DO UPDATE SET last_active = now()
        RETURNING id::text, conversation_id, agent
        """,
        (chat_id,),
    )
    assert row is not None
    return row


# --- outbox ------------------------------------------------------------------

async def drain_outbox() -> None:
    """Send unsent outbox rows to the owner. Safe to call from anywhere.
    Reconnects the channel first when it is down (backoff-limited)."""
    if not await ensure_started():
        return
    rows = await db.fetch(
        "SELECT id, intent FROM hq.outbox WHERE sent_at IS NULL AND attempts < 5"
        " ORDER BY id LIMIT 20"
    )
    for row in rows:
        intent = row["intent"] if isinstance(row["intent"], dict) else json.loads(row["intent"])
        try:
            await _send_intent(intent)
            await db.execute("UPDATE hq.outbox SET sent_at = now() WHERE id = %s", (row["id"],))
        except Exception as exc:  # noqa: BLE001
            await db.execute(
                "UPDATE hq.outbox SET attempts = attempts + 1, last_error = %s WHERE id = %s",
                (str(exc)[:500], row["id"]),
            )


async def _send_intent(intent: dict) -> None:
    assert _app is not None
    bot = _app.bot
    owner = settings().owner_chat_id
    kind = intent.get("kind")
    if kind == "confirm":
        ticket = intent["ticket_id"]
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"t:{ticket}:a"),
            InlineKeyboardButton("❌ Reject", callback_data=f"t:{ticket}:d"),
        ]])
        args = json.dumps(intent.get("args", {}), indent=0)[:800]
        await bot.send_message(owner, f"{intent['summary']}\n\nargs: {args}", reply_markup=markup)
    else:
        await bot.send_message(owner, intent.get("text", "")[:4000])


# --- lifecycle ---------------------------------------------------------------

def _configured() -> bool:
    token = settings().telegram_bot_token
    return bool(token) and token != "replace-me"


def _polling() -> bool:
    return _app is not None and _app.updater is not None and bool(_app.updater.running)


def _backoff_s(n: int) -> float:
    """30 s after the first failure, doubling, capped at RETRY_MAX_S."""
    return min(RETRY_BASE_S * (2 ** max(0, n - 1)), RETRY_MAX_S)


async def _discard_app(app: Application) -> None:
    """Tear down a half-started Application; errors here are only logged."""
    try:
        if app.updater is not None and app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
    except Exception as exc:  # noqa: BLE001 — cleanup of a broken app
        log.debug("telegram cleanup after failed start: %s", exc)


async def start() -> bool:
    """Connect and start polling. Idempotent: returns True at once when the
    channel is already up. Best-effort: a missing or bad token, or a Telegram
    timeout, never stops the rest of Mission HQ (the web console still
    works); ``ensure_started`` retries later. Returns whether polling is on."""
    global _app, _starting, attempts, next_retry_at, last_error
    if _polling():
        return True
    if not _configured():
        if last_error is None:
            log.warning("TELEGRAM_BOT_TOKEN not configured - Telegram channel disabled")
        last_error = "TELEGRAM_BOT_TOKEN not configured"
        return False
    if _starting:
        return False
    _starting = True
    app: Application | None = None
    try:
        app = Application.builder().token(settings().telegram_bot_token).build()
        app.add_handler(MessageHandler(filters.TEXT, _on_message))
        app.add_handler(CallbackQueryHandler(_on_callback))
        await app.initialize()
        await app.start()
        assert app.updater is not None
        await app.updater.start_polling(drop_pending_updates=True)
    except Exception as exc:  # noqa: BLE001 — never take the process down
        if app is not None:
            await _discard_app(app)
        _app = None
        attempts += 1
        last_error = f"{type(exc).__name__}: {exc}"[:300]
        wait = _backoff_s(attempts)
        next_retry_at = time.monotonic() + wait
        log.warning("telegram start failed (attempt %d, retry in %.0fs): %s",
                    attempts, wait, last_error)
        return False
    finally:
        _starting = False
    _app = app
    if attempts:
        log.info("telegram polling recovered after %d failed attempt(s)", attempts)
    else:
        log.info("telegram polling started")
    attempts = 0
    next_retry_at = 0.0
    last_error = None
    return True


async def ensure_started() -> bool:
    """True when polling is on. When it is down and the backoff window has
    passed, try ``start`` again (30 s, 60 s, 120 s ... max 10 min between
    attempts). Cheap when the channel is up or not configured."""
    if _polling():
        return True
    if not _configured():
        return False
    if time.monotonic() < next_retry_at:
        return False
    return await start()


def channel_status() -> dict:
    """{enabled, polling, last_error, attempts, next_retry_at}; next_retry_at
    is seconds from now until the next reconnect attempt (0 when none is due
    or the channel is up)."""
    return {
        "enabled": _configured(),
        "polling": _polling(),
        "last_error": last_error,
        "attempts": attempts,
        "next_retry_at": max(0.0, round(next_retry_at - time.monotonic(), 1)) if not _polling() else 0.0,
    }


async def stop() -> None:
    global _app
    if _app is None:
        return
    app, _app = _app, None
    await _discard_app(app)
