import logging
import os
import sys


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL")
    if not level:
        raise RuntimeError("Missing required env var: LOG_LEVEL")
    level = level.upper()
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
