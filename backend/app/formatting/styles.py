from dataclasses import dataclass
import json

DIVIDER = "━━━━━━━━━━━━"

DEFAULT_FOOTER = (
    "عضویت در کانال مشاوره رتبه لند\n"
    "رزرو مشاوره خصوصی:\n"
    "\u200e@Rotbeland_support"
)


@dataclass
class StyleConfig:
    name: str
    slug: str
    header_template: str | None = None
    footer_template: str | None = None
    divider: str = DIVIDER
    use_divider_top: bool = False
    use_divider_bottom: bool = True
    add_footer: bool = True
    spacing: str = "\n\n"


BUILTIN_STYLES: dict[str, StyleConfig] = {
    "minimal": StyleConfig(name="مینیمال", slug="minimal", divider="", use_divider_bottom=False, add_footer=False),
    "educational": StyleConfig(name="آموزشی رتبه لند", slug="educational", footer_template=DEFAULT_FOOTER),
    "premium": StyleConfig(name="پرمیوم", slug="premium", footer_template=DEFAULT_FOOTER),
    "news": StyleConfig(name="خبر", slug="news", header_template="📢", footer_template=DEFAULT_FOOTER),
    "announcement": StyleConfig(name="اطلاعیه", slug="announcement", header_template="📢 اطلاعیه", footer_template=DEFAULT_FOOTER),
    "motivational": StyleConfig(name="انگیزشی", slug="motivational", footer_template=DEFAULT_FOOTER),
    "exam": StyleConfig(name="آزمون", slug="exam", footer_template=DEFAULT_FOOTER),
    "resource": StyleConfig(name="منبع", slug="resource", footer_template=DEFAULT_FOOTER),
}


def get_style(slug: str | None) -> StyleConfig:
    if not slug:
        return BUILTIN_STYLES["educational"]
    return BUILTIN_STYLES.get(slug, BUILTIN_STYLES["educational"])


def style_for_category(category: str) -> str:
    mapping = {
        "announcement": "announcement",
        "news": "news",
        "resource": "resource",
        "book": "resource",
        "exam": "exam",
        "registration": "announcement",
        "motivational": "motivational",
        "planning": "educational",
        "consulting": "educational",
        "rank": "premium",
        "discount": "premium",
        "solution": "exam",
        "experience": "premium",
        "service": "educational",
        "class_intro": "announcement",
        "product": "premium",
        "occasion": "motivational",
    }
    return mapping.get(category, "educational")


def style_from_payload(slug: str, name: str, config: dict | str | None) -> StyleConfig:
    data = config
    if isinstance(config, str):
        try:
            data = json.loads(config or "{}")
        except json.JSONDecodeError:
            data = {}
    data = data or {}
    return StyleConfig(
        name=name or slug,
        slug=slug,
        header_template=data.get("header") or data.get("header_template"),
        footer_template=data.get("footer") or data.get("footer_template"),
        divider=data.get("divider", DIVIDER) or "",
        add_footer=bool(data.get("add_footer", True)),
        use_divider_bottom=bool(data.get("use_divider_bottom", True)),
    )
