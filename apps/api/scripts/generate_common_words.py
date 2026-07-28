"""Regenerate `services/data/common_english_words.txt`.

That file is the word list behind `services/name_matching.py`'s distinctiveness
guard: a *derived* single-token core (what is left of "Egyptian Museum" after
the structural word is peeled) is only usable as a search term if it is not an
ordinary English word. See the guard's own docstring for why length alone
could not answer that question.

**Source: the embedding model's WordPiece vocabulary.** `core/embeddings.py`
already loads `sentence-transformers/all-MiniLM-L6-v2`, whose tokenizer carries
the 30,522-entry `bert-base-uncased` vocabulary. That vocabulary is built by
frequency over a large English corpus (Wikipedia + BooksCorpus), so a token
that survives in it *as a whole word* — rather than being split into WordPiece
fragments — is by construction a frequent English word. That frequency property
is exactly the test the guard needs, and it costs nothing: no new dependency,
no network, and the generated file is plain text, so the runtime path never
touches the model.

Only words of 8+ characters are emitted. The length guard
(`_MIN_CORE_TOKEN_LEN`) runs first and rejects everything shorter, so shorter
entries could never be consulted — that alone takes the file from ~200 KB to
~85 KB.

    cd apps/api && venv/Scripts/python.exe scripts/generate_common_words.py

Re-run only if the embedding model changes. The output is committed; the
guard's behaviour must not depend on a model being present at runtime.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.embeddings import get_embedder  # noqa: E402
from core.logging_config import configure_script_logging  # noqa: E402
from services.name_matching import COMMON_WORDS_PATH, MIN_COMMON_WORD_LEN  # noqa: E402

logger = logging.getLogger("generate_common_words")


def main() -> int:
    configure_script_logging()

    vocab = get_embedder().tokenizer.get_vocab()
    words = sorted(
        w
        for w in vocab
        # `##x` entries are word *fragments*, which say nothing about whether
        # the whole token is a word. Anything non-alphabetic or capitalised is
        # not comparable with a normalised name, which is lowercase [a-z0-9 ].
        if w.isalpha() and w.islower() and len(w) >= MIN_COMMON_WORD_LEN
    )

    COMMON_WORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMMON_WORDS_PATH.write_text("\n".join(words) + "\n", encoding="utf-8")

    logger.info(
        "Wrote %d words (>= %d chars) to %s (%.0f KB) from a %d-entry vocabulary",
        len(words),
        MIN_COMMON_WORD_LEN,
        COMMON_WORDS_PATH,
        COMMON_WORDS_PATH.stat().st_size / 1024,
        len(vocab),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
