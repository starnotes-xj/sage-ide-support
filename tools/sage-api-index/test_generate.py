#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATOR = ROOT / "generate.py"

class GeneratorTest(unittest.TestCase):
    def run_generator(self, source, expected, output, coverage, previous=None, diff=None):
        command = [sys.executable, str(GENERATOR), "--source-root", str(source), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(output), "--expected", str(expected), "--coverage-output", str(coverage)]
        if previous is not None:
            command.extend(["--previous", str(previous), "--diff-output", str(diff)])
        return subprocess.run(command, check=False, capture_output=True, text=True)

    def test_extracts_high_value_domains_and_reports_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            module = source / "sage" / "all.pyi"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            module = source / "sage" / "all.pyi"
            expected = root / "expected.json"
            expected.write_text((ROOT / "expected-high-value.json").read_text(encoding="utf-8"), encoding="utf-8")
            output, report_path = root / "index.json", root / "coverage.json"
            completed = self.run_generator(source, expected, output, report_path)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(index["schemaVersion"], 1)
            self.assertEqual(index["sageVersion"], "10.6")
            names = {(entry["qualifiedName"], entry["kind"]) for entry in index["entries"]}
            matrix_factory = next(entry for entry in index["entries"] if entry["qualifiedName"] == "sage.matrix.matrix.matrix")
            self.assertIn("sage.all.matrix", matrix_factory["aliases"])
            self.assertIn(("sage.matrix.matrix.Matrix.solve_right", "METHOD"), names)
            finite_field_factory = next(entry for entry in index["entries"] if entry["qualifiedName"] == "sage.rings.finite_rings.finite_field_base.GF")
            self.assertIn("sage.all.GF", finite_field_factory["aliases"])
            self.assertEqual(report["missing"], [{"qualifiedName": "sage.all.missing", "kind": "FUNCTION"}])
            self.assertEqual(report["expectedCount"], 16)
            self.assertEqual(report["coveredCount"], 15)
            self.assertEqual(report["coverageRatio"], 0.9375)
            dynamic = next(entry for entry in index["entries"] if entry["qualifiedName"] == "sage.all.dynamic_factory")
            self.assertEqual(dynamic["signatures"][0]["returnType"]["state"], "UNKNOWN")
            self.assertTrue(index["sourceDigests"])

    def test_detects_conflicting_overloads_as_dynamic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def factory(value: Integer) -> Matrix: ...\ndef factory(value: Integer) -> Vector: ...\n", encoding="utf-8")
            expected = root / "expected.json"
            expected.write_text("[{\"qualifiedName\":\"sage.factory\",\"kind\":\"FUNCTION\"}]", encoding="utf-8")
            output, report_path = root / "index.json", root / "coverage.json"
            completed = self.run_generator(source, expected, output, report_path)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            factory = next(entry for entry in index["entries"] if entry["qualifiedName"] == "sage.factory")
            self.assertEqual(factory["dynamicity"], "DYNAMIC")
            self.assertEqual(factory["signatures"][0]["returnType"]["state"], "DYNAMIC")
            self.assertEqual(len(report["conflicts"]), 1)

    def test_diff_reports_added_removed_and_changed_symbols(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def old() -> Integer: ...\ndef changed() -> Integer: ...\n", encoding="utf-8")
            expected = root / "expected.json"
            expected.write_text("[]", encoding="utf-8")
            first, first_report = root / "first.json", root / "first-coverage.json"
            self.assertEqual(self.run_generator(source, expected, first, first_report).returncode, 0)
            (source / "sage.pyi").write_text("def changed() -> Matrix: ...\ndef added() -> Vector: ...\n", encoding="utf-8")
            second, second_report, diff = root / "second.json", root / "second-coverage.json", root / "diff.json"
            self.assertEqual(self.run_generator(source, expected, second, second_report, first, diff).returncode, 0)
            result = json.loads(diff.read_text(encoding="utf-8"))
            self.assertIn({"qualifiedName": "sage.added", "kind": "FUNCTION"}, result["added"])
            self.assertIn({"qualifiedName": "sage.old", "kind": "FUNCTION"}, result["removed"])
            self.assertIn({"qualifiedName": "sage.changed", "kind": "FUNCTION"}, result["changed"])

    def test_rejects_malformed_generated_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def broken(: ...\n", encoding="utf-8")
            output = root / "index.json"
            completed = self.run_generator(source, root / "expected.json", output, root / "coverage.json")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("invalid syntax", completed.stderr)
            self.assertFalse(output.exists())

    def test_rejects_empty_source_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.run([sys.executable, str(GENERATOR), "--source-root", str(root), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(root / "index.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("no .pyi/.py sources", result.stderr)

if __name__ == "__main__":
    unittest.main()