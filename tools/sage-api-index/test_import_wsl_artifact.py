#!/usr/bin/env python3
import argparse
import hashlib
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
                    json.dumps({
                        "expected": [], "covered": [], "missing": [],
                        "withoutSignature": [], "dynamic": [], "conflicts": [],
                        "expectedCount": 0, "coveredCount": 0, "coverageRatio": 1.0,
                        "isComplete": False, "diagnostics": [],
                    }),
                    encoding="utf-8",
                )
                index_path = Path(command[command.index("--output") + 1])
                raw_path = Path(command[command.index("--raw-output") + 1])
                index_path.write_text("{}", encoding="utf-8")
                raw_path.write_text("{}", encoding="utf-8")
                return mock.Mock(returncode=0, stdout='{"entries": 0, "diagnostics": 0, "coverage": 1.0, "missing": 0}\n', stderr="")

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

    def test_probe_only_writes_a_live_envelope_without_generator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe_json = root / "probe.json"
            args = importer.parser().parse_args([
                "--distro", "Ubuntu",
                "--conda", "/opt/conda/bin/conda",
                "--conda-env", "sage",
                "--probe-only",
                "--probe-json", str(probe_json),
                "--probe-timeout", "7",
            ])
            with mock.patch.object(importer, "probe_runtime", return_value=self.probe()) as probe_runtime:
                envelope = importer.run_probe_only(args)
            probe_runtime.assert_called_once_with(
                "Ubuntu", "/opt/conda/bin/conda", "sage", timeout=7.0
            )
            self.assertEqual(envelope["schema"], 1)
            self.assertEqual(envelope["mode"], "LIVE")
            self.assertEqual(envelope["distro"], "Ubuntu")
            self.assertEqual(envelope["conda"], "/opt/conda/bin/conda")
            self.assertEqual(envelope["env"], "sage")
            self.assertEqual(envelope["command"], importer.probe_command("Ubuntu", "/opt/conda/bin/conda", "sage"))
            self.assertEqual(envelope["probe"], self.probe())
            self.assertEqual(envelope["probeDigest"], importer.probe_digest(envelope))
            self.assertEqual(
                json.loads(probe_json.read_text(encoding="utf-8")),
                envelope,
            )

    def test_probe_replay_rejects_unbound_or_tampered_envelopes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe_json = root / "probe.json"
            envelope = importer.make_probe_envelope(
                "Ubuntu", "/opt/conda/bin/conda", "sage", self.probe()
            )
            probe_json.write_text(json.dumps(envelope), encoding="utf-8")
            for changes, expected in [
                ({"mode": "REPLAY"}, "mode"),
                ({"probeDigest": "0" * 64}, "digest"),
                ({"command": ["wsl"]}, "command"),
            ]:
                with self.subTest(changes=changes):
                    changed = json.loads(json.dumps(envelope))
                    changed.update(changes)
                    probe_json.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected):
                        importer.load_probe_replay(
                            probe_json, "Ubuntu", "/opt/conda/bin/conda", "sage"
                        )
            probe_json.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "distro"):
                importer.load_probe_replay(
                    probe_json, "Other", "/opt/conda/bin/conda", "sage"
                )
            with self.assertRaisesRegex(ValueError, "allow-probe-replay"):
                importer.resolve_probe(
                    argparse.Namespace(
                        distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                        probe_json=probe_json, allow_probe_replay=False,
                        probe_only=False, probe_timeout=7.0,
                    )
                )

    def test_parser_timeout_defaults_and_cli_overrides_are_stable(self):
        defaults = importer.parser().parse_args([
            "--probe-only", "--probe-json", "probe.json",
        ])
        self.assertEqual(defaults.probe_timeout, 900.0)
        self.assertEqual(defaults.generator_timeout, 900.0)
        overrides = importer.parser().parse_args([
            "--probe-only", "--probe-json", "probe.json",
            "--probe-timeout", "4.5", "--generator-timeout", "6.5",
        ])
        self.assertEqual(overrides.probe_timeout, 4.5)
        self.assertEqual(overrides.generator_timeout, 6.5)

    def test_generator_timeout_writes_receipt_and_main_returns_two(self):
        import subprocess

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(
                stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"],
                discovered=0, generated=0,
            )
            with (
                mock.patch.object(importer, "probe_runtime", return_value=self.probe()),
                mock.patch.object(
                    importer.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(["python", "generate.py"], 6.5),
                ) as run,
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                code = importer.main([
                    "--source-root", str(stubs),
                    "--generation-report", str(report),
                    "--output-dir", str(root / "out"),
                    "--generator-timeout", "6.5",
                ])
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(run.call_args.kwargs["timeout"], 6.5)
            receipt = json.loads((root / "out" / "artifact-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["generator"]["status"], "timeout")
            self.assertEqual(receipt["generator"]["timeoutSeconds"], 6.5)
            self.assertIsNone(receipt["generator"]["returncode"])

    def test_probe_timeout_is_passed_and_reported_stably(self):
        import subprocess

        with mock.patch.object(
            importer.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["wsl"], 3.5),
        ) as run:
            with self.assertRaisesRegex(ValueError, "timed out"):
                importer.probe_runtime("Ubuntu", "/opt/conda/bin/conda", "sage", timeout=3.5)
        self.assertEqual(run.call_args.kwargs["timeout"], 3.5)

    def expected_contract(self, stubs: Path, symbols: list[dict[str, str]]) -> dict[str, object]:
        probe = self.probe()
        metadata = importer.source_metadata(stubs, importer.source_files(stubs))
        contract = {
            "schemaVersion": 1,
            "artifactId": "wsl-ubuntu-sage-10.9-stubgen-0.8.3",
            "sageVersion": probe["sageVersion"],
            "pythonVersion": probe["pythonVersion"],
            "stubgen": {"name": "sage-pycharm-stubgen", "version": "0.8.3"},
            "provenance": {
                "kind": "STUBGEN",
                "generator": "sage-pycharm-stubgen/0.8.3",
                "source": "wsl:Ubuntu:/opt/conda/bin/conda:env=sage",
            },
            "probeDigest": "0" * 64,
            "treeDigest": metadata["treeDigest"],
            "symbols": symbols,
        }
        envelope = importer.make_probe_envelope("Ubuntu", "/opt/conda/bin/conda", "sage", probe)
        contract["probeDigest"] = envelope["probeDigest"]
        contract["expectedDigest"] = importer.expected_digest(contract)
        return contract

    def generator_fixture(self, command, *args, write_outputs=True, **kwargs):
        coverage_path = Path(command[command.index("--coverage-output") + 1])
        index_path = Path(command[command.index("--output") + 1])
        raw_path = Path(command[command.index("--raw-output") + 1])
        expected_symbols = []
        if "--expected" in command:
            expected_value = json.loads(Path(command[command.index("--expected") + 1]).read_text(encoding="utf-8"))
            expected_symbols = expected_value if isinstance(expected_value, list) else expected_value["symbols"]
        coverage = {
            "expected": expected_symbols,
            "covered": expected_symbols,
            "missing": [],
            "withoutSignature": [],
            "dynamic": [],
            "conflicts": [],
            "expectedCount": len(expected_symbols),
            "coveredCount": len(expected_symbols),
            "coverageRatio": 1.0,
            "isComplete": True,
            "diagnostics": [],
        }
        if write_outputs:
            coverage_path.parent.mkdir(parents=True, exist_ok=True)
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            index_path.write_text("{}", encoding="utf-8")
            raw_path.write_text("{}", encoding="utf-8")
        return mock.Mock(returncode=0, stdout='{"entries": 0, "diagnostics": 0, "coverage": 1.0, "missing": 0}\n', stderr="")

    def test_expected_contract_is_fail_closed_before_generator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"], discovered=0, generated=0)
            expected = root / "expected.json"
            expected.write_text(json.dumps({"schemaVersion": 1, "symbols": []}), encoding="utf-8")
            args = argparse.Namespace(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, output_dir=root / "out",
                expected=expected, generator=Path("generate.py"), python=Path(sys.executable),
                probe_only=False, probe_json=None, allow_probe_replay=False, probe_timeout=7.0, generator_timeout=7.0,
            )
            with mock.patch.object(importer, "probe_runtime", return_value=self.probe()), mock.patch.object(importer.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "expected contract"):
                    importer.run_import(args)
            run.assert_not_called()

    def test_expected_contract_rejects_binding_and_digest_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"], discovered=0, generated=0)
            symbols = [{"qualifiedName": "sage.arith.misc.factor", "kind": "FUNCTION"}]
            valid = self.expected_contract(stubs, symbols)
            for changes, expected_error in [
                ({"artifactId": "wrong-artifact"}, "artifactId"),
                ({"probeDigest": "0" * 64}, "probeDigest"),
                ({"treeDigest": "0" * 64}, "treeDigest"),
                ({"provenance": {**valid["provenance"], "kind": "FIXTURE"}}, "provenance kind"),
                ({"expectedDigest": "0" * 64}, "expectedDigest"),
            ]:
                with self.subTest(changes=changes):
                    candidate = json.loads(json.dumps(valid))
                    candidate.update(changes)
                    path = root / "expected-invalid.json"
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected_error):
                        importer.load_expected_contract(
                            path,
                            probe=self.probe(),
                            artifact_id="wsl-ubuntu-sage-10.9-stubgen-0.8.3",
                            tree_digest_value=importer.source_metadata(stubs, importer.source_files(stubs))["treeDigest"],
                            distro="Ubuntu",
                            conda="/opt/conda/bin/conda",
                            conda_env="sage",
                        )

    def test_expected_contract_digest_and_symbol_order_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            symbols = [
                {"qualifiedName": "sage.matrix.matrix2.Matrix", "kind": "CLASS"},
                {"qualifiedName": "sage.arith.misc.factor", "kind": "FUNCTION"},
            ]
            contract = self.expected_contract(stubs, symbols)
            path = root / "expected.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            loaded = importer.load_expected_contract(
                path,
                probe=self.probe(),
                artifact_id="wsl-ubuntu-sage-10.9-stubgen-0.8.3",
                tree_digest_value=contract["treeDigest"],
                distro="Ubuntu",
                conda="/opt/conda/bin/conda",
                conda_env="sage",
            )
            self.assertEqual(loaded["expectedDigest"], importer.expected_digest(loaded))
            self.assertEqual(loaded["symbols"], sorted(symbols, key=lambda item: (item["qualifiedName"], item["kind"])))

    def test_empty_expected_coverage_is_unscoped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"], discovered=0, generated=0)
            args = argparse.Namespace(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, output_dir=root / "out",
                expected=None, generator=Path("generate.py"), python=Path(sys.executable),
                probe_only=False, probe_json=None, allow_probe_replay=False, probe_timeout=7.0, generator_timeout=7.0,
            )
            with mock.patch.object(importer, "probe_runtime", return_value=self.probe()), mock.patch.object(importer.subprocess, "run", side_effect=self.generator_fixture):
                receipt = importer.run_import(args)
            self.assertEqual(receipt["coverage"], {
                "scope": "UNSCOPED", "expectedCount": 0, "coveredCount": 0, "missingCount": 0,
                "coverageRatio": None, "isComplete": False, "conflictCount": 0,
            })

    def test_nonempty_expected_coverage_is_scoped_and_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"], discovered=0, generated=0)
            symbols = [{"qualifiedName": "sage.arith.misc.factor", "kind": "FUNCTION"}]
            expected_path = root / "expected.json"
            expected_path.write_text(json.dumps(self.expected_contract(stubs, symbols)), encoding="utf-8")
            args = argparse.Namespace(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, output_dir=root / "out",
                expected=expected_path, generator=Path("generate.py"), python=Path(sys.executable),
                probe_only=False, probe_json=None, allow_probe_replay=False, probe_timeout=7.0, generator_timeout=7.0,
            )
            with mock.patch.object(importer, "probe_runtime", return_value=self.probe()), mock.patch.object(importer.subprocess, "run", side_effect=self.generator_fixture):
                receipt = importer.run_import(args)
            self.assertEqual(receipt["expected"]["count"], 1)
            self.assertEqual(receipt["coverage"]["scope"], "SCOPED")
            self.assertEqual(receipt["coverage"]["expectedCount"], 1)
            self.assertEqual(receipt["coverage"]["coveredCount"], 1)
            self.assertEqual(receipt["coverage"]["missingCount"], 0)
            self.assertEqual(receipt["coverage"]["coverageRatio"], 1.0)
            self.assertTrue(receipt["coverage"]["isComplete"])

    def test_zero_generator_returncode_with_missing_outputs_persists_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            stubs.mkdir()
            report = self.report(stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"], discovered=0, generated=0)
            output = root / "out"
            args = argparse.Namespace(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, output_dir=output,
                expected=None, generator=Path("generate.py"), python=Path(sys.executable),
                probe_only=False, probe_json=None, allow_probe_replay=False, probe_timeout=7.0, generator_timeout=7.0,
            )
            with mock.patch.object(importer, "probe_runtime", return_value=self.probe()), mock.patch.object(importer.subprocess, "run", return_value=mock.Mock(returncode=0, stdout='{"entries": 0, "diagnostics": 0, "coverage": 1.0, "missing": 0}\n', stderr="")):
                with self.assertRaisesRegex(ValueError, "post-generator"):
                    importer.run_import(args)
            receipt = json.loads((output / "artifact-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["generator"]["status"], "failed")
            self.assertEqual(receipt["generator"]["returncode"], 0)
            self.assertIn("error", receipt["generator"])

    def test_live_and_replay_receipts_record_probe_mode_and_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stubs = root / "stubs"
            (stubs / "sage").mkdir(parents=True)
            (stubs / "sage" / "__init__.pyi").write_text("def version() -> str: ...\n", encoding="utf-8")
            report = self.report(
                stubs, output_root=str(stubs), sage_package=self.probe()["sagePackage"],
                discovered=1, generated=1,
            )
            def fake_generator(command, **kwargs):
                coverage_path = Path(command[command.index("--coverage-output") + 1])
                coverage_path.parent.mkdir(parents=True, exist_ok=True)
                coverage_path.write_text(json.dumps({
                    "expected": [], "covered": [], "missing": [],
                    "withoutSignature": [], "dynamic": [], "conflicts": [],
                    "expectedCount": 0, "coveredCount": 0, "coverageRatio": 1.0,
                    "isComplete": False, "diagnostics": [],
                }), encoding="utf-8")
                Path(command[command.index("--output") + 1]).write_text("{}", encoding="utf-8")
                Path(command[command.index("--raw-output") + 1]).write_text("{}", encoding="utf-8")
                return mock.Mock(returncode=0, stdout='{"entries": 0, "diagnostics": 0, "coverage": 1.0, "missing": 0}\n', stderr="")
            base = dict(
                distro="Ubuntu", conda="/opt/conda/bin/conda", conda_env="sage",
                source_root=stubs, generation_report=report, expected=None,
                generator=Path("generate.py"), python=Path(sys.executable),
                probe_only=False, probe_json=None, allow_probe_replay=False, probe_timeout=7.0,
            )
            with (
                mock.patch.object(importer, "probe_runtime", return_value=self.probe()),
                mock.patch.object(importer.subprocess, "run", side_effect=fake_generator),
            ):
                live = importer.run_import(argparse.Namespace(output_dir=root / "live", **base))
            envelope = importer.make_probe_envelope(
                "Ubuntu", "/opt/conda/bin/conda", "sage", self.probe()
            )
            probe_json = root / "probe.json"
            probe_json.write_text(json.dumps(envelope), encoding="utf-8")
            replay_base = dict(base)
            replay_base.update(
                probe_json=probe_json, allow_probe_replay=True,
            )
            with mock.patch.object(importer.subprocess, "run", side_effect=fake_generator):
                replay = importer.run_import(argparse.Namespace(output_dir=root / "replay", **replay_base))
            self.assertEqual(live["probeMode"], "LIVE")
            self.assertEqual(replay["probeMode"], "REPLAY")
            self.assertEqual(live["probeDigest"], envelope["probeDigest"])
            self.assertEqual(replay["probeDigest"], envelope["probeDigest"])
            self.assertEqual(replay["probePath"], str(probe_json.resolve()))


if __name__ == "__main__":
    unittest.main()
