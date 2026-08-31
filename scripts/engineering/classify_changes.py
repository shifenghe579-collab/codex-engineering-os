from __future__ import annotations

import argparse
import os
from pathlib import Path

from os_core import changed_files, is_protected_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a Git diff for GitHub approval gates.")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()

    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    files = changed_files(repo_root, args.base_ref, args.head_ref)
    values = {
        "governance": str(any(is_protected_path(path) for path in files)).lower(),
        "has_changes": str(bool(files)).lower(),
    }
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
