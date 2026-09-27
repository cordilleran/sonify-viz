"""The shared glossary (glossary.yaml): one meaning per term, used word for word
by every data dictionary, and the Glossary page is current (export_glossary.py)."""
import export_glossary as EG


def test_terms_are_unique_and_in_a_known_domain():
    terms = EG.load()
    names = [t["term"].lower() for t in terms]
    assert len(names) == len(set(names))
    assert {t["domain"] for t in terms} <= set(EG.DOMAINS)


def test_dictionaries_use_the_shared_definitions():
    shared = {t["term"]: " ".join(t["definition"].split()) for t in EG.load()}
    for name, glossary in EG.dictionaries().items():
        for term, definition in glossary.items():
            assert term in shared, f"{name}: '{term}' is not in glossary.yaml"
            assert definition == shared[term], f"{name}: '{term}' differs from glossary.yaml"


def test_glossary_page_is_current():
    text, _ = EG.render()
    assert EG.OUT.read_text() == text, "run scripts/export_glossary.py"
