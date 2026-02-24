from __future__ import annotations

import logging
import os
import sys


_CONFIGURED = False


def _configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    if not root.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stdout,
        )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_logging()
    return logging.getLogger(name)


def warn_exc(logger: logging.Logger, msg: str, **kv) -> None:
    if kv:
        logger.warning(msg, exc_info=True, extra=kv)
    else:
        logger.warning(msg, exc_info=True)
