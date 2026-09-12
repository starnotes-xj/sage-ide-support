from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SANITIZER = ROOT / "sanitize_release_index.py"
VALIDATOR = ROOT / "validate_release_index.py"


class ReleaseIndexToolsTest(unittest.TestCase):
    def test_sanitizer_keeps_sage_relative_path_and_validator_accepts_result(self) -> None:
        source = {
            "schemaVersion": 1,
            "sageVersion": "10.9",
            "pythonVersion": "3.13",
            "entries": [{
                "body": (
                    "File: /home/conda/build/sage/structure/element.pyx\n"
                    "Reference: https://example.org/work/portable-proof\n"
                    "Generic element."
                ),
            }],
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            raw = temporary_path / "raw.json"
            release = temporary_path / "release.json"
            raw.write_text(json.dumps(source), encoding="utf-8")

            subprocess.run(
                [sys.executable, str(SANITIZER), "--input", str(raw), "--output", str(release)],
                check=True,
                capture_output=True,
                text=True,
            )
            sanitized = json.loads(release.read_text(encoding="utf-8"))
            self.assertEqual(
                sanitized["entries"][0]["body"],
                (
                    "File: sage/structure/element.pyx\n"
                    "Reference: https://example.org/work/portable-proof\n"
                    "Generic element."
                ),
            )
            digest = hashlib.sha256(release.read_bytes()).hexdigest()
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--index",
                    str(release),
                    "--sha256",
                    digest,
                    "--minimum-bytes",
                    "1",
                    "--minimum-entries",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn(digest, result.stdout)

    def test_sanitizer_redacts_non_file_host_path(self) -> None:
        source = {
            "schemaVersion": 1,
            "sageVersion": "10.9",
            "pythonVersion": "3.13",
            "entries": [{"body": "A builder path /home/conda/private-note remains."}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            raw = temporary_path / "raw.json"
            release = temporary_path / "release.json"
            raw.write_text(json.dumps(source), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SANITIZER), "--input", str(raw), "--output", str(release)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            sanitized = json.loads(release.read_text(encoding="utf-8"))
            self.assertEqual(
                sanitized["entries"][0]["body"],
                "A builder path <redacted builder path> remains.",
            )


if __name__ == "__main__":
    unittest.main()
