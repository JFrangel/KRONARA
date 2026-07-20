"""Editorial scheduler: the agents run themselves.

Kronara used to require a human to start every run. This module computes which
programmed runs are *due* so the agent can work unattended in the background —
one story per program, on a weekly grid, like a TV network. Time is handled as
epoch seconds; the caller supplies ``now`` (the Rust authority owns the wall
clock and the timer that ticks this), keeping the logic pure and testable.

Authorization for each due run still passes through :class:`AutonomyGuard`
(``policy``), so a paused system, a prohibited topic, or a critical risk stops
the loop instead of publishing blindly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from typing import TYPE_CHECKING, Iterable

from kronara.contracts import (
    AutonomyPolicy,
    RiskDecision,
    RiskLevel,
)
from kronara.policy import AutonomyGuard

if TYPE_CHECKING:
    from kronara.programs import ProgramDescriptor

SECONDS_PER_DAY = 86_400
DEFAULT_RELEASE_SECOND_OF_DAY = 64_800  # 18:00 UTC -- evening release for a nightly program

_WEEKDAY_INDEX = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}


class Cadence(StrEnum):
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"


def weekday_of(epoch: int) -> int:
    """Return day of week with Monday=0 .. Sunday=6 (UTC)."""
    return (epoch // SECONDS_PER_DAY + 3) % 7


@dataclass(frozen=True)
class ScheduleRule:
    rule_id: str
    program_id: str
    cadence: Cadence
    enabled: bool = True
    interval_seconds: int | None = None
    at_second_of_day: int | None = None
    weekday: int | None = None
    params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id or not self.program_id:
            raise ValueError("a schedule rule needs a rule id and a program")
        if self.cadence is Cadence.INTERVAL and not self.interval_seconds:
            raise ValueError("interval cadence requires interval_seconds")
        if self.cadence in {Cadence.DAILY, Cadence.WEEKLY} and self.at_second_of_day is None:
            raise ValueError("daily/weekly cadence requires at_second_of_day")
        if self.cadence is Cadence.WEEKLY and self.weekday is None:
            raise ValueError("weekly cadence requires a weekday (0=Mon..6=Sun)")
        if self.at_second_of_day is not None and not 0 <= self.at_second_of_day < SECONDS_PER_DAY:
            raise ValueError("at_second_of_day out of range")


@dataclass(frozen=True)
class DueRun:
    rule_id: str
    program_id: str
    scheduled_for: int
    params: dict


class Scheduler:
    """Pure scheduler: given rules + last-fired times + now, returns due runs."""

    def __init__(self, rules: tuple[ScheduleRule, ...]):
        self.rules = tuple(rules)

    def next_fire(self, rule: ScheduleRule, after: int) -> int | None:
        if not rule.enabled:
            return None
        if rule.cadence is Cadence.INTERVAL:
            assert rule.interval_seconds is not None
            return after + rule.interval_seconds
        assert rule.at_second_of_day is not None
        day = after // SECONDS_PER_DAY
        candidate = day * SECONDS_PER_DAY + rule.at_second_of_day
        if candidate <= after:
            candidate += SECONDS_PER_DAY
        if rule.cadence is Cadence.WEEKLY:
            for _ in range(8):
                if weekday_of(candidate) == rule.weekday:
                    return candidate
                candidate += SECONDS_PER_DAY
            return None
        return candidate

    def due(self, now: int, last_fired: dict[str, int] | None = None) -> tuple[DueRun, ...]:
        last_fired = last_fired or {}
        runs: list[DueRun] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            previous = last_fired.get(rule.rule_id, 0)
            fire_at = self.next_fire(rule, previous)
            if fire_at is not None and fire_at <= now:
                runs.append(
                    DueRun(
                        rule_id=rule.rule_id,
                        program_id=rule.program_id,
                        scheduled_for=fire_at,
                        params=dict(rule.params),
                    )
                )
        runs.sort(key=lambda run: (run.scheduled_for, run.rule_id))
        return tuple(runs)


@dataclass(frozen=True)
class RunAuthorization:
    allowed: bool
    requires_human: bool
    reason: str | None


class AutonomousRunAuthorizer:
    """Gates a scheduled run through the (now instantiated) AutonomyGuard.

    This wires the previously-dormant AutonomyPolicy into the live loop: a paused
    system, a prohibited-topic hit, or a non-overridable risk code stops the run.
    """

    def __init__(self, policy: AutonomyPolicy):
        self.policy = policy
        self.guard = AutonomyGuard(policy)

    def authorize(self, due: DueRun, *, topic: str = "", risk_codes: tuple[str, ...] = ()) -> RunAuthorization:
        codes = list(risk_codes)
        lowered = topic.casefold()
        if any(banned.casefold() in lowered for banned in self.policy.prohibited_topics if banned):
            codes.append("platform_policy_violation")
        level = RiskLevel.CRITICAL if "critical_reputational_risk" in codes else RiskLevel.LOW
        decision = self.guard.authorize("run", RiskDecision(level=level, codes=tuple(codes)))
        return RunAuthorization(
            allowed=decision.allowed,
            requires_human=decision.requires_human,
            reason=decision.reason,
        )


def derive_schedule_rules(
    programs: Iterable["ProgramDescriptor"],
    *,
    at_second_of_day: int = DEFAULT_RELEASE_SECOND_OF_DAY,
) -> tuple[ScheduleRule, ...]:
    """One weekly ScheduleRule per program, straight from programs.v1.json --
    B1's missing link between "the grid is documented" and "the grid runs
    itself." rule_id is deterministic (`weekly_<program_id>`) so re-deriving
    from an unchanged registry always yields the same id and last_fired
    (persisted by rule_id) stays valid across restarts. A program whose
    weekday spelling isn't recognized is skipped rather than raising -- one
    bad entry in the registry shouldn't take down the whole autonomous grid.
    """
    rules = []
    for program in programs:
        weekday = _WEEKDAY_INDEX.get(program.weekday)
        if weekday is None:
            continue
        rules.append(
            ScheduleRule(
                rule_id=f"weekly_{program.program_id}",
                program_id=program.program_id,
                cadence=Cadence.WEEKLY,
                weekday=weekday,
                at_second_of_day=at_second_of_day,
            )
        )
    return tuple(rules)
