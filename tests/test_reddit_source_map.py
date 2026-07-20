from pathlib import Path

from kronara.reddit_source_map import DEFAULT_SENSITIVITY, load_source_map, sensitivity_for

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
