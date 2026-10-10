"""Exercise release equivalence against real git history, not mocked diffs."""

import contextlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from deployment_guard import require_equivalent_preview


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        stack.callback(os.chdir, os.getcwd())
        os.chdir(directory)
        self.git("init")
        self.commit("src/app.py", "app = 1")
        self.preview = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "user.name=CI test",
                    "-c",
                    "user.email=ci@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    *args,
                ],
                stderr=subprocess.PIPE,
                timeout=10,
            )
            .decode()
            .strip()
        )

    def commit(self, name, text):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.git("add", name)
        self.git("commit", "-m", "fixture")

    def test_exact_commit_and_documentation_only_descendants_are_allowed(self):
        require_equivalent_preview(self.preview)
        self.commit("README.md", "new identity")
        self.commit("docs/release.md", "notes")
        self.commit("tests/test_new.py", "test")
        require_equivalent_preview(self.preview)

    def test_code_change_even_with_docs_blocks_production(self):
        self.commit("src/app.py", "app = 2")
        self.commit("README.md", "notes")
        with self.assertRaisesRegex(ValueError, "Application differs"):
            require_equivalent_preview(self.preview)

    def test_unknown_build_input_and_deleted_source_block_production(self):
        self.commit("new-build-input", "new")
        with self.assertRaises(ValueError):
            require_equivalent_preview(self.preview)
        self.git("reset", "--hard", self.preview)
        self.git("rm", "src/app.py")
        self.git("commit", "-m", "delete")
        with self.assertRaises(ValueError):
            require_equivalent_preview(self.preview)

    def test_missing_invalid_future_and_divergent_sha_are_rejected(self):
        for sha in ("", "--all", "f" * 40):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                require_equivalent_preview(sha)
        self.commit("README.md", "future")
        future = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.preview)
        with self.assertRaises(ValueError):
            require_equivalent_preview(future)
        self.commit("AGENTS.md", "other history")
        with self.assertRaises(ValueError):
            require_equivalent_preview(future)


if __name__ == "__main__":
    unittest.main()
