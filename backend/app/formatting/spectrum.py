"""Emoji spectra. A news post only borrows news glyphs, not the whole library."""

from __future__ import annotations

SPECTRA = {
    "news": "خبر",
    "announcement": "اطلاعیه",
    "fun": "فان",
    "guide": "راهنما",
    "alert": "هشدار",
    "consulting": "مشاوره",
    "general": "عمومی",
}

_ALIASES = {
    "flash": "news",
    "announce": "announcement",
    "registration": "announcement",
    "exam": "guide",
    "lesson": "guide",
    "rank": "news",
    "resource": "guide",
    "motivational": "fun",
    "consult": "consulting",
    "planning": "guide",
    "discount": "fun",
}

_GUESS = {
    "📌": "news",
    "📰": "news",
    "ℹ️": "news",
    "📢": "announcement",
    "📣": "announcement",
    "🔔": "announcement",
    "🆕": "announcement",
    "✅": "announcement",
    "😂": "fun",
    "🤣": "fun",
    "😄": "fun",
    "😜": "fun",
    "🤪": "fun",
    "😎": "fun",
    "🔥": "fun",
    "🎉": "fun",
    "📚": "guide",
    "📝": "guide",
    "✏️": "guide",
    "💡": "guide",
    "🎯": "guide",
    "📖": "guide",
    "⚠️": "alert",
    "🚨": "alert",
    "❌": "alert",
    "❗": "alert",
    "⛔": "alert",
    "💬": "consulting",
    "🤝": "consulting",
    "🧠": "consulting",
    "✨": "general",
    "⭐": "general",
    "💪": "general",
    "🌴": "fun",
    "❤️": "fun",
    "❤": "fun",
    "😍": "fun",
    "😭": "fun",
    "😱": "fun",
    "⚡": "alert",
    "📍": "news",
    "💻": "guide",
    "🎓": "guide",
    "🏆": "news",
    "💰": "announcement",
    "🤔": "consulting",
    "🙏": "consulting",
}


def spectrum_of(value: str | None) -> str:
    key = (value or "").strip().lower()
    if key in SPECTRA:
        return key
    return _ALIASES.get(key, "general")


def spectrum_label(value: str | None) -> str:
    return SPECTRA.get(spectrum_of(value), "عمومی")


def guess_spectrum(emoji: str) -> str | None:
    glyph = (emoji or "").strip()
    if not glyph:
        return None
    if glyph in _GUESS:
        return _GUESS[glyph]
    for char in glyph:
        if char in _GUESS:
            return _GUESS[char]
    return None


def parse_ai_spectra(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip().strip("-").strip().replace(":", "=", 1)
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        key = right.strip().lower().split()[0].strip(".,")
        if key in SPECTRA and left.strip():
            found[left.strip()] = key
    return found
