from dataclasses import dataclass

@dataclass
class RuleDef:
    name: str
    priority: int
    enabled: bool = True
    category: str | None = None
    action: str = ""

# Built-in rule priorities
RULE_PRIORITIES = {
    "security": 100,
    "entity_protection": 80,
    "category_formatting": 50,
    "emoji_replacement": 30,
    "footer": 10,
}
