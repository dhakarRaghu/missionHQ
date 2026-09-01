"""Channel contract. Core code emits semantic OutboundIntents (plain dicts with a
``kind``); each adapter renders them with its own affordances. Core never
imports a platform SDK.

Intent kinds: ``text`` {text}, ``confirm`` {ticket_id, summary, args},
``choice`` {text, options}, ``attachment`` {path, caption}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class InboundMessage:
    channel: str
    channel_user_id: str
    thread_id: str
    text: str
    raw: Any = None


class Channel(Protocol):
    name: str
    capabilities: set[str]

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, chat_ref: str, intent: dict[str, Any]) -> None: ...
