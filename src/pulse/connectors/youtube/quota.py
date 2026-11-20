"""YouTube Data API quota accounting — never assume unlimited access."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from pulse.connectors.types import ConnectorError, ConnectorErrorKind

# Official-ish unit costs for common Data API v3 methods (operator-configurable overrides OK).
# These are documented Google quota costs, not invented prices.
DEFAULT_METHOD_COSTS: dict[str, int] = {
    "search.list": 100,
    "videos.list": 1,
    "commentThreads.list": 1,
    "channels.list": 1,
}


@dataclass
class QuotaLedger:
    """Tracks units consumed against a daily budget for one connector instance."""

    daily_budget: int
    warning_threshold: float = 0.8
    method_costs: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_METHOD_COSTS))
    _day: date = field(default_factory=lambda: datetime.now(UTC).date())
    units_used: int = 0

    def _roll_day(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day = today
            self.units_used = 0

    def cost_for(self, method: str) -> int:
        return self.method_costs.get(method, 1)

    def remaining(self) -> int:
        self._roll_day()
        return max(0, self.daily_budget - self.units_used)

    def would_exceed(self, method: str) -> bool:
        return self.cost_for(method) > self.remaining()

    def at_warning(self) -> bool:
        self._roll_day()
        return self.units_used >= int(self.daily_budget * self.warning_threshold)

    def charge(self, method: str) -> int:
        """Charge quota for a successful API call. Raises if budget would be exceeded."""
        self._roll_day()
        cost = self.cost_for(method)
        if cost > self.remaining():
            raise ConnectorError(
                f"YouTube quota exhausted for method {method}: "
                f"need {cost}, remaining {self.remaining()} of {self.daily_budget} daily units. "
                "Never assume unlimited Data API access.",
                kind=ConnectorErrorKind.RATE_LIMIT,
                retryable=False,
                details={
                    "method": method,
                    "cost": cost,
                    "units_used": self.units_used,
                    "daily_budget": self.daily_budget,
                },
            )
        self.units_used += cost
        return cost

    def snapshot(self) -> dict[str, int | float | str]:
        self._roll_day()
        return {
            "day": self._day.isoformat(),
            "units_used": self.units_used,
            "daily_budget": self.daily_budget,
            "remaining": self.remaining(),
            "warning_threshold": self.warning_threshold,
        }
