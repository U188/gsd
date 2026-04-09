from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "pm" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pm_config


class RelativeRepoRootConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._active_config = dict(pm_config.ACTIVE_CONFIG)

    def tearDown(self) -> None:
        pm_config.ACTIVE_CONFIG.clear()
        pm_config.ACTIVE_CONFIG.update(self._active_config)

    def test_relative_repo_root_is_resolved_from_config_file_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "portable-kit"
            repo_root.mkdir()
            config_path = repo_root / "pm.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"name": "demo"},
                        "repo_root": ".",
                        "task": {"backend": "local"},
                        "doc": {"backend": "repo"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            loaded = pm_config.load_config(str(config_path))
            pm_config.ACTIVE_CONFIG.clear()
            pm_config.ACTIVE_CONFIG.update(loaded)

            self.assertEqual(pm_config.project_root_path(), repo_root.resolve())


if __name__ == "__main__":
    unittest.main()
