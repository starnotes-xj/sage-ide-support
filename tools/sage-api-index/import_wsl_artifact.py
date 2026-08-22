#!/usr/bin/env python3
"""Import an auditable Sage stubgen artifact from an explicit WSL Conda environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix in {".pyi", ".py"}),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def source_metadata(root: Path, paths: list[Path]) -> dict[str, Any]:
    files = [
        {"path": path.relative_to(root).as_posix(), "digest": sha256(path)}
        for path in paths
    ]
    files.sort(key=lambda item: item["path"])
    payload = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return {
        "fileCount": len(files),
        "files": [item["path"] for item in files],
        "treeDigest": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def tree_digest(root: Path, paths: list[Path]) -> str:
    return source_metadata(root, paths)["treeDigest"]


def probe_command(distro: str, conda: str, conda_env: str) -> list[str]:
    script = (
        "import importlib.metadata as m,json,os,sage,sys; "
        "import sage.env; "
        "d=m.metadata('sage-pycharm-stubgen'); "
        "print(json.dumps({'sageVersion':sage.env.SAGE_VERSION,"
        "'pythonVersion':sys.version.split()[0],"
        "'sagePackage':os.path.dirname(sage.__file__),"
        "'stubgen':{'name':'sage-pycharm-stubgen','version':m.version('sage-pycharm-stubgen'),"
        "'license':d.get('License-Expression') or d.get('License') or 'UNKNOWN'}},sort_keys=True))"
    )
    return ["wsl", "-d", distro, "--", conda, "run", "-n", conda_env, "python", "-c", script]


def validate_probe(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("WSL Sage runtime probe must be an object")
    for field in ("sageVersion", "pythonVersion", "sagePackage"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"WSL Sage runtime probe {field} must be a nonblank string")
    stubgen = value.get("stubgen")
    if not isinstance(stubgen, dict):
        raise ValueError("WSL Sage runtime probe stubgen must be an object")
    for field in ("name", "version"):
        if not isinstance(stubgen.get(field), str) or not stubgen[field].strip():
            raise ValueError(f"WSL Sage runtime probe stubgen.{field} must be a nonblank string")
    return value


def normalize_wsl_path(value: str, distro: str) -> str:
    path = value.replace("\\", "/").rstrip("/")
    prefix = f"//wsl.localhost/{distro}/"
    if path.startswith(prefix):
        return "/" + path[len(prefix):].lstrip("/")
    return path


def validate_generation_report(
    report: dict[str, Any],
    probe: dict[str, Any],
    stub_file_count: int,
    *,
    source_root: Path | None = None,
    distro: str | None = None,
) -> None:
    if not isinstance(report, dict):
        raise ValueError("generation report must be a JSON object")
    required = ("sage_version", "sage_package", "output_root", "discovered", "generated", "failed")
    missing = [field for field in required if field not in report]
    if missing:
        raise ValueError(f"generation report is missing {', '.join(missing)}")
    validate_probe(probe)
    if not isinstance(report["sage_version"], str) or not report["sage_version"].strip():
        raise ValueError("generation report sage_version must be a nonblank string")
    for field in ("sage_package", "output_root"):
        if not isinstance(report[field], str) or not report[field].strip():
            raise ValueError(f"generation report {field} must be a nonblank string")
    for field in ("discovered", "generated", "failed"):
        if type(report[field]) is not int or report[field] < 0:
            raise ValueError(f"generation report {field} must be a nonnegative integer")
    for field in ("fallbacks", "failures"):
        if field in report and not isinstance(report[field], list):
            raise ValueError(f"generation report {field} must be an array")
    docstrings = report.get("docstrings")
    if docstrings is not None:
        if not isinstance(docstrings, dict):
            raise ValueError("generation report docstrings must be an object")
        failures = docstrings.get("runtime_import_failures")
        if failures is not None and not isinstance(failures, list):
            raise ValueError("generation report runtime_import_failures must be an array")
    if report["failed"] != 0:
        raise ValueError("generation report failed must be zero")
    if report["generated"] != report["discovered"]:
        raise ValueError("generation report generated must equal discovered")
    if report["sage_version"] != probe["sageVersion"]:
        raise ValueError("generation report Sage version does not match runtime probe")
    if "python_version" in report:
        if not isinstance(report["python_version"], str) or report["python_version"] != probe["pythonVersion"]:
            raise ValueError("generation report Python version does not match runtime probe")
    report_stubgen = report.get("stubgen")
    if report_stubgen is not None:
        if not isinstance(report_stubgen, dict):
            raise ValueError("generation report stubgen must be an object")
        for field in ("name", "version"):
            if not isinstance(report_stubgen.get(field), str) or not report_stubgen[field].strip():
                raise ValueError(f"generation report stubgen.{field} must be a nonblank string")
        if report_stubgen["name"] != probe["stubgen"]["name"]:
            raise ValueError("generation report stubgen name does not match runtime probe")
        if report_stubgen["version"] != probe["stubgen"]["version"]:
            raise ValueError("generation report stubgen version does not match runtime probe")
    if source_root is not None:
        report_root = normalize_wsl_path(report["output_root"], distro or "Ubuntu")
        expected_root = normalize_wsl_path(str(source_root), distro or "Ubuntu")
        if report_root != expected_root:
            raise ValueError(f"generation report output_root does not match source root: {report['output_root']}")
        report_package = normalize_wsl_path(report["sage_package"], distro or "Ubuntu")
        probe_package = normalize_wsl_path(probe["sagePackage"], distro or "Ubuntu")
        if report_package != probe_package:
            raise ValueError("generation report sage_package does not match runtime probe")
    if stub_file_count < report["generated"]:
        raise ValueError(f"stub file count {stub_file_count} is less than generated {report['generated']}")


def probe_runtime(
    distro: str, conda: str, conda_env: str, *, timeout: float | None = 900.0
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            probe_command(distro, conda, conda_env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"WSL Sage runtime probe timed out after {timeout:g}s") from error
    if result.returncode != 0:
        raise ValueError(f"WSL Sage runtime probe failed ({result.returncode}): {result.stderr.strip()}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if len(lines) != 1:
        raise ValueError("WSL Sage runtime probe did not emit exactly one JSON object")
    return validate_probe(json.loads(lines[0]))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


EXPECTED_KINDS = frozenset({"MODULE", "CLASS", "FUNCTION", "METHOD", "PROPERTY", "CONSTANT", "ALIAS"})


def probe_digest(envelope: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in envelope.items() if key != "probeDigest"}
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def expected_digest(contract: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in contract.items() if key != "expectedDigest"}
    if isinstance(unsigned.get("symbols"), list):
        unsigned["symbols"] = sorted(
            unsigned["symbols"],
            key=lambda item: (item["qualifiedName"], item["kind"]),
        )
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def load_expected_contract(
    path: Path,
    *,
    probe: dict[str, Any],
    artifact_id: str,
    tree_digest_value: str,
    distro: str,
    conda: str,
    conda_env: str,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"expected contract cannot be read: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("expected contract must be a JSON object")
    required = {
        "schemaVersion", "artifactId", "sageVersion", "pythonVersion", "stubgen",
        "provenance", "probeDigest", "treeDigest", "symbols", "expectedDigest",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"expected contract is missing {', '.join(missing)}")
    if value["schemaVersion"] != 1:
        raise ValueError("expected contract schemaVersion must be 1")
    if value["artifactId"] != artifact_id:
        raise ValueError("expected contract artifactId does not match artifact")
    if value["sageVersion"] != probe["sageVersion"]:
        raise ValueError("expected contract Sage version does not match runtime probe")
    if value["pythonVersion"] not in {probe["pythonVersion"], python_minor(probe["pythonVersion"])}:
        raise ValueError("expected contract Python version does not match runtime probe")
    stubgen = value["stubgen"]
    runtime_stubgen = probe["stubgen"]
    if not isinstance(stubgen, dict) or stubgen.get("name") != runtime_stubgen["name"] or stubgen.get("version") != runtime_stubgen["version"]:
        raise ValueError("expected contract stubgen does not match runtime probe")
    provenance = value["provenance"]
    source_prefix = f"wsl:{distro}:{conda}:env={conda_env}"
    if not isinstance(provenance, dict):
        raise ValueError("expected contract provenance must be an object")
    if provenance.get("kind") != "STUBGEN":
        raise ValueError("expected contract provenance kind must be STUBGEN")
    if provenance.get("generator") != f"{runtime_stubgen['name']}/{runtime_stubgen['version']}":
        raise ValueError("expected contract provenance generator does not match runtime probe")
    if not isinstance(provenance.get("source"), str) or not provenance["source"].startswith(source_prefix):
        raise ValueError("expected contract provenance source does not match runtime binding")
    expected_probe_digest = make_probe_envelope(distro, conda, conda_env, probe)["probeDigest"]
    if value["probeDigest"] != expected_probe_digest:
        raise ValueError("expected contract probeDigest does not match runtime probe")
    if value["treeDigest"] != tree_digest_value:
        raise ValueError("expected contract treeDigest does not match source tree")
    symbols = value["symbols"]
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("expected contract symbols must be a non-empty array")
    normalized_symbols: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, symbol in enumerate(symbols):
        if not isinstance(symbol, dict) or not isinstance(symbol.get("qualifiedName"), str) or not symbol["qualifiedName"].strip():
            raise ValueError(f"expected contract symbol {index} requires qualifiedName")
        if symbol.get("kind") not in EXPECTED_KINDS:
            raise ValueError(f"expected contract symbol {index} kind is invalid")
        normalized = {"qualifiedName": symbol["qualifiedName"], "kind": symbol["kind"]}
        key = (normalized["qualifiedName"], normalized["kind"])
        if key in seen:
            raise ValueError(f"expected contract contains duplicate symbol {key[0]} ({key[1]})")
        seen.add(key)
        normalized_symbols.append(normalized)
    normalized = dict(value)
    normalized["symbols"] = sorted(normalized_symbols, key=lambda item: (item["qualifiedName"], item["kind"]))
    if not isinstance(value["expectedDigest"], str) or value["expectedDigest"] != expected_digest(normalized):
        raise ValueError("expected contract expectedDigest is invalid")
    return normalized


def coverage_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Sage API coverage must be a JSON object")
    arrays = ("expected", "covered", "missing", "conflicts", "diagnostics")
    for field in arrays:
        if not isinstance(value.get(field), list):
            raise ValueError(f"Sage API coverage {field} must be an array")
    expected_count = value.get("expectedCount")
    covered_count = value.get("coveredCount")
    missing_count = value.get("missingCount", len(value["missing"]))
    if type(expected_count) is not int or expected_count != len(value["expected"]):
        raise ValueError("Sage API coverage expectedCount is invalid")
    if type(covered_count) is not int or covered_count != len(value["covered"]):
        raise ValueError("Sage API coverage coveredCount is invalid")
    if type(missing_count) is not int or missing_count != len(value["missing"]):
        raise ValueError("Sage API coverage missingCount is invalid")
    conflict_count = len(value["conflicts"])
    if expected_count == 0:
        return {
            "scope": "UNSCOPED",
            "expectedCount": 0,
            "coveredCount": 0,
            "missingCount": 0,
            "coverageRatio": None,
            "isComplete": False,
            "conflictCount": conflict_count,
        }
    ratio = value.get("coverageRatio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        raise ValueError("Sage API coverage coverageRatio is invalid")
    if not isinstance(value.get("isComplete"), bool):
        raise ValueError("Sage API coverage isComplete is invalid")
    return {
        "scope": "SCOPED",
        "expectedCount": expected_count,
        "coveredCount": covered_count,
        "missingCount": missing_count,
        "coverageRatio": ratio,
        "isComplete": value["isComplete"],
        "conflictCount": conflict_count,
    }


def validate_generator_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError("Sage API generator summary must be a non-empty JSON object")
    required = {"entries", "diagnostics", "coverage", "missing"}
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"Sage API generator summary is missing {', '.join(missing)}")
    if any(type(value[field]) is not int or value[field] < 0 for field in ("entries", "diagnostics", "missing")):
        raise ValueError("Sage API generator summary counts are invalid")
    if isinstance(value["coverage"], bool) or not isinstance(value["coverage"], (int, float)):
        raise ValueError("Sage API generator summary coverage is invalid")
    return value


def persist_generator_failure(receipt_path: Path, receipt: dict[str, Any], error: str, returncode: int | None) -> None:
    receipt["generator"]["status"] = "failed"
    receipt["generator"]["returncode"] = returncode
    receipt["generator"]["error"] = error
    write_json(receipt_path, receipt)


def make_probe_envelope(distro: str, conda: str, conda_env: str, probe: dict[str, Any]) -> dict[str, Any]:
    envelope = {
        "schema": 1,
        "mode": "LIVE",
        "command": probe_command(distro, conda, conda_env),
        "distro": distro,
        "conda": conda,
        "env": conda_env,
        "probe": validate_probe(probe),
    }
    envelope["probeDigest"] = probe_digest(envelope)
    return envelope


def write_probe_envelope(path: Path, envelope: dict[str, Any]) -> None:
    write_json(path, envelope)


def load_probe_replay(path: Path, distro: str, conda: str, conda_env: str) -> dict[str, Any]:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"probe replay cannot be read: {error}") from error
    if not isinstance(envelope, dict) or envelope.get("schema") != 1:
        raise ValueError("probe replay schema is invalid")
    required_keys = {"schema", "mode", "command", "distro", "conda", "env", "probe", "probeDigest"}
    if set(envelope) != required_keys:
        raise ValueError("probe replay fields are invalid")
    if envelope.get("mode") != "LIVE":
        raise ValueError("probe replay mode must be LIVE")
    if envelope.get("distro") != distro:
        raise ValueError("probe replay distro does not match")
    if envelope.get("conda") != conda:
        raise ValueError("probe replay conda does not match")
    if envelope.get("env") != conda_env:
        raise ValueError("probe replay env does not match")
    if envelope.get("command") != probe_command(distro, conda, conda_env):
        raise ValueError("probe replay command does not match")
    validate_probe(envelope.get("probe"))
    if envelope.get("probeDigest") != probe_digest(envelope):
        raise ValueError("probe replay digest is invalid")
    return envelope


def run_probe_only(args: argparse.Namespace) -> dict[str, Any]:
    if args.probe_json is None:
        raise ValueError("--probe-only requires --probe-json")
    timeout = getattr(args, "probe_timeout", 900.0)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("--probe-timeout must be positive")
    probe = probe_runtime(args.distro, args.conda, args.conda_env, timeout=timeout)
    envelope = make_probe_envelope(args.distro, args.conda, args.conda_env, probe)
    write_probe_envelope(args.probe_json.resolve(), envelope)
    return envelope


def resolve_probe(args: argparse.Namespace) -> tuple[dict[str, Any], str, str | None, str]:
    probe_only = bool(getattr(args, "probe_only", False))
    probe_json = getattr(args, "probe_json", None)
    allow_replay = bool(getattr(args, "allow_probe_replay", False))
    timeout = getattr(args, "probe_timeout", 900.0)
    if probe_only:
        raise ValueError("probe-only does not resolve an import probe")
    if allow_replay and probe_json is None:
        raise ValueError("--allow-probe-replay requires --probe-json")
    if probe_json is not None:
        if not allow_replay:
            raise ValueError("--probe-json for import requires --allow-probe-replay")
        envelope = load_probe_replay(probe_json.resolve(), args.distro, args.conda, args.conda_env)
        return envelope["probe"], "REPLAY", str(probe_json.resolve()), envelope["probeDigest"]
    envelope = make_probe_envelope(
        args.distro,
        args.conda,
        args.conda_env,
        probe_runtime(args.distro, args.conda, args.conda_env, timeout=timeout),
    )
    return envelope["probe"], "LIVE", None, envelope["probeDigest"]


def python_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
        raise ValueError(f"invalid Python version: {version}")
    return ".".join(parts[:2])


def report_summary(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    summary = {
        "path": str(report_path),
        "digest": sha256(report_path),
        "sagePackage": report["sage_package"],
        "outputRoot": report["output_root"],
        "discovered": report["discovered"],
        "generated": report["generated"],
        "failed": report["failed"],
        "fallbackCount": len(report.get("fallbacks", [])),
        "failureCount": len(report.get("failures", [])),
        "runtimeImportFailureCount": len(report.get("docstrings", {}).get("runtime_import_failures", [])),
    }
    if "python_version" in report:
        summary["pythonVersion"] = report["python_version"]
    if "stubgen" in report:
        summary["stubgen"] = report["stubgen"]
    return summary


def build_artifacts(
    *, probe: dict[str, Any], report: dict[str, Any], source_root: Path,
    report_path: Path, distro: str, conda: str, conda_env: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    probe = validate_probe(probe)
    source_root = source_root.resolve()
    paths = source_files(source_root)
    metadata = source_metadata(source_root, paths)
    validate_generation_report(
        report, probe, len([path for path in paths if path.suffix == ".pyi"]),
        source_root=source_root, distro=distro,
    )
    stubgen = probe["stubgen"]
    artifact_id = f"wsl-{distro.lower()}-sage-{probe['sageVersion']}-stubgen-{stubgen['version']}"
    locator = f"sage-pycharm-stubgen/{probe['sageVersion']}/python-{python_minor(probe['pythonVersion'])}"
    provenance = {
        "kind": "STUBGEN",
        "generator": f"{stubgen['name']}/{stubgen['version']}",
        "source": f"wsl:{distro}:{conda}:env={conda_env}:{source_root}",
    }
    manifest = {
        "artifactId": artifact_id,
        "sageVersion": probe["sageVersion"],
        "pythonVersion": python_minor(probe["pythonVersion"]),
        "provenance": provenance,
        "sources": [{
            "root": str(source_root),
            "kind": "STUBGEN",
            "locator": locator,
            **metadata,
        }],
    }
    receipt = {
        "artifactId": artifact_id,
        "runtime": probe,
        "wsl": {"distro": distro},
        "conda": {"executable": conda, "environment": conda_env},
        "sourceRoot": str(source_root),
        "sourceFiles": metadata["files"],
        "stubFileCount": len([path for path in paths if path.suffix == ".pyi"]),
        "sourceFileCount": metadata["fileCount"],
        "treeDigest": metadata["treeDigest"],
        "generationReport": report_summary(report, report_path),
        "provenance": provenance,
    }
    return manifest, receipt


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def run_import(args: argparse.Namespace) -> dict[str, Any]:
    source_root_arg = getattr(args, "source_root", None)
    report_arg = getattr(args, "generation_report", None)
    if source_root_arg is None or report_arg is None:
        raise ValueError("import requires --source-root and --generation-report")
    source_root = source_root_arg.resolve()
    report_path = report_arg.resolve()
    if not source_root.is_dir():
        raise ValueError(f"stub source root does not exist: {source_root}")
    probe_timeout = getattr(args, "probe_timeout", 900.0)
    generator_timeout = getattr(args, "generator_timeout", 900.0)
    if not isinstance(probe_timeout, (int, float)) or probe_timeout <= 0:
        raise ValueError("--probe-timeout must be positive")
    if not isinstance(generator_timeout, (int, float)) or generator_timeout <= 0:
        raise ValueError("--generator-timeout must be positive")
    if not report_path.is_file():
        raise ValueError(f"generation report does not exist: {report_path}")
    if report_path.parent != source_root:
        raise ValueError("generation report must be inside the stub source root")
    probe, probe_mode, probe_path, probe_digest_value = resolve_probe(args)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest, receipt = build_artifacts(
        probe=probe, report=report, source_root=source_root, report_path=report_path,
        distro=args.distro, conda=args.conda, conda_env=args.conda_env,
    )
    receipt["probeMode"] = probe_mode
    receipt["probeDigest"] = probe_digest_value
    receipt["probeTimeoutSeconds"] = getattr(args, "probe_timeout", 900.0)
    if probe_path is not None:
        receipt["probePath"] = probe_path
    output = args.output_dir.resolve()
    manifest_path = output / "source-manifest.json"
    receipt_path = output / "artifact-receipt.json"
    index_path = output / "sage-api-index.json"
    coverage_path = output / "coverage.json"
    raw_path = output / "raw.json"
    write_json(manifest_path, manifest)
    write_json(receipt_path, receipt)
    command = [
        str(args.python), str(args.generator),
        "--source-manifest", str(manifest_path),
        "--source-base", str(source_root.parent),
        "--sage-version", manifest["sageVersion"],
        "--python-version", manifest["pythonVersion"],
        "--output", str(index_path),
        "--coverage-output", str(coverage_path),
        "--raw-output", str(raw_path),
        "--allow-missing", "--allow-conflicts",
    ]
    expected = getattr(args, "expected", None)
    expected_contract = None
    if expected:
        expected_contract = load_expected_contract(
            expected.resolve(), probe=probe, artifact_id=manifest["artifactId"],
            tree_digest_value=receipt["treeDigest"], distro=args.distro, conda=args.conda, conda_env=args.conda_env,
        )
        expected_array_path = output / "expected-symbols.json"
        write_json(expected_array_path, expected_contract["symbols"])
        command.extend(["--expected", str(expected_array_path)])
        receipt["expected"] = {
            "path": str(expected.resolve()),
            "digest": expected_contract["expectedDigest"],
            "artifactId": expected_contract["artifactId"],
            "count": len(expected_contract["symbols"]),
        }
    else:
        receipt["expected"] = {"count": 0, "scope": "UNSCOPED"}
    generator_timeout = getattr(args, "generator_timeout", 900.0)
    receipt["generator"] = {
        "command": command,
        "timeoutSeconds": generator_timeout,
        "status": "running",
        "returncode": None,
        "outputs": {"index": str(index_path), "coverage": str(coverage_path), "raw": str(raw_path)},
    }
    write_json(receipt_path, receipt)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=generator_timeout,
        )
    except subprocess.TimeoutExpired as error:
        receipt["generator"]["status"] = "timeout"
        write_json(receipt_path, receipt)
        raise ValueError(
            f"Sage API generator timed out after {generator_timeout:g}s"
        ) from error
    if result.returncode != 0:
        error = f"Sage API generator failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        persist_generator_failure(receipt_path, receipt, error, result.returncode)
        raise ValueError(error)
    try:
        summary = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
        summary = validate_generator_summary(summary)
        if not index_path.is_file() or not coverage_path.is_file() or not raw_path.is_file():
            raise ValueError("Sage API post-generator outputs are missing")
        coverage_report = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage = coverage_summary(coverage_report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        message = f"Sage API post-generator validation failed: {error}"
        persist_generator_failure(receipt_path, receipt, message, result.returncode)
        raise ValueError(message) from error
    receipt["coverage"] = coverage
    receipt["generator"] = {
        "command": command,
        "timeoutSeconds": generator_timeout,
        "status": "completed",
        "returncode": result.returncode,
        "summary": summary,
        "diagnostics": {"count": len(coverage_report["diagnostics"]), "conflictCount": len(coverage_report["conflicts"])},
        "outputs": {"index": str(index_path), "coverage": str(coverage_path), "raw": str(raw_path)},
    }
    write_json(receipt_path, receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    base = Path(__file__).resolve().parent
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--distro", default="Ubuntu")
    result.add_argument("--conda", default="/home/starnotes/miniconda3/bin/conda")
    result.add_argument("--conda-env", default="sage")
    result.add_argument("--source-root", type=Path)
    result.add_argument("--generation-report", type=Path)
    result.add_argument("--output-dir", type=Path, default=Path("build/sage-api-real"))
    result.add_argument("--expected", type=Path)
    result.add_argument("--generator", type=Path, default=base / "generate.py")
    result.add_argument("--python", type=Path, default=Path(sys.executable))
    result.add_argument("--probe-only", action="store_true")
    result.add_argument("--probe-json", type=Path)
    result.add_argument("--allow-probe-replay", action="store_true")
    result.add_argument("--probe-timeout", type=float, default=900.0)
    result.add_argument("--generator-timeout", type=float, default=900.0)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.probe_only:
            if args.allow_probe_replay:
                raise ValueError("--probe-only cannot be combined with --allow-probe-replay")
            envelope = run_probe_only(args)
            print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
            return 0
        receipt = run_import(args)
        print(json.dumps({
            "artifactId": receipt["artifactId"],
            "sageVersion": receipt["runtime"]["sageVersion"],
            "pythonVersion": receipt["runtime"]["pythonVersion"],
            "stubgenVersion": receipt["runtime"]["stubgen"]["version"],
            "stubFileCount": receipt["stubFileCount"],
            "treeDigest": receipt["treeDigest"],
            "output": receipt["generator"]["outputs"]["index"],
            "probeMode": receipt["probeMode"],
            "probeDigest": receipt["probeDigest"],
            "expected": receipt.get("expected"),
            "coverage": receipt.get("coverage"),
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"sage-api-artifact: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
