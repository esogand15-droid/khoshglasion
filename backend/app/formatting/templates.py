"""Channel chrome for رتبه لند.

Templates add structure only. They never invent facts, ranks, dates, prices,
or lesson names. The admin's sentences stay the admin's sentences.
"""
from __future__ import annotations

MEMBERSHIP_TEXT = "عضویت در کانال مشاوره رتبه لند"
SUPPORT_LABEL = "رزرو مشاوره خصوصی"
DEFAULT_CHANNEL_URL = "https://t.me/Rotbeland1"
DEFAULT_SUPPORT = "Rotbeland_support"
LONG_RULE = "━━━━━━━━"
SHORT_RULE = "━━━━"


def support_handle(raw: str | None) -> str:
    handle = (raw or DEFAULT_SUPPORT).strip().lstrip("@")
    return handle or DEFAULT_SUPPORT


def branded_footer(support: str | None = None) -> str:
    handle = support_handle(support)
    return f"{MEMBERSHIP_TEXT}\n{SUPPORT_LABEL}:\n\u200e@{handle}"


def plain_divider() -> str:
    return f"{LONG_RULE}\n{SHORT_RULE}"
