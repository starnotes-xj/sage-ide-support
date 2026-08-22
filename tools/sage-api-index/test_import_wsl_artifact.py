#!/usr/bin/env python3
import argparse
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_wsl_artifact as importer


class ImportWslArtifactTest(unittest.TestCase):
    def report(self, root: Path, **changes):
        data = {
            "sage_version": "10.9",
            "sage_package": "/opt/conda/envs/sage/lib/python3.13/site-packages/sage",
            "output_root": "/tmp/stubs",
            "python_version": "3.13.15",
            "stubgen": {"name": "sage-pycharm-stubgen", "version": "0.8.3"},
            "discovered": 2,
            "generated": 2,
            "failed": 0,
            "fallbacks": [],
            "failures": [],
        }
        data.update(changes)
        path = root / "generation-report.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def probe(self, **changes):
        value = {
            "sageVersion": "10.9",
            "pythonVersion": "3.13.15",
            "sagePackage": "/opt/conda/envs/sage/lib/python3.13/site-packages/sage",
            "stubgen": {"name": "sage-pycharm-stubgen", "version": "0.8.3", "license": "GPL-3.0-only"},
        }
        value.update(changes)
        return value

    def test_validate_report_rejects_failed_or_incomplete_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for changes, expected in [
                ({"failed": 1}, "failed must be zero"),
                ({"generated": 1}, "generated must equal discovered"),
                ({"sage_version": "10.8"}, "does not match runtime probe"),
            ]:
                with self.subTest(changes=changes):
                    report = json.loads(self.report(root, **changes).read_text(encoding="utf-8"))
                    with self.assertRaisesRegex(ValueError, expected):
                        importer.validate_generation_report(report, self.probe(), 2)

    def test_validate_report_rejects_missing_generated_stubs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = json.loads(self.report(root).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "stub file count"):
                importer.validate_generation_report(report, self.probe(), 1)

    def test_validate_report_accepts_additional_aggregate_stubs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = json.loads(self.report(root).read_text(encoding="utf-8"))
            importer.validate_generation_report(report, self.probe(), 3)

    def test_probe_runtime_decodes_wsl_output_as_utf8(self):
        output = json.dumps(self.probe(), ensure_ascii=False) + "\n"
        with mock.patch.object(importer.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=output, stderr="警告")
            self.assertEqual(
                importer.probe_runtime("Ubuntu", "/opt/conda/bin/conda", "sage"),
                self.probe(),
            )
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_build_artifacts_are_deterministic_and_use_stubgen_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            (stubs / "sage").mkdir(parents=True)
            (stubs / "sage" / "__init__.pyi").write_text("def version() -> str: ...\n", encoding="utf-8")
            report_path = self.report(
                stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"],
                discovered=1, generated=1,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            manifest_a, receipt_a = importer.build_artifacts(
                probe=self.probe(), report=report, source_root=stubs,
                report_path=report_path, distro="Ubuntu",
                conda="/opt/conda/bin/conda", conda_env="sage",
            )
            manifest_b, receipt_b = importer.build_artifacts(
                probe=self.probe(), report=report, source_root=stubs,
                report_path=report_path, distro="Ubuntu",
                conda="/opt/conda/bin/conda", conda_env="sage",
            )
            self.assertEqual(manifest_a, manifest_b)
            self.assertEqual(receipt_a, receipt_b)
            self.assertEqual(manifest_a["provenance"]["kind"], "STUBGEN")
            self.assertEqual(manifest_a["sageVersion"], "10.9")
            self.assertEqual(manifest_a["pythonVersion"], "3.13")
            self.assertEqual(manifest_a["sources"][0]["kind"], "STUBGEN")
            self.assertEqual(len(manifest_a["sources"][0]["treeDigest"]), 64)
            self.assertEqual(receipt_a["generationReport"]["failed"], 0)
            self.assertEqual(receipt_a["stubFileCount"], 1)

    def test_validate_report_rejects_source_and_runtime_package_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stubs"
            source.mkdir()
            probe = self.probe()
            report = json.loads(self.report(
                root,
                output_root=str(root / "other"),
                sage_package=probe["sagePackage"],
            ).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "output_root"):
                importer.validate_generation_report(report, probe, 2, source_root=source, distro="Ubuntu")

            report = json.loads(self.report(
                root,
                output_root=str(source),
                sage_package="/opt/other/site-packages/sage",
            ).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "sage_package"):
                importer.validate_generation_report(report, probe, 2, source_root=source, distro="Ubuntu")

    def test_validate_report_binds_optional_python_and_stubgen_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe = self.probe()
            for changes, expected in [
                ({"python_version": "3.12.0"}, "Python version"),
                ({"stubgen": {"name": "sage-pycharm-stubgen", "version": "0.8.2"}}, "stubgen version"),
                ({"stubgen": {"name": "other-generator", "version": "0.8.3"}}, "stubgen name"),
            ]:
                with self.subTest(changes=changes):
                    report = json.loads(self.report(root, **changes).read_text(encoding="utf-8"))
                    with self.assertRaisesRegex(ValueError, expected):
                        importer.validate_generation_report(report, probe, 2)

    def test_probe_schema_rejects_malformed_stubgen_and_missing_package(self):
        for changes, expected in [
            ({"stubgen": None}, "stubgen must be an object"),
            ({"stubgen": {"name": "", "version": "0.8.3"}}, "stubgen.name"),
            ({"stubgen": {"name": "sage-pycharm-stubgen", "version": 803}}, "stubgen.version"),
            ({"sagePackage": ""}, "sagePackage"),
        ]:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, expected):
                    importer.validate_probe(self.probe(**changes))

    def test_generator_failure_uses_utf8_and_is_stable_for_non_ascii_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(
                stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"],
                discovered=0, generated=0,
            )
            args = argparse.Namespace(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, output_dir=root / "out",
                expected=None, generator=Path("generate.py"), python=Path(sys.executable),
            )
            with (
                mock.patch.object(importer, "probe_runtime", return_value=self.probe()),
                mock.patch.object(importer.subprocess, "run") as run,
            ):
                run.return_value = mock.Mock(returncode=1, stdout="", stderr="生成失败")
                with self.assertRaisesRegex(ValueError, "生成失败"):
                    importer.run_import(args)
            self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
            self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_main_returns_exit_two_without_traceback_for_malformed_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(
                stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"],
                discovered=0, generated=0,
            )
            with (
                mock.patch.object(importer, "probe_runtime", return_value=self.probe(stubgen=None)),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                code = importer.main([
                    "--source-root", str(stubs),
                    "--generation-report", str(report),
                    "--output-dir", str(root / "out"),
                ])
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_probe_command_is_explicit_and_noninteractive(self):
        command = importer.probe_command("Ubuntu", "/opt/conda/bin/conda", "sage")
        self.assertEqual(command[:5], ["wsl", "-d", "Ubuntu", "--", "/opt/conda/bin/conda"])
        self.assertEqual(command[5:9], ["run", "-n", "sage", "python"])
        self.assertNotIn("activate", command)

    def test_run_import_writes_receipt_manifest_and_invokes_generator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            (stubs / "sage").mkdir(parents=True)
            (stubs / "sage" / "__init__.pyi").write_text("def version() -> str: ...\n", encoding="utf-8")
            report = self.report(
                stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"],
                discovered=1, generated=1,
            )
            output = root / "out"
            args = argparse.Namespace(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, output_dir=output,
                expected=None, generator=Path("generate.py"), python=Path(sys.executable),
            )
            def fake_generator(command, **kwargs):
                coverage_path = Path(command[command.index("--coverage-output") + 1])
                coverage_path.parent.mkdir(parents=True, exist_ok=True)
                coverage_path.write_text(
                    json.dumps({"diagnostics": [], "conflicts": []}),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="{}\n", stderr="")

            with (
                mock.patch.object(importer, "probe_runtime", return_value=self.probe()),
                mock.patch.object(importer.subprocess, "run", side_effect=fake_generator) as run,
            ):
                importer.run_import(args)
            manifest = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
            receipt = json.loads((output / "artifact-receipt.json").read_text(encoding="utf-8"))
            source = manifest["sources"][0]
            self.assertEqual(manifest["provenance"]["kind"], "STUBGEN")
            self.assertEqual(receipt["runtime"]["sageVersion"], "10.9")
            self.assertEqual(receipt["sourceRoot"], source["root"])
            self.assertEqual(receipt["treeDigest"], source["treeDigest"])
            self.assertEqual(receipt["sourceFileCount"], source["fileCount"])
            self.assertEqual(receipt["stubFileCount"], 1)
            self.assertEqual(receipt["provenance"], manifest["provenance"])
            self.assertEqual(receipt["generator"]["diagnostics"]["count"], 0)
            command = run.call_args.args[0]
            self.assertIn("--source-manifest", command)
            self.assertIn("--source-base", command)
            self.assertIn("--coverage-output", command)
            self.assertNotIn("--diagnostics-output", command)


if __name__ == "__main__":
    unittest.main()
