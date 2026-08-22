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


def probe_runtime(distro: str, conda: str, conda_env: str) -> dict[str, Any]:
    result = subprocess.run(
        probe_command(distro, conda, conda_env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ValueError(f"WSL Sage runtime probe failed ({result.returncode}): {result.stderr.strip()}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if len(lines) != 1:
        raise ValueError("WSL Sage runtime probe did not emit exactly one JSON object")
    return validate_probe(json.loads(lines[0]))


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
    source_root = args.source_root.resolve()
    report_path = args.generation_report.resolve()
    if not source_root.is_dir():
        raise ValueError(f"stub source root does not exist: {source_root}")
    if not report_path.is_file():
        raise ValueError(f"generation report does not exist: {report_path}")
    if report_path.parent != source_root:
        raise ValueError("generation report must be inside the stub source root")
    probe = probe_runtime(args.distro, args.conda, args.conda_env)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest, receipt = build_artifacts(
        probe=probe, report=report, source_root=source_root, report_path=report_path,
        distro=args.distro, conda=args.conda, conda_env=args.conda_env,
    )
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
    if args.expected:
        command.extend(["--expected", str(args.expected.resolve())])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ValueError(f"Sage API generator failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    summary = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
    if not isinstance(summary, dict):
        raise ValueError("Sage API generator summary must be a JSON object")
    coverage_report = json.loads(coverage_path.read_text(encoding="utf-8"))
    if not isinstance(coverage_report, dict):
        raise ValueError("Sage API coverage must be a JSON object")
    diagnostics = coverage_report.get("diagnostics", [])
    conflicts = coverage_report.get("conflicts", [])
    if not isinstance(diagnostics, list) or not isinstance(conflicts, list):
        raise ValueError("Sage API coverage diagnostics must be arrays")
    receipt["generator"] = {
        "command": command,
        "summary": summary,
        "diagnostics": {"count": len(diagnostics), "conflictCount": len(conflicts)},
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
    result.add_argument("--source-root", type=Path, required=True)
    result.add_argument("--generation-report", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, default=Path("build/sage-api-real"))
    result.add_argument("--expected", type=Path)
    result.add_argument("--generator", type=Path, default=base / "generate.py")
    result.add_argument("--python", type=Path, default=Path(sys.executable))
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        receipt = run_import(parser().parse_args(argv))
        print(json.dumps({
            "artifactId": receipt["artifactId"],
            "sageVersion": receipt["runtime"]["sageVersion"],
            "pythonVersion": receipt["runtime"]["pythonVersion"],
            "stubgenVersion": receipt["runtime"]["stubgen"]["version"],
            "stubFileCount": receipt["stubFileCount"],
            "treeDigest": receipt["treeDigest"],
            "output": receipt["generator"]["outputs"]["index"],
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"sage-api-artifact: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
