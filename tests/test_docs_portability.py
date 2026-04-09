from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "INSTALL.md",
]
ABSOLUTE_FILE_LINK_RE = re.compile(r"\]\(((?:/[A-Za-z0-9._-][^)]*)|(?:[A-Za-z]:[\\/][^)]*))\)")


class DocsPortabilityTest(unittest.TestCase):
    def test_docs_do_not_use_local_absolute_markdown_links(self) -> None:
        violations: list[str] = []
        for path in MARKDOWN_FILES:
            text = path.read_text(encoding="utf-8")
            for match in ABSOLUTE_FILE_LINK_RE.finditer(text):
                target = match.group(1)
                if target.startswith("//"):
                    continue
                violations.append(f"{path.name}: {target}")
        self.assertEqual(violations, [], "absolute local markdown links found: " + "; ".join(violations))


if __name__ == "__main__":
    unittest.main()
