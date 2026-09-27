"""The track catalogue (tracks/*.yaml): every card agrees with the render
lock, and the Tracks page is current with the cards (export_cards.py)."""
import json

import export_cards as EX


def test_cards_match_the_lock():
    albums, cards = EX.load_cards()
    assert EX.check(cards, json.loads(EX.LOCK.read_text())) == []
    listed = [t for a in albums for t in a["tracks"]]
    assert sorted(listed) == sorted(c["id"] for c in cards.values())  # every card in exactly one album
    assert len(listed) == len(set(listed))


def test_every_card_has_what_a_card_promises():
    for c in EX.load_cards()[1].values():
        for k in ("question", "place", "year", "records", "mapping", "harmony", "limitations", "credits", "changelog"):
            assert c.get(k), (c["id"], k)
        assert any("Claude Code" in x for x in c["credits"]), c["id"]  # AI assistance is always credited


def test_tracks_page_is_current():
    text, _ = EX.render()
    assert EX.OUT.read_text() == text, "run scripts/export_cards.py"
