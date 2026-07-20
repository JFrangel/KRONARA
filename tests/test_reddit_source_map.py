from pathlib import Path

from kronara.reddit_source_map import (
    DEFAULT_SENSITIVITY,
    load_source_map,
    sensitivity_for,
    subreddits_for_program,
)

FIXTURE = """# Nodo de prueba

| Subreddit | Descripción | sensitivity |
|---|---|---|
| StoryTellingSub | Historias para entretenimiento. | entertainment |
| SupportGroupSub | Comunidad de apoyo real. | real_experience_serious |
| AmItheAsshole (flair Serious) | Casos con "comillas" y — guion largo. | real_experience_serious |
| ParentA / ParentB | Dos subs en una fila. | real_experience_serious |
"""


def test_parses_table_rows_including_parens_and_slashes(tmp_path):
    directory = tmp_path / "reddit-sources"
    directory.mkdir()
    (directory / "nodo-test.md").write_text(FIXTURE, encoding="utf-8")

    source_map = load_source_map(directory)

    assert sensitivity_for("StoryTellingSub", source_map) == "entertainment"
    assert sensitivity_for("SupportGroupSub", source_map) == "real_experience_serious"
    assert sensitivity_for("AmItheAsshole", source_map) == "real_experience_serious"
    assert sensitivity_for("ParentA", source_map) == "real_experience_serious"
    assert sensitivity_for("ParentB", source_map) == "real_experience_serious"


def test_unknown_subreddit_defaults_to_entertainment(tmp_path):
    directory = tmp_path / "reddit-sources"
    directory.mkdir()
    (directory / "nodo-test.md").write_text(FIXTURE, encoding="utf-8")
    source_map = load_source_map(directory)

    assert sensitivity_for("NeverListed", source_map) == DEFAULT_SENSITIVITY


def test_missing_directory_returns_empty_map(tmp_path):
    assert load_source_map(tmp_path / "does-not-exist") == {}


def test_separator_row_and_header_are_not_treated_as_data():
    directory = Path(__file__).resolve().parents[1] / "knowledge" / "reddit-sources"
    source_map = load_source_map(directory)
    # The header row's literal cell text ("Subreddit") must not become an entry.
    assert "subreddit" not in source_map
    assert "descripción" not in source_map


def test_real_nodo_files_parse_and_classify_known_examples():
    directory = Path(__file__).resolve().parents[1] / "knowledge" / "reddit-sources"
    source_map = load_source_map(directory)

    assert sensitivity_for("ProRevenge", source_map) == "entertainment"
    assert sensitivity_for("nosleep", source_map) == "entertainment"
    assert sensitivity_for("CPTSD", source_map) == "real_experience_serious"
    assert sensitivity_for("domesticviolence", source_map) == "real_experience_serious"
    assert sensitivity_for("survivorsofabuse", source_map) == "real_experience_serious"
    assert len(source_map) >= 40


def test_subreddits_for_program_reads_only_that_programs_node_file(tmp_path):
    directory = tmp_path / "reddit-sources"
    directory.mkdir()
    (directory / "nodo-viernes-paranormal.md").write_text(
        "| Subreddit | Descripción | sensitivity |\n|---|---|---|\n"
        "| nosleep | Terror. | entertainment |\n"
        "| Paranormal | Fenómenos. | entertainment |\n",
        encoding="utf-8",
    )
    (directory / "nodo-cronicas-de-justicia.md").write_text(
        "| Subreddit | Descripción | sensitivity |\n|---|---|---|\n"
        "| ProRevenge | Venganza. | entertainment |\n",
        encoding="utf-8",
    )

    assert subreddits_for_program("viernes-paranormal", directory) == ("nosleep", "Paranormal")
    assert subreddits_for_program("cronicas-de-justicia", directory) == ("ProRevenge",)


def test_subreddits_for_program_does_not_lose_subreddits_shared_across_programs(tmp_path):
    """A subreddit listed in two programs' node files (e.g. r/nosleep feeding
    both a short-stories and a long-stories program) must appear for BOTH --
    load_source_map()'s cross-file "first file wins" dedup is right for a
    global sensitivity lookup but would silently starve whichever program
    sorts second of a subreddit its own file explicitly lists."""
    directory = tmp_path / "reddit-sources"
    directory.mkdir()
    (directory / "nodo-aaa-first.md").write_text(
        "| Subreddit | Descripción | sensitivity |\n|---|---|---|\n"
        "| shared | Compartido. | entertainment |\n",
        encoding="utf-8",
    )
    (directory / "nodo-zzz-second.md").write_text(
        "| Subreddit | Descripción | sensitivity |\n|---|---|---|\n"
        "| shared | Compartido. | entertainment |\n",
        encoding="utf-8",
    )

    assert subreddits_for_program("aaa-first", directory) == ("shared",)
    assert subreddits_for_program("zzz-second", directory) == ("shared",)


def test_subreddits_for_program_unknown_program_is_empty_not_an_error(tmp_path):
    directory = tmp_path / "reddit-sources"
    directory.mkdir()
    assert subreddits_for_program("not-a-real-program", directory) == ()


def test_real_program_node_files_have_real_subreddits():
    directory = Path(__file__).resolve().parents[1] / "knowledge" / "reddit-sources"
    for program_id in (
        "decisiones-dificiles", "confesiones-anonimas", "cronicas-de-justicia",
        "mentes-ocultas", "viernes-paranormal", "historias-medianoche", "caso-de-la-semana",
    ):
        subreddits = subreddits_for_program(program_id, directory)
        assert subreddits, f"{program_id} has no subreddits in its nodo-*.md file"


def test_real_viernes_paranormal_includes_nosleep_despite_it_also_feeding_saturday():
    directory = Path(__file__).resolve().parents[1] / "knowledge" / "reddit-sources"
    assert "nosleep" in subreddits_for_program("viernes-paranormal", directory)
    assert "nosleep" in subreddits_for_program("historias-medianoche", directory)
