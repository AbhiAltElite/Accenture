"""The narrative, and the gate it has to pass.

    result -> brief -> writer -> validator -> Narrative

`narrate` is the only entry point the API uses. It always returns a narrative:
if the model is unavailable, the template writes it; if the model writes and
the validator rejects everything, the template writes it and the fallback is
reported rather than hidden. What varies is who wrote it and what it cost, and
both are on the receipt.
"""

from __future__ import annotations

from dataclasses import dataclass

from whychain.narrate.brief import Brief, Fact, build_brief, format_value
from whychain.narrate.validate import (
    Failure,
    Rejection,
    Sentence,
    ValidationResult,
    validate,
)
from whychain.narrate.writer import (
    ModelWriter,
    TemplateWriter,
    Writer,
    Written,
    default_writer,
)


@dataclass(frozen=True)
class Narrative:
    """Validated prose, with the audit of how it got there attached."""

    text: str
    sentences: tuple[Sentence, ...]
    validation: ValidationResult
    writer: str
    model_calls: int
    tokens_in: int
    tokens_out: int
    note: str
    cache_hits: int = 0
    fell_back: bool = False

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "sentences": [s.as_dict() for s in self.sentences],
            "validation": self.validation.as_dict(),
            "writer": self.writer,
            "model_calls": self.model_calls,
            "cache_hits": self.cache_hits,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "note": self.note,
            "fell_back": self.fell_back,
        }


def narrate(
    result: dict,
    *,
    writer: Writer | None = None,
    known_entities: frozenset[str] = frozenset(),
) -> Narrative:
    """Write the summary for one diagnosis, and prove every sentence.

    A model failure is not an error condition for the caller. If the call
    raises, the template runs and `fell_back` records it; the diagnosis is
    already complete at this point and the narrative is the last thing added
    to it, so there is nothing to abandon.
    """
    brief = build_brief(result)
    writer = writer or default_writer()

    try:
        written = writer.write(brief)
        failure_note = ""
    except Exception as exc:
        written = TemplateWriter().write(brief)
        # The class alone was not diagnosable: every hosted failure arrives as
        # RuntimeError, so "model writer failed (RuntimeError)" could equally be
        # a bad key, a rejected schema or a capacity spike. The message carries
        # the status code, and the receipt is where a reader looks when the
        # narrative is not the one they expected.
        failure_note = (
            f"model writer failed ({type(exc).__name__}: {exc}), template used"
        )

    validation = validate(list(written.sentences), brief, known_entities=known_entities)
    fell_back = bool(failure_note)

    # Nothing survived to print. Falling back is the honest move; emitting an
    # empty narrative would read as "nothing to say".
    #
    # This used to require `written.sentences` as well, which meant it covered
    # the writer whose sentences were all rejected and missed the writer that
    # returned no sentences at all. A model answering with an empty object
    # therefore produced an empty narrative reported as model-written, clean and
    # not fallen back -- the receipt describing work that did not happen, which
    # is the one failure this engine cannot afford. The condition is now about
    # the output, not about how much of it there was.
    if not validation.accepted and written.writer != TemplateWriter.name:
        fallback = TemplateWriter().write(brief)
        validation = validate(list(fallback.sentences), brief, known_entities=known_entities)
        failure_note = (
            f"the {written.writer} writer returned no sentences; "
            "the deterministic template was used instead"
            if not written.sentences else
            f"every sentence from the {written.writer} writer failed validation; "
            "the deterministic template was used instead"
        )
        written = Written(
            sentences=fallback.sentences,
            model_calls=written.model_calls,
            cache_hits=written.cache_hits,
            tokens_in=written.tokens_in,
            tokens_out=written.tokens_out,
            writer=f"{written.writer} -> template",
            note=fallback.note,
        )
        fell_back = True

    return Narrative(
        text=" ".join(s.text for s in validation.accepted),
        sentences=validation.accepted,
        validation=validation,
        writer=written.writer,
        model_calls=written.model_calls,
        cache_hits=written.cache_hits,
        tokens_in=written.tokens_in,
        tokens_out=written.tokens_out,
        note=" · ".join(n for n in (written.note, failure_note) if n),
        fell_back=fell_back,
    )


__all__ = [
    "Brief",
    "Fact",
    "Failure",
    "ModelWriter",
    "Narrative",
    "Rejection",
    "Sentence",
    "TemplateWriter",
    "ValidationResult",
    "Writer",
    "Written",
    "build_brief",
    "default_writer",
    "format_value",
    "narrate",
    "validate",
]
