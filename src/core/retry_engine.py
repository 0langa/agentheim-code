"""Bounded retry engine with exponential backoff and error classification.

Integrates with the ledger (event emission) and step budget (respects limits).
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import TypeVar

from core.error_classification import (
    ErrorCategory,
    backoff_for,
    classify_error,
    max_retries_for,
    should_retry,
)
from core.events import EventType
from core.ledger import RunLedger

T = TypeVar("T")


class RetryExhaustedError(RuntimeError):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_exception: BaseException) -> None:
        super().__init__(message)
        self.last_exception = last_exception


class RetryEngine:
    """Execute callables with bounded retry and backoff.

    Each retry attempt is logged to the ledger as a structured event.
    Budget checks are performed before every attempt.
    """

    def __init__(
        self,
        ledger: RunLedger | None = None,
        default_max_retries: int = 3,
        default_backoff: float = 2.0,
    ) -> None:
        self.ledger = ledger
        self.default_max_retries = default_max_retries
        self.default_backoff = default_backoff

    def execute(
        self,
        fn: Callable[[], T],
        *,
        max_retries: int | None = None,
        backoff: float | None = None,
        error_category: ErrorCategory | None = None,
        step_id: str | None = None,
        run_id: str | None = None,
    ) -> T:
        """Execute *fn*, retrying on failure according to its error category.

        Args:
            fn: Callable taking no arguments and returning T.
            max_retries: Override default max retries. If None, inferred from category.
            backoff: Override default initial backoff (seconds).
            error_category: If known upfront, skip classification.
            step_id: For event attribution.
            run_id: For event attribution.

        Returns:
            The result of *fn* on success.

        Raises:
            RetryExhaustedError: If all retries are exhausted.
            BaseException: If the error category indicates no retry (CONFIGURATION, PERMISSION, FATAL).
        """
        attempt = 0
        while True:
            try:
                result = fn()
                if attempt > 0 and self.ledger is not None:
                    self.ledger.emit_event(
                        EventType.RETRY_ATTEMPTED,
                        step_id=step_id,
                        payload={
                            "attempt": attempt,
                            "outcome": "success",
                            "max_retries": max_retries,
                        },
                    )
                return result
            except BaseException as exc:
                category = error_category or classify_error(exc)

                retries = (
                    max_retries
                    if max_retries is not None
                    else max_retries_for(category, self.default_max_retries)
                )
                delay = (
                    backoff if backoff is not None else backoff_for(category, self.default_backoff)
                )

                if not should_retry(category) or attempt >= retries:
                    # Log final failure and re-raise wrapped or raw
                    if self.ledger is not None:
                        self.ledger.emit_event(
                            EventType.RETRY_EXHAUSTED,
                            step_id=step_id,
                            payload={
                                "attempt": attempt,
                                "category": category.value,
                                "error": str(exc),
                                "error_type": type(exc).__name__,
                            },
                        )
                    if should_retry(category):
                        raise RetryExhaustedError(
                            f"Failed after {attempt + 1} attempts ({category.value}): {exc}",
                            exc,
                        ) from exc
                    raise

                # Log retry attempt
                if self.ledger is not None:
                    self.ledger.emit_event(
                        EventType.RETRY_ATTEMPTED,
                        step_id=step_id,
                        payload={
                            "attempt": attempt,
                            "outcome": "retry",
                            "category": category.value,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "next_delay": delay * (2**attempt),
                        },
                    )

                time.sleep(delay * (2**attempt))
                attempt += 1

    def execute_with_budget(
        self,
        fn: Callable[[], T],
        *,
        budget_checker: Callable[[], bool],
        max_retries: int | None = None,
        backoff: float | None = None,
        error_category: ErrorCategory | None = None,
        step_id: str | None = None,
        run_id: str | None = None,
    ) -> T:
        """Execute *fn* with retry, but check budget before every attempt.

        Args:
            budget_checker: Callable returning True if budget remains, False to halt.
            Other args same as `execute`.
        """
        wrapped = self._with_budget(fn, budget_checker, step_id)
        return self.execute(
            wrapped,
            max_retries=max_retries,
            backoff=backoff,
            error_category=error_category,
            step_id=step_id,
            run_id=run_id,
        )

    @staticmethod
    def _with_budget(
        fn: Callable[[], T],
        budget_checker: Callable[[], bool],
        step_id: str | None = None,
    ) -> Callable[[], T]:
        """Wrap fn so it checks budget before each call."""

        @functools.wraps(fn)
        def wrapper() -> T:
            if not budget_checker():
                raise RuntimeError(f"Budget exceeded before step {step_id}")
            return fn()

        return wrapper
