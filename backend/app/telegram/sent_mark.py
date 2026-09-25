"""Remember posts this process just sent, before the database commit lands.

The channel editor must still restyle a post the admin typed. It must not
restyle a post the autopost path just published. The webhook can arrive while
the send is still in flight, so the mark is recorded before Telegram is called.
"""
from __future__ import annotations

from collections import deque

_IDS: deque[tuple[int, int]] = deque(maxlen=500)
_TEXTS: deque[tuple[int, str]] = deque(maxlen=500)
_PENDING: list[tuple[int, int]] = []


def fingerprint(text: str) -> str:
    return "".join((text or "").split())[:800]


def remember_outgoing(chat_id: int, text: str) -> None:
    compact = fingerprint(text)
    if len(compact) < 24:
        return
    _TEXTS.append((int(chat_id), compact))


def forget_outgoing(chat_id: int, text: str) -> None:
    compact = fingerprint(text)
    if not compact:
        return
    kept = deque(((cid, known) for cid, known in _TEXTS if not (cid == int(chat_id) and known == compact)), maxlen=500)
    _TEXTS.clear()
    _TEXTS.extend(kept)


def remember_sent_id(chat_id: int, message_id: int) -> None:
    pair = (int(chat_id), int(message_id))
    _IDS.append(pair)
    _PENDING.append(pair)


def drain_sent_ids(chat_id: int) -> list[int]:
    found: list[int] = []
    kept: list[tuple[int, int]] = []
    for cid, mid in _PENDING:
        if cid == int(chat_id):
            found.append(mid)
        else:
            kept.append((cid, mid))
    _PENDING[:] = kept
    return found


def automation_already_sent(chat_id: int, message_id: int | None, text: str) -> bool:
    """True only for a message this process published. An admin's own post is not here."""
    if message_id and (int(chat_id), int(message_id)) in _IDS:
        return True
    compact = fingerprint(text)
    if len(compact) < 40:
        return False
    for cid, known in _TEXTS:
        if cid != int(chat_id) or len(known) < 40:
            continue
        if known == compact:
            return True
        if known in compact and len(compact) - len(known) < 180:
            return True
        if compact in known and len(known) - len(compact) < 180:
            return True
    return False
