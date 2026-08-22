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
            self.assertEqual(completed.returncode, 3, completed.stderr)
            self.assertIn("missing=1", completed.stderr)
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

    def test_checked_in_source_manifest_reproduces_fixture_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "index.json"
            result = subprocess.run([sys.executable, str(GENERATOR), "--source-manifest", str(ROOT / "source-manifest.json"), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(output), "--expected", str(ROOT / "expected-high-value.json"), "--allow-missing"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(index["sourceDigests"]["fixture-stubgen/10.6/sage/all.pyi"], index["entries"][0]["sources"][0]["digest"])
            self.assertEqual(len(index["entries"]), 45)

    def test_source_manifest_preserves_kinds_and_locators(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stub_root = root / "stub"
            runtime_root = root / "runtime"
            stub_root.mkdir()
            runtime_root.mkdir()
            (stub_root / "sage.pyi").write_text("def factory() -> Matrix: ...\n", encoding="utf-8")
            (runtime_root / "sage.pyi").write_text("class Matrix: ...\n", encoding="utf-8")
            manifest = root / "sources.json"
            manifest.write_text(json.dumps([
                {"root": str(stub_root), "kind": "STUB", "locator": "stubgen/v1"},
                {"root": str(runtime_root), "kind": "RUNTIME", "locator": "sage/10.6"},
            ]), encoding="utf-8")
            output = root / "index.json"
            result = subprocess.run([sys.executable, str(GENERATOR), "--source-manifest", str(manifest), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            sources = {source["kind"] for entry in index["entries"] for source in entry["sources"]}
            locators = {source["locator"] for entry in index["entries"] for source in entry["sources"]}
            self.assertIn("STUB", sources)
            self.assertIn("RUNTIME", sources)
            self.assertTrue(any(locator.startswith("stubgen/v1/") for locator in locators))
            self.assertTrue(any(locator.startswith("sage/10.6/") for locator in locators))

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
            self.assertEqual(completed.returncode, 3, completed.stderr)
            self.assertIn("conflicts=1", completed.stderr)
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

    def test_coverage_gate_fails_after_writing_auditable_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def present() -> Integer: ...\n", encoding="utf-8")
            expected = root / "expected.json"
            expected.write_text(json.dumps([{ "qualifiedName": "sage.present", "kind": "FUNCTION" }, { "qualifiedName": "sage.missing", "kind": "FUNCTION" }]), encoding="utf-8")
            output, report_path = root / "index.json", root / "coverage.json"
            result = self.run_generator(source, expected, output, report_path)
            self.assertEqual(result.returncode, 3)
            self.assertTrue(output.exists())
            self.assertTrue(report_path.exists())
            self.assertIn("missing=1", result.stderr)

    def test_min_coverage_gate_fails_even_when_missing_is_explicitly_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def present() -> Integer: ...\n", encoding="utf-8")
            expected = root / "expected.json"
            expected.write_text("[{\"qualifiedName\":\"sage.present\",\"kind\":\"FUNCTION\"},{\"qualifiedName\":\"sage.missing\",\"kind\":\"FUNCTION\"}]", encoding="utf-8")
            output, report_path = root / "index.json", root / "coverage.json"
            command = [sys.executable, str(GENERATOR), "--source-root", str(source), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(output), "--expected", str(expected), "--coverage-output", str(report_path), "--allow-missing", "--min-coverage", "1.0"]
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertIn("coverage=0.500000<min=1.000000", result.stderr)
            self.assertTrue(output.exists())
            self.assertTrue(report_path.exists())

    def test_allow_missing_can_produce_a_green_fixture_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def present() -> Integer: ...\n", encoding="utf-8")
            expected = root / "expected.json"
            expected.write_text("[{\"qualifiedName\":\"sage.present\",\"kind\":\"FUNCTION\"},{\"qualifiedName\":\"sage.missing\",\"kind\":\"FUNCTION\"}]", encoding="utf-8")
            output = root / "index.json"
            command = [sys.executable, str(GENERATOR), "--source-root", str(source), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(output), "--expected", str(expected), "--allow-missing", "--min-coverage", "0.5"]
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_empty_source_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.run([sys.executable, str(GENERATOR), "--source-root", str(root), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(root / "index.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("no .pyi/.py sources", result.stderr)

if __name__ == "__main__":
    unittest.main()