from __future__ import annotations

import json
import logging
from typing import Any

try:
    import structlog as _structlog  # type: ignore
except Exception:  # pragma: no cover
    _structlog = None


class _FallbackBoundLogger:
    def __init__(self, logger: logging.Logger, bound: dict[str, Any] | None = None):
        self._logger = logger
        self._bound = dict(bound or {})

    def bind(self, **kwargs: Any):
        return _FallbackBoundLogger(self._logger, {**self._bound, **kwargs})

    def unbind(self, *keys: str):
        current = dict(self._bound)
        for key in keys:
            current.pop(key, None)
        return _FallbackBoundLogger(self._logger, current)

    def _message(self, message: str, event: dict[str, Any]) -> str:
        payload = {**self._bound, **event}
        if not payload:
            return message
        return f"{message} | {json.dumps(payload, sort_keys=True, default=str)}"

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(self._message(message, kwargs), *args)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(self._message(message, kwargs), *args)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(self._message(message, kwargs), *args)

    warn = warning

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(self._message(message, kwargs), *args)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(self._message(message, kwargs), *args)


class _FallbackStructlog:
    def get_logger(self, name: str | None = None):
        return _FallbackBoundLogger(logging.getLogger(name or "viki"))

    class stdlib:  # pragma: no cover - compatibility shim
        filter_by_level = staticmethod(lambda logger, method_name, event_dict: event_dict)
        add_logger_name = staticmethod(lambda logger, method_name, event_dict: event_dict)
        add_log_level = staticmethod(lambda logger, method_name, event_dict: event_dict)
        PositionalArgumentsFormatter = staticmethod(lambda *args, **kwargs: (lambda logger, method_name, event_dict: event_dict))
        LoggerFactory = staticmethod(lambda *args, **kwargs: None)
        BoundLogger = _FallbackBoundLogger

    class processors:  # pragma: no cover
        TimeStamper = staticmethod(lambda *args, **kwargs: (lambda logger, method_name, event_dict: event_dict))
        StackInfoRenderer = staticmethod(lambda *args, **kwargs: (lambda logger, method_name, event_dict: event_dict))
        format_exc_info = staticmethod(lambda logger, method_name, event_dict: event_dict)
        JSONRenderer = staticmethod(lambda *args, **kwargs: (lambda logger, method_name, event_dict: event_dict))

    @staticmethod
    def configure(*args, **kwargs):
        return None


structlog = _structlog or _FallbackStructlog()
