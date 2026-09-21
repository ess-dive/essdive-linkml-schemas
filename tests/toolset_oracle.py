"""Expose the installed essdive-toolset validator to the conformance tests."""

import argparse
import json
from pathlib import Path

from essdive.validation import validate


def main() -> None:
    """Print canonical validation results or the canonical generated schema."""
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()

    results = {}
    for path in args.paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        results[path.name] = not bool(validate(data, test=True))
    print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
