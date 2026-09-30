#!/usr/bin/env python3
"""Verify that the local transformer runtime can encode text."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-cache", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    started = time.monotonic()

    try:
        from embedding_runtime import load_embedding_model

        model = load_embedding_model(
            args.model,
            args.model_cache,
            allow_model_download=False,
        )
        documents = model.encode_document(
            ["local semantic runtime health check"],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        query = model.encode_query(
            "local semantic runtime health check",
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        similarity = float((documents @ query)[0])
    except Exception as error:  # Libraries expose several model/cache exceptions.
        print(f"Semantic runtime health check failed: {error}", file=sys.stderr)
        return 1

    if documents.ndim != 2 or tuple(documents.shape) != (1, 384):
        print(
            f"Semantic runtime returned an unexpected embedding shape: {tuple(documents.shape)}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Semantic runtime passed: model={args.model}, shape={tuple(documents.shape)}, "
        f"self_similarity={similarity:.4f}, elapsed_seconds={time.monotonic() - started:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
