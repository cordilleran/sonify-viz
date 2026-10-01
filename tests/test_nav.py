"""The navbar's Pieces menu is generated from tracks/albums.yaml (export_nav.py) and is current."""
import export_nav as EN


def test_pieces_menu_is_current():
    text = EN.QUARTO.read_text()
    assert EN.render(text) == text, "run scripts/export_nav.py"


def test_every_album_page_is_in_the_menu():
    for a in EN.albums():
        assert f"href: {a['page']}" in EN.QUARTO.read_text(), a["id"]
