#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "apps" / "api"
OUTPUT = REPO_ROOT / "contracts" / "mutation-security-matrix.csv"
API_VENV = API_ROOT / ".venv"

# Local development keeps API dependencies in apps/api/.venv; GitHub Actions
# installs them into its selected Python environment. Re-exec only when the
# local venv exists and this command was launched by an unrelated interpreter.
if API_VENV.exists() and Path(sys.prefix).resolve() != API_VENV.resolve():
    os.execv(
        str(API_VENV / "bin" / "python"),
        [str(API_VENV / "bin" / "python"), __file__, *sys.argv[1:]],
    )
sys.path.insert(0, str(API_ROOT))

from app.core.mutation_security import (  # noqa: E402
    build_mutation_security_matrix,
    render_mutation_security_matrix_csv,
)
from app.main import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = render_mutation_security_matrix_csv(
        build_mutation_security_matrix(create_app())
    )
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(
                "mutation security matrix is stale; run "
                "python3 infra/scripts/generate-mutation-security-matrix.py",
                file=sys.stderr,
            )
            return 1
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
