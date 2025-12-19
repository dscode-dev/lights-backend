from __future__ import annotations

import logging
import sys
from typing import Any, Dict


class JsonLikeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        # add extras if present
        for k, v in record.__dict__.items():
            if k.startswith("_"):
                continue
            if k in ("name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                     "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                     "created", "msecs", "relativeCreated", "thread", "threadName",
                     "processName", "process"):
                continue
            base.setdefault("extra", {})[k] = v
        return str(base)


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(JsonLikeFormatter())

    # avoid duplicate handlers in reload
    root.handlers.clear()
    root.addHandler(handler)
