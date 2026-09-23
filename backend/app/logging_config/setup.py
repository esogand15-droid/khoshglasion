import logging
import re
import sys

_SECRET = re.compile(
    r"(nvapi-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,}|\b\d{6,}:[A-Za-z0-9_-]{20,})",
    re.IGNORECASE,
)


def redact_secrets(value):
    if not isinstance(value, str) or not value:
        return value
    return _SECRET.sub("***", value)


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: redact_secrets(item) for key, item in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_secrets(item) for item in record.args)
        return True


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger().addFilter(RedactSecretsFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
