import pytest

from kronara.contracts import AutonomyMode, AutonomyPolicy
from kronara.schedule import (
    AutonomousRunAuthorizer,
    Cadence,
    DueRun,
    Scheduler,
    ScheduleRule,
    weekday_of,
)

# 2026-07-20 00:00:00 UTC is a Monday.
MONDAY_MIDNIGHT = 1_784_506_800 - (1_784_506_800 % 86_400)


def test_weekday_of_monday():
    # 1970-01-05 was a Monday.
    assert weekday_of(4 * 86_400) == 0


def test_interval_rule_becomes_due_after_interval():
    rule = ScheduleRule("r1", "confesiones", Cadence.INTERVAL, interval_seconds=3600)
    scheduler = Scheduler((rule,))
    assert scheduler.due(now=3599, last_fired={"r1": 0}) == ()
    due = scheduler.due(now=3600, last_fired={"r1": 0})
    assert len(due) == 1 and due[0].program_id == "confesiones"


def test_daily_rule_fires_once_per_day_at_time():
    # Fire at 20:00 (72000s into the day).
    rule = ScheduleRule("r2", "viernes-paranormal", Cadence.DAILY, at_second_of_day=72_000)
    scheduler = Scheduler((rule,))
    day = 20_000 * 86_400
    just_before = day + 71_999
    at_time = day + 72_000
    assert scheduler.due(now=just_before, last_fired={"r2": day}) == ()
    assert len(scheduler.due(now=at_time, last_fired={"r2": day})) == 1


def test_weekly_rule_only_fires_on_its_weekday():
    friday = 4  # Mon=0..Fri=4
    rule = ScheduleRule(
        "r3", "viernes-paranormal", Cadence.WEEKLY, at_second_of_day=72_000, weekday=friday
    )
    scheduler = Scheduler((rule,))
    fire = scheduler.next_fire(rule, after=0)
    assert fire is not None
    assert weekday_of(fire) == friday


def test_disabled_rule_never_due():
    rule = ScheduleRule("r4", "p", Cadence.INTERVAL, interval_seconds=1, enabled=False)
    assert Scheduler((rule,)).due(now=10_000) == ()


def test_multiple_programs_sorted_by_time():
    rules = (
        ScheduleRule("a", "prog-a", Cadence.INTERVAL, interval_seconds=100),
        ScheduleRule("b", "prog-b", Cadence.INTERVAL, interval_seconds=50),
    )
    due = Scheduler(rules).due(now=1000, last_fired={"a": 0, "b": 0})
    assert [run.program_id for run in due] == ["prog-b", "prog-a"]


def test_autonomy_authorizer_blocks_when_paused():
    policy = AutonomyPolicy(mode=AutonomyMode.FULL_AUTO, paused=True)
    authorizer = AutonomousRunAuthorizer(policy)
    decision = authorizer.authorize(DueRun("r", "p", 0, {}))
    assert decision.allowed is False
    assert decision.reason == "globally_paused"


def test_autonomy_authorizer_blocks_prohibited_topic():
    policy = AutonomyPolicy(mode=AutonomyMode.FULL_AUTO, prohibited_topics=("gore",))
    authorizer = AutonomousRunAuthorizer(policy)
    decision = authorizer.authorize(DueRun("r", "p", 0, {}), topic="una historia de GORE explícito")
    assert decision.allowed is False
    assert decision.reason == "platform_policy_violation"


def test_autonomy_authorizer_allows_clean_full_auto_run():
    policy = AutonomyPolicy(mode=AutonomyMode.FULL_AUTO)
    authorizer = AutonomousRunAuthorizer(policy)
    decision = authorizer.authorize(DueRun("r", "p", 0, {}), topic="conflicto familiar")
    assert decision.allowed is True
    assert decision.requires_human is False


def test_invalid_rule_rejected():
    with pytest.raises(ValueError):
        ScheduleRule("r", "p", Cadence.WEEKLY, at_second_of_day=100)  # missing weekday
