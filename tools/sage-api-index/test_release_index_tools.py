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
sys.path.insert(0, str(ROOT))
from apply_method_aliases import apply_aliases, discover_method_aliases


class ReleaseIndexToolsTest(unittest.TestCase):
    def test_source_proven_class_method_alias_copies_only_one_exact_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            stub_root = temporary_path / "stubs"
            stub = stub_root / "sage" / "curves" / "finite.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Curve:\n"
                "    def cardinality(self, algorithm=None) -> Integer: ...\n"
                "    order = cardinality\n",
                encoding="utf-8",
            )
            source = {
                "qualifiedName": "sage.curves.finite.Curve.cardinality",
                "kind": "METHOD",
                "dynamicity": "STATIC",
                "confidence": "HIGH",
                "parents": [],
                "protocols": [],
                "aliases": [],
                "sources": [{
                    "kind": "STUB",
                    "locator": "stubgen/10.9/sage/curves/finite.pyi:2",
                    "digest": "a" * 64,
                }],
                "signatures": [{
                    "parameters": [{"name": "algorithm", "optional": True}],
                    "returnType": {"state": "KNOWN", "expression": "sage.rings.integer.Integer"},
                }],
                "documentation": {"summary": "Cardinality", "body": "Exact contract", "examples": []},
            }
            index = {
                "schemaVersion": 1,
                "sageVersion": "10.9",
                "pythonVersion": "3.13",
                "entries": [source],
            }

            aliases = discover_method_aliases(stub_root)
            patched, summary = apply_aliases(index, aliases)

            self.assertEqual(1, summary["created"])
            copied = next(entry for entry in patched["entries"] if entry["qualifiedName"].endswith(".order"))
            self.assertEqual(source["signatures"], copied["signatures"])
            self.assertEqual(source["documentation"], copied["documentation"])
            self.assertEqual(["sage.curves.finite.Curve.cardinality"], copied["aliases"])
            self.assertEqual("stubgen/10.9/sage/curves/finite.pyi:3", copied["sources"][0]["locator"])

            _, rerun_summary = apply_aliases(patched, aliases)
            self.assertEqual(0, rerun_summary["created"])
            self.assertEqual(1, rerun_summary["alreadyPresent"])

    def test_method_alias_does_not_replace_an_existing_declaration(self) -> None:
        index = {
            "schemaVersion": 1,
            "sageVersion": "10.9",
            "pythonVersion": "3.13",
            "entries": [
                {"qualifiedName": "sage.Curve.cardinality", "kind": "METHOD", "signatures": []},
                {"qualifiedName": "sage.Curve.order", "kind": "METHOD", "signatures": [{"returnType": {"state": "UNKNOWN"}}]},
            ],
        }
        from apply_method_aliases import MethodAlias

        patched, summary = apply_aliases(index, [
            MethodAlias("sage.Curve.order", "sage.Curve.cardinality", "sage/curve.pyi", 3),
        ])
        self.assertEqual(2, len(patched["entries"]))
        self.assertEqual(0, summary["created"])
        self.assertEqual(1, summary["skippedConflict"])

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
