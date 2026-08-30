"""The model layer must be swappable, and absent must be a supported state.

Two properties matter more than which model is configured. The engine must not
depend on a vendor, so that a compliance decision about model choice is a
configuration change rather than a rewrite. And with no backend reachable the
engine must still answer, because a diagnosis that fails when a network call
fails is not one a finance team can rely on.
"""

from __future__ import annotations

import json

import pytest

from whychain.corroborate.model_extract import ModelExtractor
from whychain.corroborate.quarantine import quarantine
from whychain.llm import ChatModel, Completion, default_model, describe
from whychain.narrate import build_brief, narrate
from whychain.narrate.writer import ModelWriter, default_writer

TICKET = "The card page just spins on my phone and I never reach the confirm screen."


class FakeModel:
    """A backend that returns whatever the test hands it."""

    name = "fake-7b"
    backend = "fake"

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema, max_tokens=4096) -> Completion:
        self.calls += 1
        return Completion(
            text=json.dumps(self.payload), model=self.name,
            tokens_in=100, tokens_out=40, backend=self.backend,
        )


class TestTheProtocolIsTheOnlyDependency:
    def test_a_backend_needs_nothing_but_the_protocol(self):
        """No SDK, no vendor class, no inheritance. Just the three obligations."""
        assert isinstance(FakeModel({}), ChatModel)

    def test_the_engine_imports_no_vendor_sdk(self):
        """A dependency file with a vendor in it is a lock-in a reviewer can see."""
        pinned = __import__("pathlib").Path("requirements.txt").read_text().lower()
        for vendor in ("anthropic", "openai==", "google-generativeai", "cohere"):
            assert vendor not in pinned, f"{vendor} is pinned; the layer is meant to be neutral"


class TestAbsenceIsSupported:
    @pytest.mark.invariant
    def test_forcing_none_yields_no_backend(self, monkeypatch):
        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "none")
        assert default_model() is None

    def test_the_absent_case_explains_itself(self):
        """A reader who sees zero model calls must be told why, and what to do."""
        text = describe(None)
        assert "ollama" in text.lower()
        assert "deterministic" in text.lower()

    @pytest.mark.invariant
    def test_extraction_falls_back_rather_than_failing(self, monkeypatch):
        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "none")
        extractor = ModelExtractor()
        assert not extractor.available
        # The rule table still reads the ticket, so the pipeline continues.
        extractor.extract([quarantine("t-1", TICKET)])
        assert extractor.calls == 0
        assert "rule-based" in extractor.note

    def test_the_writer_falls_back_rather_than_failing(self, monkeypatch):
        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "none")
        assert not ModelWriter().available
        assert type(default_writer()).__name__ == "TemplateWriter"


class TestTheCitationIsVerifiedNotTrusted:
    """The property that makes a small open model safe to use here."""

    def _extract(self, quote: str):
        backend = FakeModel(
            {"extractions": [{
                "doc_id": "t-1", "issue": "checkout_failure", "quote": quote,
                "channel": None, "device": "mobile", "category": None,
            }]}
        )
        extractor = ModelExtractor(backend=backend)
        return extractor, extractor.extract([quarantine("t-1", TICKET)])

    @pytest.mark.invariant
    def test_a_verbatim_quote_resolves_to_a_span_in_the_source(self):
        quote = "The card page just spins on my phone"
        extractor, out = self._extract(quote)
        assert extractor.calls == 1
        assert len(out) == 1
        start, end = out[0].span
        assert TICKET[start:end] == quote

    @pytest.mark.invariant
    def test_a_paraphrase_is_dropped_rather_than_cited(self):
        """A tidied quote is not in the document, so it gets no citation.

        This is the whole reason a 7B model is safe in this stage: it cannot
        manufacture a reference to text that does not exist.
        """
        _, out = self._extract("The card page spins on the user's phone.")
        assert out == []

    def test_the_drop_is_recorded_with_a_reason(self):
        extractor, _ = self._extract("something the customer never wrote")
        assert extractor.dropped
        assert "not found in source" in extractor.dropped[0]

    def test_an_unknown_document_id_is_dropped(self):
        backend = FakeModel(
            {"extractions": [{
                "doc_id": "no-such-doc", "issue": "stockout", "quote": TICKET,
                "channel": None, "device": None, "category": None,
            }]}
        )
        extractor = ModelExtractor(backend=backend)
        assert extractor.extract([quarantine("t-1", TICKET)]) == []


class TestTheWriterUsesWhateverBackend:
    def test_sentences_come_back_with_their_cost(self):
        backend = FakeModel(
            {"sentences": [{"text": "Net revenue in West moved −₹35,323 per day.",
                            "cites": ["f-movement"]}]}
        )
        written = ModelWriter(backend=backend).write(build_brief(RESULT))
        assert written.model_calls == 1
        assert written.tokens_in == 100 and written.tokens_out == 40
        assert "fake" in written.note

    def test_a_backend_failure_falls_back_and_says_so(self):
        class Broken:
            name, backend = "broken", "fake"
            available = True

            def complete(self, **_):
                raise RuntimeError("endpoint down")

        story = narrate(RESULT, writer=ModelWriter(backend=Broken()))
        assert story.text
        assert story.fell_back


RESULT = {
    "run_id": "run-llm-test",
    "kpi_id": "net_revenue",
    "region": "West",
    "verdict": "explained",
    "window": {"from": "2026-08-13", "to": "2026-08-16"},
    "movement": {"total_change": -35323.0, "pct": -0.129, "explained": -35323.0},
    "confidence": {"score": 0.86, "band": "high"},
    "verified": [],
    "set_aside": [],
    "decisions": [],
}


class TestTheCatalogueIsHonest:
    """What the console offers must be what the server can actually reach."""

    def test_every_backend_declares_licence_and_sovereignty(self):
        """The two terms a model choice is actually decided on."""
        from whychain.llm import catalogue

        for row in catalogue():
            assert row["licence"], f"{row['id']} declares no licence"
            assert row["sovereignty"], f"{row['id']} does not say where inference runs"

    @pytest.mark.invariant
    def test_an_unimplemented_backend_never_reports_available(self):
        """A platform backend nobody has run is a claim, not a capability.

        Listing it is useful: it shows where an enterprise platform attaches.
        Listing it as reachable would be the kind of unearned claim this
        project exists to argue against.
        """
        from whychain.llm import catalogue

        enterprise = next(r for r in catalogue() if r["id"] == "enterprise")
        assert enterprise["available"] is False
        assert "not implemented" in enterprise["note"].lower()

    def test_the_no_model_option_is_always_reachable(self):
        """The deterministic path is the floor and can never be unavailable."""
        from whychain.llm import catalogue

        assert next(r for r in catalogue() if r["id"] == "none")["available"] is True

    def test_a_request_can_pin_a_backend(self, monkeypatch):
        """Per-request selection is what makes the choice demonstrable."""
        from whychain.llm import default_model

        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "ollama")
        assert default_model(backend="none") is None


class TestOneBackendsSettingsAreNotAnothers:
    """A hosted endpoint in the environment must not disable the local one.

    `WHYCHAIN_LLM_MODEL` and `WHYCHAIN_LLM_BASE_URL` were read by both classes,
    so configuring OpenRouter pointed `OllamaModel` at it as well: it probed an
    HTTPS provider for `/api/tags`, found no model matching that provider's
    catalogue, and reported itself unavailable while Ollama was running locally.
    The console's local option was then unselectable for as long as a hosted key
    sat in `.env` -- which is the whole of a demo.
    """

    def test_a_hosted_endpoint_leaves_the_local_defaults_alone(self, monkeypatch):
        from whychain.llm.local import DEFAULT_BASE_URL, DEFAULT_MODEL, OllamaModel

        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "openai")
        monkeypatch.setenv("WHYCHAIN_LLM_BASE_URL", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("WHYCHAIN_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

        local = OllamaModel()
        assert local.name == DEFAULT_MODEL
        assert local.base_url == DEFAULT_BASE_URL

    def test_the_local_backend_takes_its_own_overrides(self, monkeypatch):
        from whychain.llm.local import OllamaModel

        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "openai")
        monkeypatch.setenv("WHYCHAIN_LLM_BASE_URL", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("WHYCHAIN_OLLAMA_BASE_URL", "http://gpu-box:11434")
        monkeypatch.setenv("WHYCHAIN_OLLAMA_MODEL", "qwen2.5:7b-instruct")

        local = OllamaModel()
        assert local.name == "qwen2.5:7b-instruct"
        assert local.base_url == "http://gpu-box:11434"

    def test_an_unset_backend_still_shares_the_model(self, monkeypatch):
        """The single-backend setup this started as is unchanged.

        The URL is the exception: `WHYCHAIN_LLM_BASE_URL` is documented as the
        OpenAI-compatible endpoint, so a remote Ollama uses its own variable
        rather than borrowing one that means something else.
        """
        from whychain.llm.local import DEFAULT_BASE_URL, OllamaModel

        monkeypatch.delenv("WHYCHAIN_LLM_BACKEND", raising=False)
        monkeypatch.setenv("WHYCHAIN_LLM_BASE_URL", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("WHYCHAIN_LLM_MODEL", "qwen2.5:7b-instruct")

        local = OllamaModel()
        assert local.name == "qwen2.5:7b-instruct"
        assert local.base_url == DEFAULT_BASE_URL

    def test_selecting_the_local_backend_leaves_the_hosted_one_unconfigured(
        self, monkeypatch
    ):
        from whychain.llm.hosted import OpenAICompatibleModel

        monkeypatch.setenv("WHYCHAIN_LLM_BACKEND", "ollama")
        monkeypatch.setenv("WHYCHAIN_LLM_BASE_URL", "https://openrouter.ai/api/v1")

        assert OpenAICompatibleModel().base_url == ""
