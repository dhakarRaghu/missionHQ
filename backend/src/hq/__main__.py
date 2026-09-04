"""Thin runner. All startup lives in the API lifespan (single owner)."""
import logging
import re


class _RedactSecrets(logging.Filter):
    _patterns = (
        re.compile(r"/bot\d+:[A-Za-z0-9_-]+"),          # Telegram bot token in URLs
        re.compile(r"sk-[A-Za-z0-9_-]{8,}"),               # gateway / API keys
        re.compile(r"(?i)(authorization: bearer )\S+"),   # bearer headers
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = msg
        for pat in self._patterns:
            redacted = pat.sub(lambda m: m.group(1) + "[redacted]" if m.lastindex else "[redacted]", redacted)
        if redacted != msg:
            record.msg, record.args = redacted, ()
        return True

import uvicorn

from hq.config import settings


def main() -> None:
    # Our own modules log at INFO ("telegram polling started", "mission hq up").
    # Without this only WARNING and above reach the log file.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    # httpx logs every request URL at INFO, and Telegram's API URL embeds the
    # bot token. Keep third-party HTTP clients at WARNING and scrub any token
    # that still reaches a log line.
    for noisy in ("httpx", "httpcore", "telegram", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger().addFilter(_RedactSecrets())
    s = settings()
    uvicorn.run("hq.api.app:app", host=s.bind_host, port=s.bind_port, log_level="info")


if __name__ == "__main__":
    main()
