"""Composition root for the Pi edge agent."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import structlog

from .config import load_bootstrap
from .publisher import publish_forever


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )


async def _async_main() -> None:
    config_path = Path(os.environ.get("SOLAMON_CONFIG", "/etc/solamon/bootstrap.yaml"))
    config = load_bootstrap(config_path)
    _configure_logging(config.log_level)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    await publish_forever(config, stop)


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
