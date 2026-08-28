"""Text embedding for corroboration retrieval.

The default embedder runs offline and deterministically so that stages 0-8 and
the entire benchmark need no API key, and so repeated runs over the same corpus
produce identical evidence (see the determinism invariant).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer


@runtime_checkable
class Embedder(Protocol):
    """Turns text into unit-norm vectors."""

    @property
    def dim(self) -> int: ...

    def fit(self, corpus: list[str]) -> None: ...

    def encode(self, texts: list[str]) -> np.ndarray: ...


class TfidfSvdEmbedder:
    """TF-IDF reduced by SVD, latent semantic indexing.

    Chosen over a hosted embedding model for the local default because it is
    deterministic, needs no network, and at demo corpus size retrieves well
    enough that retrieval quality is not what limits the diagnosis. Swap in a
    hosted embedder by implementing the Embedder protocol.
    """

    def __init__(self, dim: int = 128, random_state: int = 0) -> None:
        self._dim = dim
        self._random_state = random_state
        self._pipeline = None

    @property
    def dim(self) -> int:
        return self._dim

    def fit(self, corpus: list[str]) -> None:
        if not corpus:
            raise ValueError("cannot fit an embedder on an empty corpus")

        # SVD cannot produce more components than the term matrix has columns, and
        # the column count is the vocabulary, not the corpus. A large set of
        # similarly worded tickets has far fewer distinct terms than documents, so
        # the vectorizer is fitted first and the dimension taken from what it found.
        vectorizer = TfidfVectorizer(sublinear_tf=True, stop_words="english", min_df=1)
        matrix = vectorizer.fit_transform(corpus)
        n_features = matrix.shape[1]
        if n_features < 2:
            raise ValueError(
                f"corpus has only {n_features} distinct term(s); there is nothing to "
                "distinguish documents by"
            )

        n_components = min(self._dim, n_features - 1)
        self._pipeline = make_pipeline(
            vectorizer,
            TruncatedSVD(n_components=n_components, random_state=self._random_state),
            Normalizer(copy=False),
        )
        self._pipeline.fit(corpus)
        self._dim = n_components

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._pipeline is None:
            raise RuntimeError("embedder must be fitted before encoding")
        return np.asarray(self._pipeline.transform(texts), dtype=np.float32)
