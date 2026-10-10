#!/usr/bin/env python3
"""Build a private condition-check profile from verified Obsidian notes."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vault_evidence import list_value, parse_frontmatter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = PROJECT_ROOT / "career-vault"
DEFAULT_OUTPUT = PROJECT_ROOT / ".state" / "condition-check.json"
AUTH_NOTE = Path("01 Profile/Work Authorization.md")
CAREER_NOTE = Path("01 Profile/Career Profile.md")


def read_verified_note(vault: Path, relative_path: Path) -> tuple[dict[str, Any], Path]:
    path = vault / relative_path
    try:
        metadata, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read profile note: {relative_path.as_posix()}") from error
    if (
        metadata.get("status") != "verified"
        or not list_value(metadata, "source")
        or metadata.get("last_verified") in (None, "", "null", "None")
    ):
        raise ValueError(f"Profile note is not verified and source-linked: {relative_path.as_posix()}")
    return metadata, path


def required_text(metadata: dict[str, Any], key: str, note: Path) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or value.strip().lower() in {"", "null", "none"}:
        raise ValueError(f"Missing {key} in verified profile note: {note.name}")
    return value.strip()


def required_bool(metadata: dict[str, Any], key: str, note: Path) -> bool:
    value = required_text(metadata, key, note).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"Invalid {key} in verified profile note: {note.name}")
    return value == "true"


def optional_bool(metadata: dict[str, Any], key: str, note: Path) -> bool | None:
    value = metadata.get(key)
    if value in (None, "", "null", "None"):
        return None
    if not isinstance(value, str) or value.lower() not in {"true", "false"}:
        raise ValueError(f"Invalid {key} in verified profile note: {note.name}")
    return value.lower() == "true"


def build_condition_profile(vault: Path, output: Path) -> dict[str, Any]:
    auth, auth_path = read_verified_note(vault, AUTH_NOTE)
    career, career_path = read_verified_note(vault, CAREER_NOTE)
    education = list_value(career, "education")
    if not education:
        raise ValueError(f"Missing education in verified profile note: {career_path.name}")

    profile = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "work_authorization": {
            "visa_type": required_text(auth, "visa_type", auth_path),
            "authorized_regions": [required_text(auth, "work_rights_regions", auth_path)],
            "full_current_work_rights_regions": [required_text(auth, "full_current_work_rights", auth_path)],
            "sponsorship_required": optional_bool(auth, "sponsorship_required", auth_path),
            "permanent_resident": required_bool(auth, "permanent_resident", auth_path),
            "australian_citizen": required_bool(auth, "australian_citizen", auth_path),
            "new_zealand_citizen": required_bool(auth, "new_zealand_citizen", auth_path),
        },
        "education": list(education),
        "sources": {
            "work_authorization": {
            "path": AUTH_NOTE.as_posix(),
            "last_verified": auth["last_verified"],
            "source": list(list_value(auth, "source")),
            },
            "education": {
            "path": CAREER_NOTE.as_posix(),
            "last_verified": career["last_verified"],
            "source": list(list_value(career, "source")),
            },
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(profile, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, output)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="write the private condition profile JSON")
    build.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        build_condition_profile(args.vault, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Private condition profile refreshed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
