#!/usr/bin/env python3
"""Embed verified Career Vault sections with OpenAI and index vectors in Chroma Cloud."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vault_evidence import (
    SemanticSearchUnavailable,
    build_chroma_index,
    default_embedding_model,
    default_vault_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=default_vault_path())
    parser.add_argument(
        "--embedding-model",
        default=default_embedding_model(),
        help="OpenAI model used to embed eligible vault sections",
    )
    args = parser.parse_args()
    count = build_chroma_index(args.vault, args.embedding_model)
    print(f"Indexed {count} eligible vault sections in Chroma Cloud.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, SemanticSearchUnavailable) as error:
        print(f"index_vault_chroma: {error}", file=sys.stderr)
        raise SystemExit(1) from error
