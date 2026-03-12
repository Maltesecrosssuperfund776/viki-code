import asyncio
import logging
import signal
import time
from typing import Any, Callable

from .._log import structlog

try:
    from tenacity import (
        before_sleep_log,
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )
except Exception:  # pragma: no cover
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None

    def retry_if_exception_type(*args, **kwargs):
        return None

    def before_sleep_log(*args, **kwargs):
        return None

logger = structlog.get_logger()


class CircuitBreaker:
    """Prevent cascade failures"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self.state = "CLOSED"

    def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == "OPEN":
            if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"Circuit breaker opened for {func.__name__}")
            raise


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, rate: int = 10, per: int = 60):
        self.rate = rate
        self.per = per
        self.tokens = rate
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per))
            self.updated_at = now
            if self.tokens < 1:
                sleep_time = (1 - self.tokens) * (self.per / self.rate)
                logger.debug(f"Rate limit hit, sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class GracefulShutdown:
    """Handle SIGTERM/SIGINT properly"""

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.cleanup_handlers = []
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                asyncio.get_running_loop().add_signal_handler(sig, self._signal_handler)
        except (NotImplementedError, RuntimeError, ValueError):
            try:
                signal.signal(signal.SIGINT, self._sync_signal_handler)
                signal.signal(signal.SIGTERM, self._sync_signal_handler)
            except Exception:
                pass

    def _signal_handler(self):
        logger.info("Shutdown signal received")
        self.shutdown_event.set()

    def _sync_signal_handler(self, signum, frame):
        logger.info(f"Shutdown signal {signum} received")
        try:
            self.shutdown_event.set()
        except Exception:
            pass

    async def wait_for_shutdown(self):
        await self.shutdown_event.wait()
        logger.info("Executing cleanup handlers...")
        for handler in self.cleanup_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                logger.error(f"Cleanup handler failed: {e}")

    def add_cleanup_handler(self, handler: Callable):
        self.cleanup_handlers.append(handler)

    def is_shutting_down(self) -> bool:
        return self.shutdown_event.is_set()


# Retry decorator for API calls
def resilient_api_call(max_attempts=3):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
