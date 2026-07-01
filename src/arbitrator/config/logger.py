"""
Project-wide logging based on loguru with rotation and file routing.

Single line format for console and files. Channel routing via bracket-style
``logger["subdir/name.log"]`` allows ad-hoc per-feature log files under the
configured log directory.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Protocol, cast

from loguru import logger as loguru_logger

if TYPE_CHECKING:
    from loguru import Message, Record


_ch_file_root: Path = Path("logs")


class ArbitrageLogger(Protocol):
    """Narrow loguru surface used in this project (loguru stubs leave methods untyped)."""

    def debug(self, __message: str, *args: object, **kwargs: object) -> None: ...

    def info(self, __message: str, *args: object, **kwargs: object) -> None: ...

    def warning(self, __message: str, *args: object, **kwargs: object) -> None: ...

    def error(self, __message: str, *args: object, **kwargs: object) -> None: ...

    def exception(self, __message: str, *args: object, **kwargs: object) -> None: ...


UNIFIED_LOG_FORMAT_PLAIN = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | [{name}:{function}:{line}] - {message}"
)

CONSOLE_FORMAT = (
    "<white>{time:YYYY-MM-DD HH:mm:ss}</white> | "
    "<level>{level: <8}</level> | "
    "[<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>] - "
    "<level>{message}</level>"
)

FILE_FORMAT = UNIFIED_LOG_FORMAT_PLAIN

_stdlib_intercept_installed = False


def _record_routed_channel_file(record: Record) -> bool:
    extra = record["extra"]
    return extra.get("ch_log_subdir") is not None


def _ch_file_sink(message: Message) -> None:
    extra = message.record["extra"]
    sub = extra.get("ch_log_subdir")
    fn = extra.get("ch_log_filename")
    if not isinstance(sub, str) or not isinstance(fn, str):
        return
    dest = _ch_file_root / sub / fn
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "a", encoding="utf-8") as f:
        f.write(str(message))


_MAX_INTERCEPTED_MESSAGE_LEN = 2000

_NOISY_STDLIB_LOGGERS_WARNING: tuple[str, ...] = (
    "ccxt",
    "ccxt.base",
    "ccxt.base.exchange",
    "ccxt.async_support",
    "ccxt.async_support.base",
    "ccxt.async_support.base.exchange",
    "ccxt.pro",
    "asyncio",
    "urllib3",
    "websockets",
    "aiohttp",
    "aiohttp.client",
    "aiohttp.access",
)


class _StdlibInterceptHandler(logging.Handler):
    """Send stdlib logs through Loguru with the same format and truncation."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        message = record.getMessage()
        if len(message) > _MAX_INTERCEPTED_MESSAGE_LEN:
            message = (
                message[:_MAX_INTERCEPTED_MESSAGE_LEN]
                + f"...[truncated {len(message) - _MAX_INTERCEPTED_MESSAGE_LEN} chars]"
            )

        depth = 2
        frame: FrameType | None = logging.currentframe()
        if frame is not None:
            frame = frame.f_back
        log_init = getattr(logging, "__file__", "") or ""
        while frame is not None and log_init and frame.f_code.co_filename == log_init:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            "[{}] {}",
            record.name,
            message,
        )


def _install_stdlib_intercept() -> None:
    global _stdlib_intercept_installed
    if _stdlib_intercept_installed:
        return
    _stdlib_intercept_installed = True

    logging.root.handlers = [_StdlibInterceptHandler()]
    logging.root.setLevel(logging.INFO)

    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "starlette",
    ):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    for name in _NOISY_STDLIB_LOGGERS_WARNING:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.WARNING)
        lg.propagate = True


def init_logger(log_dir: str = "logs", console_level: str = "INFO") -> None:
    """Configure global loguru sinks: colored stderr, base file, errors file, channel router."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    loguru_logger.remove()

    day_stamp = datetime.now().strftime("%Y-%m-%d")
    pid = os.getpid()
    global _ch_file_root
    _ch_file_root = log_path

    loguru_logger.add(
        sys.stderr,
        format=CONSOLE_FORMAT,
        level=console_level,
        enqueue=True,
    )

    loguru_logger.add(
        log_path / f"base_{day_stamp}_pid{pid}.log",
        format=FILE_FORMAT,
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        enqueue=True,
        catch=True,
    )

    loguru_logger.add(
        _ch_file_sink,
        format=FILE_FORMAT,
        filter=_record_routed_channel_file,
        level="DEBUG",
        enqueue=True,
        catch=True,
    )

    loguru_logger.add(
        log_path / f"errors_{day_stamp}_pid{pid}.log",
        format=FILE_FORMAT,
        level="ERROR",
        rotation="00:00",
        retention="30 days",
        enqueue=True,
        catch=True,
    )

    _install_stdlib_intercept()


def get_logger(name: str | None = None) -> ArbitrageLogger:
    """Return the project logger (``name`` kept for backward compatibility only)."""
    if name:
        return cast(ArbitrageLogger, loguru_logger.bind(channel=name))
    return cast(ArbitrageLogger, loguru_logger)


def _logger_for_bracket_key(key: str) -> ArbitrageLogger:
    if "/" not in key:
        return cast(ArbitrageLogger, loguru_logger.bind(channel=key))
    head, tail = key.split("/", 1)
    sub = head.strip()
    rel = tail.strip().lstrip("/")
    if not sub or not rel or ".." in key:
        raise ValueError(key)
    if any(x in sub for x in "/\\"):
        raise ValueError(key)
    pn = Path(rel.replace("\\", "/"))
    if len(pn.parts) != 1:
        raise ValueError(key)
    fname = pn.name
    if not fname.endswith(".log") or len(fname) <= 4:
        raise ValueError(key)
    stem = fname[:-4]
    day = datetime.now().strftime("%Y-%m-%d")
    dated_fname = f"{stem}_{day}.log"
    dest = _ch_file_root / sub / dated_fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.touch(exist_ok=True)
    return cast(
        ArbitrageLogger,
        loguru_logger.bind(channel=key, ch_log_subdir=sub, ch_log_filename=dated_fname),
    )


class _BracketLogger:
    """Public proxy: ``logger.info(...)`` and ``logger["dir/file.log"].info(...)``."""

    __slots__ = ()

    def __getitem__(self, key: str) -> ArbitrageLogger:
        return _logger_for_bracket_key(key)

    def debug(self, message: str, *args: object, **kwargs: object) -> None:
        loguru_logger.opt(depth=1).debug(message, *args, **kwargs)

    def info(self, message: str, *args: object, **kwargs: object) -> None:
        loguru_logger.opt(depth=1).info(message, *args, **kwargs)

    def warning(self, message: str, *args: object, **kwargs: object) -> None:
        loguru_logger.opt(depth=1).warning(message, *args, **kwargs)

    def error(self, message: str, *args: object, **kwargs: object) -> None:
        loguru_logger.opt(depth=1).error(message, *args, **kwargs)

    def exception(self, message: str, *args: object, **kwargs: object) -> None:
        loguru_logger.opt(depth=1, exception=True).error(message, *args, **kwargs)


logger = _BracketLogger()

init_logger()
