from dataclasses import dataclass
import json

DIVIDER = "━━━━━━━━━━━━"

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
    "minimal": StyleConfig(name="Minimal", slug="minimal", divider="", use_divider_bottom=False, add_footer=False),
    "educational": StyleConfig(name="Educational", slug="educational", footer_template="🎓 مشاوره تخصصی کنکور\n📍 عضویت در کانال مشاوره رتبه لند\n👩‍💻 رزرو مشاوره خصوصی: @Rotbeland_support"),
    "premium": StyleConfig(name="Premium", slug="premium", footer_template="🎓 مشاوره رتبه لند"),
    "news": StyleConfig(name="News", slug="news", header_template="📢", footer_template="🎓 رتبه لند | مشاوره و آموزش کنکور"),
    "announcement": StyleConfig(name="Announcement", slug="announcement", header_template="📢 اطلاعیه مهم", footer_template="🎓 رتبه لند"),
    "motivational": StyleConfig(name="Motivational", slug="motivational", footer_template="✨ رتبه لند"),
    "exam": StyleConfig(name="Exam", slug="exam", footer_template="📝 رتبه لند | مشاوره کنکور"),
    "resource": StyleConfig(name="Book / Resource", slug="resource", header_template="📚 معرفی منبع", footer_template="📚 رتبه لند"),
}

def get_style(slug: str) -> StyleConfig:
    return BUILTIN_STYLES.get(slug, BUILTIN_STYLES["educational"])

def style_for_category(category: str) -> str:
    mapping = {
        "announcement": "announcement",
        "news": "news",
        "resource": "resource",
        "book": "resource",
        "exam": "exam",
        "motivational": "motivational",
        "planning": "educational",
        "consulting": "educational",
    }
    return mapping.get(category, "educational")
