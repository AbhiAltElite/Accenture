"""Prove the model path works, before a demo depends on it.

Both model stages fall back to deterministic code when anything goes wrong: no
key, a bad key, a schema the API rejects, a network failure. That is the right
behaviour for a diagnosis, which should never fail because a network call did.
It is the wrong behaviour ten minutes before a demo, because the console shows
a complete, correct, entirely deterministic answer and nothing about it says
"your API key is malformed".

So this script removes the safety net on purpose. It calls each stage directly,
lets failures raise, and exits non-zero. Run it before any demo where the AI
contribution is part of what is being shown.

    make verify-ai

With no key configured it explains what to set and exits 0, because "the AI path
is off and the system runs anyway" is a true and intended state, not a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whychain.corroborate.model_extract import ModelExtractor
from whychain.corroborate.quarantine import quarantine
from whychain.env import load_env
from whychain.llm import default_model, describe
from whychain.narrate import build_brief
from whychain.narrate.validate import validate
from whychain.narrate.writer import ModelWriter

# Before anything reads the environment, and after the imports so the path
# bootstrap above still comes first. Settings are read when a backend is
# constructed, not when this module is imported, so here is early enough.
load_env()

# A ticket no keyword table would catch. The vocabulary is the customer's, not
# the company's: no "checkout", no "payment failure", no product noun at all.
TICKET = (
    "Tried three times on my phone last night and the card bit just spins "
    "forever, never got to the confirm screen. Gave up and used a different site."
)

RESULT = {
    "run_id": "verify-ai",
    "kpi_id": "net_revenue",
    "region": "West",
    "verdict": "explained",
    "window": {"from": "2026-08-13", "to": "2026-08-16"},
    "movement": {"total_change": -35323.0, "pct": -0.129, "explained": -35323.0},
    "confidence": {"score": 0.86, "band": "high"},
    "verified": [
        {
            "candidate_id": "rel-4.05",
            "description": "rel-4.05: Release 4.05 broke card entry on the Android checkout flow.",
            "contribution": -26187.0,
            "effect_pct": -0.288,
            "exposed_regions": ["West"],
            "scope": {"channel": "app", "device": "mobile"},
        }
    ],
    "set_aside": [],
    "decisions": [],
}

KNOWN = frozenset({"West", "net_revenue", "app", "mobile"})


def main() -> int:
    backend = default_model()
    if backend is None:
        print("No model backend is reachable.\n")
        print(describe(None) + "\n")
        print("The engine runs without one: extraction falls back to the rule")
        print("table, the narrative to the deterministic writer, and the run")
        print("receipt reports zero model calls rather than the two the design")
        print("intends. That is a supported configuration, and the benchmark is")
        print("produced in it so the numbers do not move when a model does.\n")
        print("To exercise the model path, either:")
        print("  brew install ollama && ollama serve")
        print("  ollama pull mistral:7b-instruct        # Apache 2.0, no account")
        print("or point at any OpenAI-compatible endpoint serving open weights:")
        print("  export WHYCHAIN_LLM_BASE_URL=https://api.groq.com/openai/v1")
        print("  export WHYCHAIN_LLM_API_KEY=...")
        return 0

    print(f"Backend      {describe(backend)}\n")

    failures = 0

    print("1. Extraction  reading a ticket written in the customer's words")
    extractor = ModelExtractor()
    extractions = extractor.extract([quarantine("ticket-verify", TICKET)])
    print(f"   model        {extractor.model}")
    print(f"   calls        {extractor.calls}")
    print(f"   tokens       {extractor.tokens_in} in / {extractor.tokens_out} out")
    if extractor.calls == 0:
        print("   FAILED       no call was made; check the key and the SDK")
        failures += 1
    elif not extractions:
        print("   FAILED       the model returned nothing for a clear complaint")
        failures += 1
    else:
        found = extractions[0]
        print(f"   issue        {found.issue.value}")
        print(f"   span         {found.span[0]}-{found.span[1]}")
        print(f"   quote        {found.quote[:60]!r}")
        # The whole point of the design: the citation resolves in the source.
        if TICKET[found.span[0] : found.span[1]] != found.quote:
            print("   FAILED       the span does not resolve to the quote")
            failures += 1
        else:
            print("   verified     the span resolves to the quoted text")
    if extractor.dropped:
        print(f"   dropped      {len(extractor.dropped)} unverifiable citation(s)")

    print("\n2. Narrative  writing from the evidence table and nothing else")
    writer = ModelWriter()
    written = writer.write(build_brief(RESULT))
    print(f"   model        {writer.model}")
    print(f"   calls        {written.model_calls}")
    print(f"   tokens       {written.tokens_in} in / {written.tokens_out} out")
    if written.model_calls == 0 or not written.sentences:
        print("   FAILED       no sentences came back")
        failures += 1
    else:
        checked = validate(
            list(written.sentences), build_brief(RESULT), known_entities=KNOWN
        )
        print(f"   sentences    {len(written.sentences)} written")
        print(f"   accepted     {len(checked.accepted)}")
        print(f"   rejected     {len(checked.rejected)}")
        for rejection in checked.rejected:
            print(f"     - {rejection.failure.value}: {rejection.detail}")
        if not checked.accepted:
            print("   FAILED       the validator rejected every sentence")
            failures += 1
        else:
            print(f"\n   {checked.accepted[0].text}")

    total_in = extractor.tokens_in + written.tokens_in
    total_out = extractor.tokens_out + written.tokens_out
    calls = extractor.calls + written.model_calls
    print(f"\n   {calls} model call(s), {total_in + total_out} tokens.")
    # What the tokens cost depends on where inference happened, and saying
    # "self-hosted, so the marginal cost is compute" while billing a hosted
    # provider per token is the same untruth as a licence claim that does not
    # match the model. The backend already knows which it is.
    if backend.backend == "ollama":
        print("   Self-hosted open weights, so the marginal cost of a diagnosis is")
        print("   compute rather than a per-token charge.")
    else:
        print(f"   Billed per token by the configured endpoint ({backend.name}),")
        print("   and inference left the boundary. The local open-weight backend")
        print("   is the default for exactly that reason; this is the latency trade.")

    print("\nFAILED" if failures else "\nBoth model stages work.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
