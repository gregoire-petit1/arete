"""Allow promotion across non-deployable commits, never across untested app code."""

import argparse
import re
import subprocess

from select_checks import changed_paths, git_output, select_checks


def require_equivalent_preview(serving: str) -> None:
    # Treat provider metadata as data, not a git option or arbitrary revision.
    if not re.fullmatch(r"[0-9a-f]{40}", serving):
        raise ValueError(
            "Preview has no valid commit SHA; deploy a tagged preview first"
        )
    try:
        git_output("merge-base", "--is-ancestor", serving, "HEAD")
    except subprocess.CalledProcessError as error:
        raise ValueError(
            "Preview commit is missing or is not an ancestor of this release"
        ) from error
    paths = changed_paths(serving)
    if "preview" in select_checks(paths):
        raise ValueError(
            "Application differs from the healthy preview; wait for or fix Deploy preview"
        )
    print(f"Preview {serving} covers this release: no deployable input differs.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-sha", required=True)
    args = parser.parse_args()
    require_equivalent_preview(args.preview_sha)


if __name__ == "__main__":
    main()
