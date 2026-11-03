import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from time import monotonic

logger = logging.getLogger(__name__)


class State(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class Permit:
    generation: int
    probe: bool


class CircuitBreaker:
    def __init__(self, threshold=5, cooldown=15.0, window=60.0):
        if threshold < 1 or not all(
            isfinite(value) and value > 0 for value in (cooldown, window)
        ):
            raise ValueError("Circuit breaker threshold and durations must be positive")
        self.threshold = threshold
        self.cooldown = cooldown
        self.window = window
        self.state = State.CLOSED
        self._generation = 0
        self._failures = deque()
        self._reopen_at = (
            0.0  # a time when new attempt becomes possible with probe=True
        )

    def acquire(self):
        if self.state is State.CLOSED:
            return Permit(self._generation, probe=False)
        if self.state is State.OPEN and monotonic() >= self._reopen_at:
            self._transition(State.HALF_OPEN)
            return Permit(self._generation, probe=True)
        return None

    def complete(self, permit, *, failed):
        if permit.generation != self._generation:
            return
        if permit.probe:
            if failed:
                self._open(monotonic())
            else:
                self._transition(State.CLOSED)
            return
        if not failed:
            self._failures.clear()
            return
        now = monotonic()
        while self._failures and self._failures[0] <= now - self.window:
            self._failures.popleft()
        self._failures.append(now)
        if len(self._failures) >= self.threshold:
            self._open(now)

    def _open(self, now):
        self._reopen_at = now + self.cooldown
        self._transition(State.OPEN)

    def _transition(self, state):
        logger.info("flight_breaker %s -> %s", self.state.value, state.value)
        self.state = state
        self._generation += 1
        self._failures.clear()
