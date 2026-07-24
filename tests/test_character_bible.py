from kronara.character_bible import build_character_bible


class FakeRouter:
    def __init__(self, payload=None, *, fail=False):
        self.calls = 0
        self.last_kwargs = None
        self._payload = payload
        self._fail = fail

    def complete(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._fail:
            raise RuntimeError("no quota")
        return self._payload


def test_character_bible_maps_names_to_appearance_via_one_call():
    router = FakeRouter(
        {
            "characters": [
                {"name": "Ana", "appearance": "mujer 30s, pelo negro corto, impermeable rojo"},
                {"name": "Luis", "appearance": "hombre 40s, barba, abrigo gris"},
            ]
        }
    )
    bible = build_character_bible(router, character_names=["Ana", "Luis"], premise="p", theme="t")
    assert router.calls == 1
    assert bible["ana"] == "mujer 30s, pelo negro corto, impermeable rojo"
    assert bible["luis"] == "hombre 40s, barba, abrigo gris"
    # The character names actually reached the model.
    assert router.last_kwargs["input_payload"]["characters"] == ["Ana", "Luis"]


def test_character_bible_makes_no_call_and_is_empty_without_names():
    router = FakeRouter({"characters": []})
    assert build_character_bible(router, character_names=["", "  "]) == {}
    assert router.calls == 0


def test_character_bible_degrades_to_empty_on_router_failure():
    router = FakeRouter(fail=True)
    assert build_character_bible(router, character_names=["Ana"]) == {}


def test_character_bible_ignores_malformed_items():
    router = FakeRouter({"characters": [{"name": "Ana"}, {"appearance": "x"}, "junk"]})
    assert build_character_bible(router, character_names=["Ana"]) == {}
