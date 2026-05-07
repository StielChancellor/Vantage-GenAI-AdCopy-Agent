#!/usr/bin/env python3
"""Single-shot version bumper.

Updates the version in four places at once so they never drift:
    1. backend/app/core/version.py        APP_VERSION
    2. frontend/src/version.js            APP_VERSION
    3. frontend/package.json              "version" field
    4. README.md                          `App: X.Y — last live: …` header line

Usage:
    python scripts/bump_version.py 2.3
    python scripts/bump_version.py 2.3 --date 2026-06-15
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date as _date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_VERSION = REPO_ROOT / "backend" / "app" / "core" / "version.py"
FRONTEND_VERSION = REPO_ROOT / "frontend" / "src" / "version.js"
FRONTEND_PACKAGE = REPO_ROOT / "frontend" / "package.json"
README = REPO_ROOT / "README.md"


VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
HEADER_RE = re.compile(r"^App:\s*[0-9.]+\s*—\s*last live:\s*[0-9-]+\s*$", re.MULTILINE)


def update_backend(version: str, date_str: str) -> None:
    text = BACKEND_VERSION.read_text(encoding="utf-8")
    text = re.sub(r'APP_VERSION\s*=\s*"[^"]*"', f'APP_VERSION = "{version}"', text)
    text = re.sub(r'APP_VERSION_DATE\s*=\s*"[^"]*"', f'APP_VERSION_DATE = "{date_str}"', text)
    BACKEND_VERSION.write_text(text, encoding="utf-8")
    print(f"  [ok]{BACKEND_VERSION.relative_to(REPO_ROOT)}")


def update_frontend_js(version: str, date_str: str) -> None:
    text = FRONTEND_VERSION.read_text(encoding="utf-8")
    text = re.sub(r'APP_VERSION\s*=\s*"[^"]*"', f'APP_VERSION = "{version}"', text)
    text = re.sub(r'APP_VERSION_DATE\s*=\s*"[^"]*"', f'APP_VERSION_DATE = "{date_str}"', text)
    FRONTEND_VERSION.write_text(text, encoding="utf-8")
    print(f"  [ok]{FRONTEND_VERSION.relative_to(REPO_ROOT)}")


def update_package_json(version: str) -> None:
    """package.json wants `2.3.0` form (npm semver). We pad with .0 if needed."""
    pkg = json.loads(FRONTEND_PACKAGE.read_text(encoding="utf-8"))
    npm_version = version if version.count(".") == 2 else f"{version}.0"
    pkg["version"] = npm_version
    FRONTEND_PACKAGE.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
    print(f"  [ok]{FRONTEND_PACKAGE.relative_to(REPO_ROOT)}  (set to {npm_version})")


def update_readme(version: str, date_str: str) -> None:
    text = README.read_text(encoding="utf-8")
    new_line = f"App: {version} — last live: {date_str}"
    if HEADER_RE.search(text):
        text = HEADER_RE.sub(new_line, text, count=1)
    else:
        # Insert just under the H1 title with a blank line on each side.
        text = re.sub(
            r"^(# [^\n]+\n)",
            rf"\1\n{new_line}\n\n",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    README.write_text(text, encoding="utf-8")
    print(f"  [ok]{README.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", help='New version, e.g. "2.3"')
    parser.add_argument("--date", default=_date.today().isoformat(), help="Override release date")
    args = parser.parse_args()

    if not VERSION_RE.match(args.version):
        print(f"Invalid version '{args.version}'. Expected MAJOR.MINOR or MAJOR.MINOR.PATCH.", file=sys.stderr)
        return 2

    print(f"Bumping app version -> {args.version} (date: {args.date})")
    update_backend(args.version, args.date)
    update_frontend_js(args.version, args.date)
    update_package_json(args.version)
    update_readme(args.version, args.date)
    print("Done. Commit the four files together.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
