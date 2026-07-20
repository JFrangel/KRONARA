from kronara.autonomous_loop import AutonomousProductionLoop
from kronara.contracts import AutonomyMode, AutonomyPolicy
from kronara.programs import ProgramDescriptor, ProgramRegistry
from kronara.schedule import AutonomousRunAuthorizer, Scheduler, derive_schedule_rules
from kronara.store import KronaraStore

# 2026-07-24 18:00:00 UTC is a Friday -- exactly viernes-paranormal's weekly slot.
FRIDAY_RELEASE = 1_784_930_400


def _registry(**overrides) -> ProgramRegistry:
    defaults = dict(
        program_id="viernes-paranormal", name="Viernes Paranormal", weekday="viernes",
        genre="paranormal", description="terror y fenómenos sobrenaturales",
        visual_style_id="viernes-paranormal", target_duration_seconds=480, platforms=(),
    )
    defaults.update(overrides)
    return ProgramRegistry((ProgramDescriptor(**defaults),))


def _loop(registry, *, run_program, is_paused=lambda: False, policy=None, store=None):
    rules = derive_schedule_rules(registry._descriptors.values())
    policy = policy or AutonomyPolicy(mode=AutonomyMode.FULL_AUTO)
    return AutonomousProductionLoop(
        scheduler=Scheduler(rules),
        authorizer=AutonomousRunAuthorizer(policy),
        registry=registry,
        store=store,
        run_program=run_program,
        is_paused=is_paused,
    )


def test_tick_runs_a_due_program_and_records_it_fired(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    calls = []
    loop = _loop(_registry(), run_program=lambda pid, params: calls.append((pid, params)), store=store)

    report = loop.tick(FRIDAY_RELEASE)

    assert report.ran == ("viernes-paranormal",)
    assert len(calls) == 1
    assert store.load_schedule_last_fired() == {"weekly_viernes-paranormal": FRIDAY_RELEASE}
    store.close()


def test_tick_passes_real_subreddits_and_program_id_into_run_program(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    calls = []
    loop = _loop(_registry(), run_program=lambda pid, params: calls.append((pid, params)), store=store)

    loop.tick(FRIDAY_RELEASE)

    program_id, params = calls[0]
    assert program_id == "viernes-paranormal"
    assert params["program_id"] == "viernes-paranormal"
    assert params["target_duration_seconds"] == 480
    assert "nosleep" in params["subreddits"]  # real knowledge/reddit-sources/nodo-viernes-paranormal.md
    store.close()


def test_tick_skips_everything_when_globally_paused(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    calls = []
    loop = _loop(
        _registry(), run_program=lambda pid, params: calls.append(pid),
        is_paused=lambda: True, store=store,
    )

    report = loop.tick(FRIDAY_RELEASE)

    assert report.outcomes == ()
    assert calls == []
    assert store.load_schedule_last_fired() == {}
    store.close()


def test_tick_does_not_mark_fired_on_failure_so_the_next_tick_retries(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()

    def _boom(pid, params):
        raise RuntimeError("reddit fetch failed")

    loop = _loop(_registry(), run_program=_boom, store=store)

    first = loop.tick(FRIDAY_RELEASE)
    assert first.outcomes[0].status == "failed"
    assert store.load_schedule_last_fired() == {}

    # Same `now`: still due, because nothing was recorded as fired.
    second = loop.tick(FRIDAY_RELEASE)
    assert second.outcomes[0].status == "failed"
    store.close()


def test_tick_marks_fired_when_authorization_blocks_a_prohibited_program(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    calls = []
    policy = AutonomyPolicy(mode=AutonomyMode.FULL_AUTO, prohibited_topics=("fenómenos",))
    loop = _loop(_registry(), run_program=lambda pid, params: calls.append(pid), policy=policy, store=store)

    report = loop.tick(FRIDAY_RELEASE)

    assert report.outcomes[0].status == "blocked"
    assert report.outcomes[0].detail == "platform_policy_violation"
    assert calls == []
    # Blocked runs ARE marked fired -- a durable policy block shouldn't be
    # re-evaluated (and re-logged) on every single tick forever.
    assert store.load_schedule_last_fired() == {"weekly_viernes-paranormal": FRIDAY_RELEASE}
    store.close()


def test_last_fired_survives_a_process_restart(tmp_path):
    db_path = tmp_path / "runtime.db"
    store_a = KronaraStore(db_path)
    store_a.initialize()
    _loop(_registry(), run_program=lambda pid, params: None, store=store_a).tick(FRIDAY_RELEASE)
    store_a.close()

    # A brand new store/loop over the same on-disk db -- simulates the app
    # restarting -- must not re-fire the same weekly slot.
    store_b = KronaraStore(db_path)
    store_b.initialize()
    calls = []
    report = _loop(
        _registry(), run_program=lambda pid, params: calls.append(pid), store=store_b
    ).tick(FRIDAY_RELEASE)

    assert report.ran == ()
    assert calls == []
    store_b.close()


def test_tick_with_nothing_due_runs_nothing(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    # Simulate it already fired last week -- with no history at all, a
    # WEEKLY rule's "next occurrence since epoch 0" is always in the past
    # relative to any real `now`, so it would look due regardless of what
    # weekday `now` actually falls on.
    store.record_schedule_fired("weekly_viernes-paranormal", FRIDAY_RELEASE - 7 * 86_400)
    loop = _loop(_registry(), run_program=lambda pid, params: (_ for _ in ()).throw(AssertionError), store=store)

    report = loop.tick(FRIDAY_RELEASE - 86_400)  # Thursday: one day before the NEXT weekly slot

    assert report.outcomes == ()
    store.close()
