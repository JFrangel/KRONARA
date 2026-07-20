"""The autonomous production loop: turns Scheduler.due() from a pure query
into Kronara actually running itself.

R6 built Scheduler/ScheduleRule/AutonomousRunAuthorizer as pure, tested
logic, but nothing ever instantiated them with real programs or called them
on a real clock -- "hit run and it starts everything on its own" was still
manual. This module is the missing wiring: on each tick(now), it asks the
Scheduler which programs are due for their next weekly episode, authorizes
each through AutonomyGuard, and invokes a real production run for it --
using derive_schedule_rules() (schedule.py) for the grid and
subreddits_for_program() (reddit_source_map.py) so each program investigates
the real sources F0 documented for it, not a hardcoded list here.

A single program failing (network blip, a bad model response, whatever)
must never take down the weekly grid for the other six -- every exception
from run_program is caught, recorded in the tick report, and the rule stays
due so the *next* tick retries it (last_fired is only recorded on success or
on a definite authorization block). The caller controls the tick interval;
see sidecar.py's background loop for the real cadence, chosen to keep a
persistent failure's retry rate bounded without making a transient one wait
a whole week.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from kronara.programs import ProgramRegistry
from kronara.reddit_source_map import subreddits_for_program
from kronara.schedule import AutonomousRunAuthorizer, DueRun, Scheduler
from kronara.store import KronaraStore

RunProgram = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class TickOutcome:
    program_id: str
    rule_id: str
    status: str  # "completed" | "blocked" | "failed"
    detail: str = ""


@dataclass(frozen=True)
class TickReport:
    checked_at: int
    outcomes: tuple[TickOutcome, ...]

    @property
    def ran(self) -> tuple[str, ...]:
        return tuple(outcome.program_id for outcome in self.outcomes if outcome.status == "completed")


class AutonomousProductionLoop:
    def __init__(
        self,
        *,
        scheduler: Scheduler,
        authorizer: AutonomousRunAuthorizer,
        registry: ProgramRegistry,
        store: KronaraStore,
        run_program: RunProgram,
        is_paused: Callable[[], bool] = lambda: False,
    ):
        self._scheduler = scheduler
        self._authorizer = authorizer
        self._registry = registry
        self._store = store
        self._run_program = run_program
        self._is_paused = is_paused

    def tick(self, now: int) -> TickReport:
        """Global pause short-circuits before even consulting the schedule --
        a paused tick must not consume anyone's due window, so unpausing
        later still finds those programs due rather than having silently
        skipped their slot forever."""
        if self._is_paused():
            return TickReport(checked_at=now, outcomes=())
        last_fired = self._store.load_schedule_last_fired()
        due = self._scheduler.due(now, last_fired)
        outcomes = tuple(self._fire(run, now) for run in due)
        return TickReport(checked_at=now, outcomes=outcomes)

    def _fire(self, run: DueRun, now: int) -> TickOutcome:
        program = self._registry.get(run.program_id)
        authorization = self._authorizer.authorize(run, topic=program.description)
        if not authorization.allowed:
            # A block here is a durable policy fact (prohibited topic,
            # critical risk code), not a transient failure -- retrying every
            # tick would just waste cycles, so this rule waits for its next
            # natural weekly slot like a successful run would.
            self._store.record_schedule_fired(run.rule_id, now)
            return TickOutcome(
                program_id=run.program_id, rule_id=run.rule_id,
                status="blocked", detail=authorization.reason or "not authorized",
            )
        params = {
            "subreddits": list(subreddits_for_program(run.program_id)),
            "target_duration_seconds": program.target_duration_seconds,
            "story_id": f"owned_auto_{run.program_id}_{now}",
            **run.params,
            "program_id": run.program_id,
        }
        try:
            self._run_program(run.program_id, params)
        except Exception as error:  # noqa: BLE001 -- one broken program must not break the grid
            # Deliberately NOT marked fired: a failure (often transient --
            # network, rate limit, a model hiccup) should be retried at the
            # next tick rather than silently skipping this program's whole
            # week. The tick interval itself is what keeps retries bounded.
            return TickOutcome(
                program_id=run.program_id, rule_id=run.rule_id,
                status="failed", detail=type(error).__name__,
            )
        self._store.record_schedule_fired(run.rule_id, now)
        return TickOutcome(program_id=run.program_id, rule_id=run.rule_id, status="completed")
