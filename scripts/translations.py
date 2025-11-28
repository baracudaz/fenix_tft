#!/usr/bin/env python3
"""
Translation verification script for Fenix TFT integration.

This script checks translation files against en.json (source) and reports:
- Missing keys: present in en.json but missing in translation
- Extra keys: present in translation but not in en.json

Usage: python scripts/check_translations.py
"""

import json
import sys
from pathlib import Path


def collect_keys(data: dict, prefix: str = "") -> set[str]:
    """Recursively collect all dot-separated keys from a dict."""
    keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            p = f"{prefix}.{k}" if prefix else k
            keys.add(p)
            if isinstance(v, dict):
                keys |= collect_keys(v, p)
    return keys


def main() -> None:
    """Check translation alignment."""
    repo_root = Path(__file__).parent.parent
    translations_dir = repo_root / "custom_components" / "fenix_tft" / "translations"

    if not translations_dir.exists():
        print(f"Error: Translations directory not found: {translations_dir}")  # noqa: T201
        sys.exit(1)

    # Load English (source)
    en_file = translations_dir / "en.json"
    if not en_file.exists():
        print(f"Error: en.json not found: {en_file}")  # noqa: T201
        sys.exit(1)

    with en_file.open(encoding="utf-8") as f:
        en_data = json.load(f)

    en_keys = collect_keys(en_data)

    # Check each translation file
    translation_files = ["cs.json", "de.json", "fr.json", "sk.json"]
    all_good = True

    for tf in translation_files:
        tf_path = translations_dir / tf
        if not tf_path.exists():
            print(f"Warning: {tf} not found, skipping.")  # noqa: T201
            continue

        with tf_path.open(encoding="utf-8") as f:
            tf_data = json.load(f)

        tf_keys = collect_keys(tf_data)

        missing = sorted(en_keys - tf_keys)
        extra = sorted(tf_keys - en_keys)

        if missing or extra:
            all_good = False
            print(f"\n{tf}:")  # noqa: T201
            if missing:
                print(f"  Missing keys ({len(missing)}):")  # noqa: T201
                for k in missing:
                    print(f"    {k}")  # noqa: T201
            if extra:
                print(f"  Extra keys ({len(extra)}):")  # noqa: T201
                for k in extra:
                    print(f"    {k}")  # noqa: T201
        else:
            print(f"{tf}: OK")  # noqa: T201

    if all_good:
        print("\nAll translations are aligned with en.json.")  # noqa: T201
        sys.exit(0)
    else:
        print("\nSome translations have issues. Please fix them.")  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    main()
