"""Pick a stored template without rewriting facts.

Variety is only spacing and whether body emoji may be swapped. The channel
footer, quote, membership link and admin style stay put. A locked post does
not rotate.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.formatting.editor import ContentDecision
from backend.app.formatting.styles import style_for_category

STRUCTURES = ("classic", "airy", "compact")
EMOJI_STYLES = ("list", "scatter", "closing", "title")
_LIST_LINE = re.compile(r"^\s*(?:🔹|🔶|•|▪|·|[-–—]|[0-9۰-۹]{1,2}[).．]|[الفبجد]\))")


@dataclass(frozen=True)
class TemplateChoice:
    template_id: str
    style_id: str
    emoji_style_id: str
    structure_id: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "style_id": self.style_id,
            "emoji_style_id": self.emoji_style_id,
            "structure_id": self.structure_id,
            "reasons": list(self.reasons),
        }


def pick_avoiding_recent(candidates: tuple[str, ...] | list[str], recent_newest_last: list[str]) -> str:
    """Prefer a candidate that was not used in the last three picks."""
    options = list(candidates)
    if not options:
        return "classic"
    if len(options) == 1:
        return options[0]
    window = [item for item in recent_newest_last[-3:] if item in options]
    for candidate in options:
        if candidate not in window:
            return candidate
    last = window[-1] if window else None
    for candidate in options:
        if candidate != last:
            return candidate
    return options[0]


def choose_template(
    decision: ContentDecision,
    *,
    channel_style: str | None,
    recent_structures: list[str] | None = None,
    recent_emoji_styles: list[str] | None = None,
    emoji_enabled: bool = True,
    has_entities: bool = False,
) -> TemplateChoice:
    reasons: list[str] = []
    style_id = (channel_style or "").strip() or style_for_category(decision.category)
    if channel_style:
        reasons.append("style:channel")
    else:
        reasons.append("style:category")

    locked = decision.strategy == "preserve_strict" or has_entities
    if locked:
        structure_id = "locked"
        reasons.append("structure:locked")
    else:
        structure_id = pick_avoiding_recent(STRUCTURES, recent_structures or [])
        reasons.append(f"structure:{structure_id}")

    if not emoji_enabled:
        emoji_style_id = "off"
        reasons.append("emoji:off")
    elif decision.has_options or decision.category in {"exam", "solution"}:
        emoji_style_id = "quiet"
        reasons.append("emoji:quiet")
    else:
        emoji_style_id = pick_avoiding_recent(EMOJI_STYLES, recent_emoji_styles or [])
        reasons.append(f"emoji:{emoji_style_id}")
        if locked:
            reasons.append("words:locked")

    return TemplateChoice(
        template_id=f"{decision.template_family}.{structure_id}",
        style_id=style_id,
        emoji_style_id=emoji_style_id,
        structure_id=structure_id,
        reasons=tuple(reasons),
    )


def apply_structure(text: str, structure_id: str | None) -> str:
    """Change rhythm only. Wording, numbers and list lines stay."""
    if not text or structure_id in {None, "", "classic", "locked"}:
        return text
    if structure_id == "compact":
        return re.sub(r"\n{2,}", "\n", text).strip()
    if structure_id != "airy":
        return text
    out: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        previous = next((item for item in reversed(out) if item != ""), "")
        if out and out[-1] != "" and not _LIST_LINE.match(line) and not _LIST_LINE.match(previous):
            out.append("")
        out.append(line.strip())
    return "\n".join(out).strip()
