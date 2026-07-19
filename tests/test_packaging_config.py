from pathlib import Path


def test_sidecar_packaging_discovers_all_kronara_submodules_and_resources():
    script = (
        Path(__file__).parents[1] / "scripts" / "build-sidecar.ps1"
    ).read_text(encoding="utf-8")

    assert "$env:PYTHONPATH" in script
    assert "--collect-submodules 'kronara'" in script
    assert "'config');config" in script
    assert "'knowledge');knowledge" in script
