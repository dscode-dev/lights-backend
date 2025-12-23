import logging
import sys


class SafeExtraFormatter(logging.Formatter):
    """
    Formatter que não quebra se algum campo do `extra`
    não existir no LogRecord.
    """

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "extra"):
            record.extra = {}
        return super().format(record)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)

    formatter = SafeExtraFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s | %(extra)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)