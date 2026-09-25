"""Decide how a رتبه لند post may be edited. This does not rewrite text.

Suitability beats variety. Fact-heavy posts stay preserve-only for templates.
The model may still read them in tidy mode. Exam options and short notes are
not sent to the model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re

from backend.app.formatting.category import detect_category
from backend.app.formatting.richtext import quote_texts
from backend.app.formatting.textutil import extract_protected_tokens, missing_long_numbers

OPTION_RE = re.compile(r"(?m)(?:^|\s)(?:[1-4۱-۴][).．]|[الفبجد]\))")
STRICT_CATEGORIES = {"exam", "solution", "rank", "news", "announcement", "registration", "experience"}


@dataclass
class ContentDecision:
    category: str
    length_class: str
    strategy: str
    template_family: str
    reasons: list[str] = field(default_factory=list)
    has_quote: bool = False
    has_link: bool = False
    has_number: bool = False
    has_options: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _length_class(text: str) -> str:
    size = len(text.strip())
    if size < 80:
        return "short"
    if size > 700:
        return "long"
    return "medium"


def _template_family(category: str, length_class: str) -> str:
    if length_class == "short":
        return "minimal"
    if category in {"announcement", "registration", "news"}:
        return "announcement"
    if category in {"exam", "solution", "resource", "planning", "lesson"}:
        return "educational"
    if category in {"rank", "experience"}:
        return "result"
    if category in {"motivational", "consulting"}:
        return "consultation"
    return "educational"


def analyze_post(text: str | None, entities: list | None = None) -> ContentDecision:
    raw = text or ""
    category = detect_category(raw)
    length_class = _length_class(raw)
    quotes = quote_texts(raw, entities)
    protected = extract_protected_tokens(raw)
    has_number = bool(missing_long_numbers(raw, ""))
    has_options = bool(OPTION_RE.search(raw))
    has_link = any(token.startswith("http") or token.startswith("@") for token in protected)
    reasons: list[str] = [f"category:{category}", f"length:{length_class}"]

    strategy = "structure_only"
    if quotes:
        reasons.append("has_quote")
    if has_number:
        reasons.append("has_number")
    if has_options:
        reasons.append("has_options")
    if has_link:
        reasons.append("has_link")
    if category in STRICT_CATEGORIES or quotes or has_number or has_options or length_class == "short":
        strategy = "preserve_strict"
        reasons.append("facts_or_structure_locked")
    elif category in {"motivational", "consulting", "general"} and length_class == "long":
        strategy = "light_edit"
        reasons.append("long_soft_content")

    return ContentDecision(
        category=category,
        length_class=length_class,
        strategy=strategy,
        template_family=_template_family(category, length_class),
        reasons=reasons,
        has_quote=bool(quotes),
        has_link=has_link,
        has_number=has_number,
        has_options=has_options,
    )


REWRITE_CATEGORIES = {"motivational", "consulting", "general", "planning", "qa", "occasion", "ad", "service"}


def ai_plan(decision: ContentDecision) -> str:
    """rewrite, tidy, or skip.

    skip keeps exam options, answer keys, and very short notes untouched.
    tidy means the model reads a fact-heavy post and may only restack it.
    rewrite is the lighter edit used for soft posts.
    """
    if decision.has_options or decision.category == "solution":
        return "skip"
    if decision.length_class == "short":
        return "skip"
    if decision.strategy == "light_edit" or decision.category in REWRITE_CATEGORIES:
        return "rewrite"
    return "tidy"
