#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import validate_index, validate_source_contract

ROOT = Path(__file__).resolve().parent
GENERATOR = ROOT / "generate.py"

class ManifestContractTest(unittest.TestCase):
    def test_manifest_index_source_metadata_contract_rejects_locator_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest.write_text(json.dumps({
                "artifactId": "fixture-contract-consistency",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"},
                "sources": [{"root": "stubs", "kind": "FIXTURE", "locator": "fixture-contract-consistency/10.6"}],
            }), encoding="utf-8")
            command = [
                sys.executable, str(GENERATOR), "--source-manifest", str(manifest),
                "--source-base", str(root), "--sage-version", "10.6", "--python-version", "3.11",
                "--output", str(output), "--expected", str(ROOT / "expected-high-value.json"), "--allow-missing",
            ]
            generated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            source_metadata = index["sources"][0]
            self.assertEqual(source_metadata["kind"], "FIXTURE")
            self.assertEqual(source_metadata["locator"], "fixture-contract-consistency/10.6")
            self.assertEqual(source_metadata["fileCount"], len(source_metadata["files"]))
            self.assertEqual(index["sourceDigests"], {source["locator"].split(":")[0]: source["digest"] for entry in index["entries"] for source in entry["sources"]})

            drifted = dict(index)
            drifted["sources"] = [dict(source_metadata, locator="wrong-locator")]
            metadata = {"sourceSpecs": [{"kind": "FIXTURE", "extractorKind": "STUB", "locator": "fixture-contract-consistency/10.6", "treeDigest": source_metadata["treeDigest"]}]}
            with self.assertRaisesRegex(ValueError, "source 0 locator"):
                validate_source_contract(drifted, metadata)

    def test_manifest_index_source_metadata_contract_rejects_missing_entry_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            (root / "empty").mkdir()
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest.write_text(json.dumps({
                "artifactId": "fixture-contract-missing-source",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"},
                "sources": [
                    {"root": "stubs", "kind": "FIXTURE", "locator": "fixture-contract-missing-source/10.6"},
                    {"root": "empty", "kind": "FIXTURE", "locator": "fixture-contract-missing-source/empty"},
                ],
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(GENERATOR), "--source-manifest", str(manifest),
                "--source-base", str(root), "--sage-version", "10.6", "--python-version", "3.11",
                "--output", str(output), "--allow-missing",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("source manifest entry 1 has no extracted", result.stderr)

    def test_manifest_index_source_metadata_contract_rejects_metadata_drift(self):
        digest = "a" * 64
        metadata = {"sourceSpecs": [{
            "kind": "FIXTURE",
            "extractorKind": "STUB",
            "locator": "fixture-contract/10.6",
            "treeDigest": digest,
            "fileCount": 1,
            "files": ["sage.pyi"],
        }]}
        entry = {
            "qualifiedName": "sage",
            "kind": "MODULE",
            "dynamicity": "STATIC",
            "confidence": "HIGH",
            "parents": [],
            "protocols": [],
            "aliases": [],
            "sources": [{"kind": "STUB", "locator": "fixture-contract/10.6/sage.pyi", "digest": digest}],
            "signatures": [],
        }
        base = {
            "sources": [{
                "kind": "FIXTURE",
                "locator": "fixture-contract/10.6",
                "treeDigest": digest,
                "fileCount": 1,
                "files": ["fixture-contract/10.6/sage.pyi"],
            }],
            "sourceDigests": {"fixture-contract/10.6/sage.pyi": digest},
            "entries": [entry],
        }
        validate_source_contract(base, metadata)
        cases = [
            ({**base, "sources": [{**base["sources"][0], "fileCount": 2}]}, "file metadata"),
            ({**base, "sources": [{**base["sources"][0], "files": ["fixture-contract/10.6/other.pyi"]}]}, "file metadata"),
            ({**base, "sources": [{**base["sources"][0], "treeDigest": "b" * 64}]}, "treeDigest"),
            ({**base, "sourceDigests": {}}, "source digests"),
            ({
                **base,
                "entries": [entry, {**entry, "qualifiedName": "rogue", "sources": [{"kind": "STUB", "locator": "rogue/sage.pyi", "digest": digest}]}],
                "sourceDigests": {**base["sourceDigests"], "rogue/sage.pyi": digest},
            }, "does not belong to a manifest source"),
            ({
                **base,
                "entries": [entry, {**entry, "qualifiedName": "phantom", "sources": [{"kind": "STUB", "locator": "fixture-contract/10.6/phantom.pyi", "digest": digest}]}],
                "sourceDigests": {**base["sourceDigests"], "fixture-contract/10.6/phantom.pyi": digest},
            }, "does not match a scanned source file"),
        ]
        for index, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_source_contract(index, metadata)

    def test_manifest_index_source_metadata_contract_rejects_duplicate_locator(self):
        source = {
            "kind": "FIXTURE",
            "extractorKind": "STUB",
            "locator": "duplicate",
            "treeDigest": "a" * 64,
            "fileCount": 0,
            "files": [],
        }
        with self.assertRaisesRegex(ValueError, "locators must be unique"):
            validate_source_contract({"sources": [{}, {}], "entries": [], "sourceDigests": {}}, {"sourceSpecs": [source, dict(source)]})

    def test_manifest_index_source_metadata_contract_preserves_multiple_source_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_a = root / "stubs-a"
            source_b = root / "stubs-b"
            shutil.copytree(ROOT / "fixtures" / "sage" / "matrix", source_a / "sage" / "matrix")
            shutil.copytree(ROOT / "fixtures" / "sage" / "modules", source_b / "sage" / "modules")
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest.write_text(json.dumps({
                "artifactId": "fixture-multi-source",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"},
                "sources": [
                    {"root": "stubs-b", "kind": "FIXTURE", "locator": "fixture-multi-source/b"},
                    {"root": "stubs-a", "kind": "FIXTURE", "locator": "fixture-multi-source/a"},
                ],
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(GENERATOR), "--source-manifest", str(manifest),
                "--source-base", str(root), "--sage-version", "10.6", "--python-version", "3.11",
                "--output", str(output), "--allow-missing",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([source["locator"] for source in index["sources"]], ["fixture-multi-source/b", "fixture-multi-source/a"])
            self.assertEqual(index["sources"][0]["fileCount"], len(index["sources"][0]["files"]))
            self.assertEqual(index["sources"][1]["fileCount"], len(index["sources"][1]["files"]))
            second_output = root / "index-second.json"
            second_command = [
                sys.executable, str(GENERATOR), "--source-manifest", str(manifest),
                "--source-base", str(root), "--sage-version", "10.6", "--python-version", "3.11",
                "--output", str(second_output), "--allow-missing",
            ]
            second = subprocess.run(second_command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_bytes(), second_output.read_bytes())

    def test_manifest_contract_accepts_stubgen_source_without_downgrading_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            (source / "sage.pyi").write_text("def version() -> str: ...\n", encoding="utf-8")
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest.write_text(json.dumps({
                "artifactId": "stubgen-real-contract",
                "sageVersion": "10.9",
                "pythonVersion": "3.13",
                "provenance": {"kind": "STUBGEN", "generator": "sage-pycharm-stubgen/0.8.3", "source": "wsl:Ubuntu"},
                "sources": [{"root": "stubs", "kind": "STUBGEN", "locator": "sage-pycharm-stubgen/10.9"}],
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(GENERATOR), "--source-manifest", str(manifest),
                "--source-base", str(root), "--sage-version", "10.9", "--python-version", "3.13",
                "--output", str(output), "--allow-missing",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(index["sources"][0]["kind"], "STUBGEN")
            self.assertTrue(all(source["kind"] == "STUB" for entry in index["entries"] for source in entry["sources"]))

    def test_manifest_contract_requires_identity_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest.write_text(json.dumps({
                "artifactId": "fixture-contract",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test", "source": "test"},
                "sources": [{"root": "missing-stubs", "kind": "FIXTURE", "locator": "fixture-contract/10.6"}],
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(GENERATOR),
                "--source-manifest", str(manifest),
                "--sage-version", "10.6",
                "--python-version", "3.11",
                "--output", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("source manifest root does not exist", result.stderr)

    def test_manifest_contract_preserves_provenance_and_source_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            manifest = root / "manifest.json"
            output = root / "index.json"
            coverage = root / "coverage.json"
            manifest.write_text(json.dumps({
                "artifactId": "fixture-contract",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"},
                "sources": [{"root": "stubs", "kind": "FIXTURE", "locator": "fixture-contract/10.6"}],
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(GENERATOR),
                "--source-manifest", str(manifest),
                "--source-base", str(root),
                "--sage-version", "10.6",
                "--python-version", "3.11",
                "--output", str(output),
                "--coverage-output", str(coverage),
                "--expected", str(ROOT / "expected-high-value.json"),
                "--allow-missing",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(index["artifactId"], "fixture-contract")
            self.assertEqual(index["sageVersion"], "10.6")
            self.assertEqual(index["pythonVersion"], "3.11")
            self.assertEqual(index["provenance"], {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"})
            self.assertEqual(index["sourceManifest"], "manifest.json")
            self.assertEqual(index["sources"][0]["kind"], "FIXTURE")
            self.assertEqual(index["sources"][0]["locator"], "fixture-contract/10.6")
            self.assertTrue(index["sources"][0]["files"])
            self.assertTrue(index["sourceDigests"])
            names = {(entry["qualifiedName"], entry["kind"]): entry for entry in index["entries"]}
            self.assertIn(("sage.matrix.matrix.Matrix.solve_right", "METHOD"), names)
            factory = names[("sage.matrix.matrix.matrix", "FUNCTION")]
            self.assertEqual(factory["signatures"][0]["returnType"], {"state": "KNOWN", "expression": "sage.matrix.matrix.Matrix"})
            self.assertTrue(all(source["digest"] for entry in index["entries"] for source in entry["sources"]))

    def test_manifest_tree_digest_is_stable_and_rejects_content_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest_data = {
                "artifactId": "fixture-tree-digest",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"},
                "sources": [{"root": "stubs", "kind": "FIXTURE", "locator": "fixture-tree-digest/10.6"}],
            }
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            command = [
                sys.executable, str(GENERATOR),
                "--source-manifest", str(manifest),
                "--source-base", str(root),
                "--sage-version", "10.6",
                "--python-version", "3.11",
                "--output", str(output),
                "--expected", str(ROOT / "expected-high-value.json"),
                "--allow-missing",
            ]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_index = json.loads(output.read_text(encoding="utf-8"))
            source_metadata = first_index["sources"][0]
            self.assertEqual(source_metadata["fileCount"], len(source_metadata["files"]))
            self.assertTrue(source_metadata["treeDigest"])

            manifest_data["sources"][0]["treeDigest"] = source_metadata["treeDigest"]
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            second_index = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(second_index["sources"][0]["treeDigest"], source_metadata["treeDigest"])

            target = next(source.glob("**/*.pyi"))
            target.write_text(target.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
            drifted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(drifted.returncode, 2)
            self.assertIn("tree digest mismatch", drifted.stderr)

    def test_manifest_tree_digest_rejects_file_set_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            manifest = root / "manifest.json"
            output = root / "index.json"
            manifest_data = {
                "artifactId": "fixture-file-set",
                "sageVersion": "10.6",
                "pythonVersion": "3.11",
                "provenance": {"kind": "FIXTURE", "generator": "test_generate", "source": "checked-in"},
                "sources": [{"root": "stubs", "kind": "FIXTURE", "locator": "fixture-file-set/10.6"}],
            }
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            command = [
                sys.executable, str(GENERATOR),
                "--source-manifest", str(manifest),
                "--source-base", str(root),
                "--sage-version", "10.6",
                "--python-version", "3.11",
                "--output", str(output),
                "--allow-missing",
            ]
            initial = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(initial.returncode, 0, initial.stderr)
            generated = json.loads(output.read_text(encoding="utf-8"))
            manifest_data["sources"][0]["treeDigest"] = generated["sources"][0]["treeDigest"]
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            (source / "sage" / "added.pyi").write_text("def added() -> int: ...\n", encoding="utf-8")
            drifted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(drifted.returncode, 2)
            self.assertIn("tree digest mismatch", drifted.stderr)

    def test_manifest_provenance_rejects_unknown_or_incomplete_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            shutil.copytree(ROOT / "fixtures" / "sage", source / "sage")
            cases = [
                ({"kind": "NOT_A_REAL_SOURCE", "generator": "test", "source": "checked-in"}, "provenance.kind"),
                ({"kind": "FIXTURE", "generator": "", "source": "checked-in"}, "provenance.generator"),
                ({"kind": "FIXTURE", "generator": "test", "source": ""}, "provenance.source"),
            ]
            for provenance, expected_error in cases:
                with self.subTest(provenance=provenance):
                    manifest = root / "manifest.json"
                    manifest.write_text(json.dumps({
                        "artifactId": "fixture-provenance",
                        "sageVersion": "10.6",
                        "pythonVersion": "3.11",
                        "provenance": provenance,
                        "sources": [{"root": "stubs", "kind": "FIXTURE", "locator": "fixture-provenance/10.6"}],
                    }), encoding="utf-8")
                    result = subprocess.run([
                        sys.executable, str(GENERATOR),
                        "--source-manifest", str(manifest),
                        "--source-base", str(root),
                        "--sage-version", "10.6",
                        "--python-version", "3.11",
                        "--output", str(root / "index.json"),
                    ], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(expected_error, result.stderr)

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
            conflict = report["conflicts"][0]
            self.assertEqual(conflict["sourceDigest"], factory["sources"][0]["digest"])
            self.assertEqual(conflict["declarationCount"], 2)
            self.assertEqual(conflict["distinctSignatureCount"], 2)
            self.assertEqual(len(conflict["signatureKeys"]), 2)
            self.assertEqual(conflict["signatureKeys"], sorted(conflict["signatureKeys"]))

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

    def test_checked_in_bundled_index_matches_generator_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "generated.json"
            coverage = root / "coverage.json"
            result = subprocess.run([
                sys.executable,
                str(GENERATOR),
                "--source-manifest",
                str(ROOT / "source-manifest.json"),
                "--sage-version",
                "10.6",
                "--python-version",
                "3.11",
                "--output",
                str(output),
                "--coverage-output",
                str(coverage),
                "--expected",
                str(ROOT / "expected-high-value.json"),
                "--allow-missing",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            generated = json.loads(output.read_text(encoding="utf-8"))
            bundled_path = ROOT.parent.parent / "plugins" / "sage-core" / "src" / "main" / "resources" / "sage-api-index.json"
            bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
            self.assertEqual(generated["entries"], bundled["entries"])
            self.assertEqual(generated["sourceDigests"], bundled["sourceDigests"])
            self.assertEqual(generated["sageVersion"], bundled["sageVersion"])
            self.assertEqual(generated["pythonVersion"], bundled["pythonVersion"])
            self.assertEqual(generated["generatorVersion"], bundled["generatorVersion"])
            report = json.loads(coverage.read_text(encoding="utf-8"))
            self.assertEqual(report["coveredCount"], 15)
            self.assertEqual(report["coverageRatio"], 0.9375)
            self.assertEqual(report["missing"], [{"qualifiedName": "sage.all.missing", "kind": "FUNCTION"}])
            validate_index(bundled)
            duplicate = dict(bundled)
            duplicate["entries"] = bundled["entries"] + [bundled["entries"][0]]
            with self.assertRaisesRegex(ValueError, "duplicate entry"):
                validate_index(duplicate)
            damaged = dict(bundled)
            damaged_entry = dict(bundled["entries"][0])
            damaged_entry["kind"] = "CORRUPTED"
            damaged["entries"] = [damaged_entry] + bundled["entries"][1:]
            with self.assertRaisesRegex(ValueError, "known Sage symbol kind"):
                validate_index(damaged)

            entries = {(entry["qualifiedName"], entry["kind"]): entry for entry in bundled["entries"]}
            self.assertIn(("sage.matrix.matrix.matrix", "FUNCTION"), entries)
            self.assertIn(("sage.matrix.matrix.Matrix", "CLASS"), entries)
            self.assertIn(("sage.matrix.matrix.Matrix.solve_right", "METHOD"), entries)
            self.assertIn("sage.all.matrix", entries[("sage.matrix.matrix.matrix", "FUNCTION")]["aliases"])
            self.assertEqual(
                entries[("sage.matrix.matrix.matrix", "FUNCTION")]["signatures"][0]["returnType"],
                {"state": "KNOWN", "expression": "sage.matrix.matrix.Matrix"},
            )
            self.assertTrue(bundled["generatorVersion"])
            self.assertTrue(bundled["sourceDigests"])
            self.assertTrue(all(entry["sources"] for entry in bundled["entries"]))
            self.assertTrue(any(entry.get("documentation") for entry in bundled["entries"]))
            self.assertTrue(any(source.get("digest") for entry in bundled["entries"] for source in entry["sources"]))

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

    def test_annotated_class_property_does_not_request_an_ast_docstring(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "module.pyi").write_text(
                "class Holder:\n    value: int\n",
                encoding="utf-8",
            )
            result = subprocess.run([
                sys.executable, str(GENERATOR), "--source-root", str(root),
                "--sage-version", "10.9", "--python-version", "3.13",
                "--output", str(root / "index.json"), "--allow-missing",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads((root / "index.json").read_text(encoding="utf-8"))
            self.assertTrue(any(entry["qualifiedName"] == "module.Holder.value" for entry in index["entries"]))

    def test_rejects_empty_source_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.run([sys.executable, str(GENERATOR), "--source-root", str(root), "--sage-version", "10.6", "--python-version", "3.11", "--output", str(root / "index.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("no .pyi/.py sources", result.stderr)

if __name__ == "__main__":
    unittest.main()