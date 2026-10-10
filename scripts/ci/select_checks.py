"""Route CI by changed paths; unknown surfaces deliberately run every check."""

import argparse
import subprocess

CHECKS = frozenset({"backend", "frontend", "transport", "preview"})
MAX_CHANGED_FILES = 10_000
GIT_TIMEOUT_SECONDS = 30
DOC_FILES = frozenset({"README.md", "AGENTS.md", "CLAUDE.md", "LICENSE"})
FRONTEND_TEST_CONFIGS = frozenset(
    {"frontend/playwright.config.ts", "frontend/vitest.config.ts"}
)


def select_checks(paths: list[str]) -> set[str]:
    if len(paths) > MAX_CHANGED_FILES:
        raise ValueError(f"CI diff exceeds {MAX_CHANGED_FILES} files")
    selected: set[str] = set()
    for path in paths:
        if path in DOC_FILES or path.startswith(("docs/", "openwiki/")):
            continue
        if path.startswith("src/"):
            selected.update(("backend", "preview"))
        elif path.startswith("tests/"):
            selected.add("backend")
        elif path.startswith("frontend/"):
            selected.add("frontend")
            # Test-only edits need the complete UI gate, but do not change the
            # deployed application and need no remote build or preview comment.
            if not (
                path.startswith("frontend/browser-tests/")
                or path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
                or path in FRONTEND_TEST_CONFIGS
            ):
                selected.add("preview")
        elif path.startswith("scripts/openwiki/"):
            selected.add("transport")
        else:
            # Build inputs, CI policy, dependencies and new directories must
            # never silently bypass verification because a mapping is missing.
            selected.update(CHECKS)
    return selected


def changed_paths(base: str) -> list[str]:
    result = subprocess.run(
        # Disabling rename detection includes both the old and new path, so
        # moving code into a docs directory still tests the deleted code.
        ["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD", "--"],
        check=True,
        stdout=subprocess.PIPE,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return result.stdout.decode("utf-8").split("\0")[:-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base")
    mode.add_argument("--all", action="store_true")
    args = parser.parse_args()
    selected = CHECKS if args.all else select_checks(changed_paths(args.base))
    for check in sorted(CHECKS):
        print(f"{check}={str(check in selected).lower()}")


if __name__ == "__main__":
    main()
