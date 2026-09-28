"""Explain this card: the model says what one card shows, from that card's facts.

The claim this feature makes on the page is "N of N sentences checked against
this card's figures; it calculates nothing". These tests are what make that
sentence true.
"""

from __future__ import annotations

import json
import os

import pytest

from whychain.llm import Completion
from whychain.narrate.explain import CARDS, card_brief, explain

WEST = {"kpi": "net_revenue", "region": "West", "start": "2026-08-13", "end": "2026-08-15",
        "industry": "retail"}


class Fake:
    """A model that says exactly what the test tells it to."""

    name, backend = "fake-7b", "fake"
    available = True

    def __init__(self, sentences=None, raises=False):
        self.sentences, self.raises = sentences or [], raises

    def complete(self, *, system, user, schema, max_tokens=4096):
        if self.raises:
            raise RuntimeError("endpoint returned HTTP 503")
        return Completion(text=json.dumps({"sentences": self.sentences}), model=self.name,
                          backend=self.backend)


@pytest.fixture(scope="module")
def west():
    os.environ["WHYCHAIN_LLM_BACKEND"] = "none"
    from fastapi.testclient import TestClient

    from api.main import app
    c = TestClient(app)
    diag = c.get("/api/diagnose", params={**WEST, "persona": "analyst", "backend": "none"}).json()
    cand = c.get("/api/candidates", params=WEST).json()
    return c, diag, cand


def test_a_card_is_given_its_own_facts_and_no_others(west):
    _, diag, cand = west
    bridge = {f.id for f in card_brief("bridge", diag).facts}
    assert "f-bridge-before" in bridge and "f-bridge-after" in bridge
    assert not any(i.startswith("f-decision") for i in bridge)
    fish = card_brief("fishbone", diag, cand).facts
    assert any(f.state == "rejected" for f in fish) and any(f.kind == "cause" for f in fish)
    assert all(f.id.startswith("f-whatif") for f in card_brief("whatif", diag).facts)


def test_an_invented_figure_is_removed(west):
    _, diag, _ = west
    fake = Fake([{"text": "The figure went from ₹99,999 to nowhere.", "cites": ["f-bridge-before"]},
                 {"text": "It started at ₹2,71,320 a day.", "cites": ["f-bridge-before"]}])
    out = explain("bridge", diag, backend=fake)
    assert out.writer == "model"
    assert [s.text for s in out.sentences] == ["It started at ₹2,71,320 a day."]
    assert len(out.validation.rejected) == 1


def test_square_bracket_citations_are_not_read_as_figures(west):
    """Ultra wrote "[f-whatif-price_move-also-1]" and the "-1" failed every sentence."""
    _, diag, _ = west
    fid = next(f.id for f in card_brief("whatif", diag).facts if "-also-" in f.id)
    disp = next(f.display for f in card_brief("whatif", diag).facts if f.id == fid)
    out = explain("whatif", diag, backend=Fake([{"text": f"Revenue moves by {disp} a day [{fid}].",
                                                  "cites": [fid]}]))
    assert out.writer == "model" and len(out.sentences) == 1
    assert "[" not in out.as_dict()["text"]


def test_a_ruled_out_cause_cannot_be_stated_as_the_cause(west):
    _, diag, cand = west
    rid = next(f.id for f in card_brief("fishbone", diag, cand).facts if f.state == "rejected")
    out = explain("fishbone", diag, cand,
                  backend=Fake([{"text": "The promotion caused the fall.", "cites": [rid]}]))
    assert out.writer == "template"      # nothing the model wrote survived


def test_a_model_failure_falls_back_to_the_template(west):
    _, diag, _ = west
    out = explain("decide", diag, backend=Fake(raises=True))
    assert out.writer == "template" and out.sentences
    assert out.as_dict()["model"] == "none"


def test_the_endpoint_explains_each_card_and_refuses_an_unknown_one(west):
    c, _, _ = west
    for card in CARDS:
        r = c.get("/api/explain", params={**WEST, "card": card, "persona": "cfo", "backend": "none"})
        assert r.status_code == 200 and r.json()["text"], card
    assert c.get("/api/explain", params={**WEST, "card": "nonsense"}).status_code == 422


def test_a_reader_whose_card_withholds_the_ruled_out_is_not_told_them(west):
    """The finance director's fishbone withholds what was ruled out; so does its explanation."""
    _, diag, _ = west
    facts = card_brief("fishbone", diag, None, withheld=True).facts
    assert not any(f.state == "rejected" for f in facts)
    assert any(f.id == "f-withheld" for f in facts)


def test_a_hyphen_for_a_minus_sign_is_the_same_number(west):
    """The engine writes a minus sign; a model types a hyphen. Not an invented figure."""
    _, diag, _ = west
    f = next(x for x in card_brief("bridge", diag).facts if x.display.startswith("\u2212"))
    out = explain("bridge", diag, backend=Fake([{"text": f"It fell by {f.display.replace(chr(0x2212), '-')} a day.",
                                                  "cites": [f.id]}]))
    assert out.writer == "model" and len(out.sentences) == 1
