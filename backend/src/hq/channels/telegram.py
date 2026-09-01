"""Telegram adapter: owner-locked chat, approval buttons, durable outbox drain.

Manual PTB lifecycle (initialize/start/start_polling) so it shares the one
asyncio loop with DBOS and FastAPI. Callback data stays under 64 bytes:
``t:<ticket_uuid>:a`` / ``t:<ticket_uuid>:d``.
"""

from __future__ import annotations

import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from hq import board, db
from hq.config import settings
from hq.dbos_app import DBOS

log = logging.getLogger(__name__)
_app: Application | None = None


def _owner_only(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.id == settings().owner_chat_id


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _owner_only(update) or not update.message or not update.message.text:
        return
    from hq import engine  # late import to avoid cycles

    text = update.message.text.strip()
    session = await _session_for(update)

    if text.startswith("/"):
        reply = await _command(text, session)
        if reply:
            await update.message.reply_text(reply)
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
    await engine._queues["chat"].enqueue_async(engine.chat_turn, str(session["id"]), text)


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
    return "commands: /board /tickets /costs /agents /pause <agent> /resume <agent>"


async def _on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()  # required or the client spins
    if not _owner_only(update):
        return
    try:
        _, ticket_id, code = query.data.split(":")
    except (AttributeError, ValueError):
        return
    verdict = "approved" if code == "a" else "denied"
    row = await board.resolve_ticket(ticket_id, verdict, via="telegram")
    if row is None:
        await query.edit_message_text(f"(already resolved) ticket {ticket_id[:8]}…")
        return
    await DBOS.send_async(row["wf_id"], f"{ticket_id}:{verdict}", topic="approval")
    await query.edit_message_text(f"{verdict}: {row['tool_name']} (ticket {ticket_id[:8]}…)")


async def _session_for(update: Update) -> dict:
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
    return row


# --- outbox ------------------------------------------------------------------

async def drain_outbox() -> None:
    """Send unsent outbox rows to the owner. Safe to call from anywhere."""
    if _app is None:
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

async def start() -> None:
    """Best-effort: a missing or bad token disables the channel but must never
    stop the rest of Mission HQ from running (the web console still works)."""
    global _app
    token = settings().telegram_bot_token
    if not token or token == "replace-me":
        log.warning("TELEGRAM_BOT_TOKEN not configured — Telegram channel disabled")
        return
    try:
        _app = Application.builder().token(token).build()
        _app.add_handler(MessageHandler(filters.TEXT, _on_message))
        _app.add_handler(CallbackQueryHandler(_on_callback))
        await _app.initialize()
        await _app.start()
        await _app.updater.start_polling(drop_pending_updates=True)
        log.info("telegram polling started")
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram channel disabled: %s", exc)
        _app = None


async def stop() -> None:
    global _app
    if _app is None:
        return
    await _app.updater.stop()
    await _app.stop()
    await _app.shutdown()
    _app = None
