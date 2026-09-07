#!/usr/bin/env python3
"""Import an auditable Sage stubgen artifact from an explicit WSL Conda environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
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
        "fileDigests": {item["path"]: item["digest"] for item in files},
        "treeDigest": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def tree_digest(root: Path, paths: list[Path]) -> str:
    return source_metadata(root, paths)["treeDigest"]


AUTO_CONDA = "auto"


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
    if conda == AUTO_CONDA:
        python_command = f"python -c {shlex.quote(script)}"
        return [
            "wsl", "-d", distro, "--exec", "/bin/bash", "-lc",
            "set -e; "
            "for conda_executable in "
            '"$HOME/miniconda3/bin/conda" '
            '"$HOME/anaconda3/bin/conda" '
            '"$HOME/mambaforge/bin/conda" '
            '"$HOME/miniforge3/bin/conda" '
            '"/opt/conda/bin/conda"; do '
            "if [ -x \"$conda_executable\" ]; then "
            f"exec \"$conda_executable\" run -n {shlex.quote(conda_env)} {python_command}; "
            "fi; done; "
            f"if command -v conda >/dev/null 2>&1; then exec conda run -n {shlex.quote(conda_env)} {python_command}; fi; "
            "echo 'Sage API importer: no WSL Conda executable was found' >&2; exit 127",
        ]
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


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


EXPECTED_KINDS = frozenset({"MODULE", "CLASS", "FUNCTION", "METHOD", "PROPERTY", "CONSTANT", "ALIAS"})
EXPECTED_SOURCE_KINDS = frozenset({"RUNTIME", "STUB", "SIGNATURE", "DOCUMENTATION", "USER_STUB", "PROBE"})
INDEX_SCHEMA_VERSION = 1
INDEX_ENVELOPE_SCHEMA_VERSION = 1
INVENTORY_SCHEMA_VERSION = 1
QUALITY_CONTRACT_VERSION = 1
INVENTORY_KIND_ORDER = {name: index for index, name in enumerate(("MODULE", "CLASS", "FUNCTION", "METHOD", "PROPERTY", "CONSTANT", "ALIAS"))}
TYPE_STATES = frozenset({"KNOWN", "UNKNOWN", "DYNAMIC"})


def source_locator_key(locator: str) -> str:
    base, separator, line = locator.rpartition(":")
    return base if separator and line.isdigit() else locator


def inventory_identity_digest(identities: list[dict[str, str]]) -> str:
    return hashlib.sha256(canonical_json(identities).encode("utf-8")).hexdigest()


def validate_inventory(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != INVENTORY_SCHEMA_VERSION:
        raise ValueError("Sage API inventory schemaVersion is invalid")
    if value.get("basis") != "RAW_AST_DECLARATIONS":
        raise ValueError("Sage API inventory basis is invalid")
    for field in ("sageVersion", "pythonVersion", "generatorVersion"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"Sage API inventory {field} is invalid")
    identities = value.get("identities")
    if not isinstance(identities, list):
        raise ValueError("Sage API inventory identities must be an array")
    seen: set[tuple[str, str]] = set()
    previous: tuple[str, int] | None = None
    for index, item in enumerate(identities):
        key = identity_key(item, f"inventory.identities[{index}]")
        if key in seen:
            raise ValueError(f"Sage API inventory contains duplicate identity {key[0]} ({key[1]})")
        order_key = (key[0], INVENTORY_KIND_ORDER[key[1]])
        if previous is not None and order_key <= previous:
            raise ValueError("Sage API inventory identities are not strictly sorted")
        previous = order_key
        seen.add(key)
    if value.get("identityCount") != len(identities) or value.get("identityDigest") != inventory_identity_digest(identities):
        raise ValueError("Sage API inventory identity digest is invalid")
    for field in ("rawDeclarationCount", "sourceFileCount"):
        if type(value.get(field)) is not int or value[field] < 0:
            raise ValueError(f"Sage API inventory {field} is invalid")
    if value["rawDeclarationCount"] < value["identityCount"]:
        raise ValueError("Sage API inventory rawDeclarationCount is less than identityCount")
    source_digests = value.get("sourceDigests")
    if not isinstance(source_digests, dict) or len(source_digests) != value["sourceFileCount"]:
        raise ValueError("Sage API inventory sourceDigests are invalid")
    for locator, digest in source_digests.items():
        if not isinstance(locator, str) or not locator.strip() or not is_sha256(digest):
            raise ValueError("Sage API inventory sourceDigests contain an invalid digest")
    return value


def identity_key(value: Any, path: str) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    qualified_name = value.get("qualifiedName")
    kind = value.get("kind")
    if not isinstance(qualified_name, str) or not qualified_name.strip() or not isinstance(kind, str) or kind not in EXPECTED_KINDS:
        raise ValueError(f"{path} identity is invalid")
    return qualified_name, kind


SOURCE_PROVENANCE_KIND = "STUBGEN"


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
    if isinstance(unsigned.get("quality"), list):
        unsigned["quality"] = sorted(
            unsigned["quality"],
            key=lambda item: (item["qualifiedName"], item["kind"]),
        )
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def validate_quality_contract(value: Any, *, require_nonempty: bool = False) -> list[dict[str, Any]]:
    quality = value.get("quality") if isinstance(value, dict) else None
    if quality is None:
        if require_nonempty:
            raise ValueError("expected contract quality must be a non-empty array")
        return []
    if not isinstance(quality, list) or (require_nonempty and not quality):
        raise ValueError("expected contract quality must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(quality):
        if not isinstance(item, dict):
            raise ValueError(f"expected contract quality item {index} must be an object")
        qualified_name = item.get("qualifiedName")
        kind = item.get("kind")
        if not isinstance(qualified_name, str) or not qualified_name.strip():
            raise ValueError(f"expected contract quality item {index} requires qualifiedName")
        if not isinstance(kind, str) or kind not in EXPECTED_KINDS:
            raise ValueError(f"expected contract quality item {index} kind is invalid")
        key = (qualified_name, kind)
        if key in seen:
            raise ValueError(f"expected contract contains duplicate quality item {qualified_name} ({kind})")
        seen.add(key)
        source = item.get("source")
        if not isinstance(source, dict) or source.get("kind") not in EXPECTED_SOURCE_KINDS:
            raise ValueError(f"expected contract quality item {index} source kind is invalid")
        if not isinstance(source.get("locatorPrefix"), str) or not source["locatorPrefix"].strip():
            raise ValueError(f"expected contract quality item {index} source locatorPrefix is invalid")
        if not is_sha256(source.get("digest")):
            raise ValueError(f"expected contract quality item {index} source digest is invalid")
        signatures = item.get("signatures")
        if not isinstance(signatures, list):
            raise ValueError(f"expected contract quality item {index} signatures must be an array")
        for signature_index, signature in enumerate(signatures):
            if not isinstance(signature, dict) or not isinstance(signature.get("parameters"), list):
                raise ValueError(f"expected contract quality item {index} signature {signature_index} parameters are invalid")
            return_type = signature.get("returnType")
            if not isinstance(return_type, dict) or return_type.get("state") not in TYPE_STATES:
                raise ValueError(f"expected contract quality item {index} signature {signature_index} returnType is invalid")
            if "expression" in return_type and return_type["expression"] is not None and not isinstance(return_type["expression"], str):
                raise ValueError(f"expected contract quality item {index} signature {signature_index} returnType expression is invalid")
            for parameter_index, parameter in enumerate(signature["parameters"]):
                if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str) or not parameter["name"].strip():
                    raise ValueError(f"expected contract quality item {index} parameter {parameter_index} name is invalid")
                if parameter.get("typeState") not in TYPE_STATES:
                    raise ValueError(f"expected contract quality item {index} parameter {parameter_index} typeState is invalid")
                if "typeExpression" in parameter and parameter["typeExpression"] is not None and not isinstance(parameter["typeExpression"], str):
                    raise ValueError(f"expected contract quality item {index} parameter {parameter_index} typeExpression is invalid")
                for field in ("optional", "keywordOnly", "variadic"):
                    if field in parameter and not isinstance(parameter[field], bool):
                        raise ValueError(f"expected contract quality item {index} parameter {parameter_index} {field} is invalid")
                if "defaultValue" in parameter and parameter["defaultValue"] is not None and not isinstance(parameter["defaultValue"], str):
                    raise ValueError(f"expected contract quality item {index} parameter {parameter_index} defaultValue is invalid")
        documentation = item.get("documentation")
        if not isinstance(documentation, dict):
            raise ValueError(f"expected contract quality item {index} documentation is invalid")
        for field in ("required", "nonEmpty", "nonEmptyArrays"):
            values = documentation.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"expected contract quality item {index} documentation.{field} is invalid")
        normalized.append(dict(item))
    return sorted(normalized, key=lambda item: (item["qualifiedName"], item["kind"]))


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
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
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
    if provenance.get("kind") != SOURCE_PROVENANCE_KIND:
        raise ValueError("expected contract provenance kind must be STUBGEN")
    if provenance.get("generator") != f"{runtime_stubgen['name']}/{runtime_stubgen['version']}":
        raise ValueError("expected contract provenance generator does not match runtime probe")
    if not isinstance(provenance.get("source"), str) or not (provenance["source"] == source_prefix or provenance["source"].startswith(source_prefix + ":")):
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
    quality = validate_quality_contract(value)
    if "qualityContractVersion" in value:
        if type(value.get("qualityContractVersion")) is not int or value["qualityContractVersion"] != QUALITY_CONTRACT_VERSION:
            raise ValueError("expected contract qualityContractVersion is invalid")
        if not isinstance(value.get("quality"), list) or not quality:
            raise ValueError("expected contract quality must be a non-empty array")
        normalized["quality"] = quality
    if not isinstance(value["expectedDigest"], str) or value["expectedDigest"] != expected_digest(normalized):
        raise ValueError("expected contract expectedDigest is invalid")
    return normalized


def _validate_type_reference(value: Any, path: str) -> None:
    if not isinstance(value, dict) or value.get("state") not in TYPE_STATES:
        raise ValueError(f"{path} is an invalid type reference")
    expression = value.get("expression")
    if expression is not None and (not isinstance(expression, str) or not expression.strip()):
        raise ValueError(f"{path}.expression is invalid")
    if value["state"] == "KNOWN" and not isinstance(expression, str):
        raise ValueError(f"{path} KNOWN type requires an expression")


def _validate_index_signature(value: Any, path: str) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("parameters"), list) or "returnType" not in value:
        raise ValueError(f"{path} is invalid")
    for index, parameter in enumerate(value["parameters"]):
        parameter_path = f"{path}.parameters[{index}]"
        if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str) or not parameter["name"].strip():
            raise ValueError(f"{parameter_path} is invalid")
        _validate_type_reference(parameter.get("type"), f"{parameter_path}.type")
        for field in ("optional", "keywordOnly", "variadic"):
            if field in parameter and type(parameter[field]) is not bool:
                raise ValueError(f"{parameter_path}.{field} must be boolean")
        if "defaultValue" in parameter and parameter["defaultValue"] is not None and not isinstance(parameter["defaultValue"], str):
            raise ValueError(f"{parameter_path}.defaultValue is invalid")
    _validate_type_reference(value["returnType"], f"{path}.returnType")


def _validate_index_entry(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    for field in ("qualifiedName", "kind", "dynamicity", "confidence"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"{path}.{field} must be a nonblank string")
    if value["kind"] not in EXPECTED_KINDS:
        raise ValueError(f"{path}.kind is invalid")
    if value["dynamicity"] not in {"STATIC", "DYNAMIC", "UNKNOWN"}:
        raise ValueError(f"{path}.dynamicity is invalid")
    if value["confidence"] not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError(f"{path}.confidence is invalid")
    for field in ("parents", "protocols", "aliases"):
        if not isinstance(value.get(field), list) or not all(isinstance(item, str) and item.strip() for item in value[field]):
            raise ValueError(f"{path}.{field} must contain nonblank strings")
    signatures = value.get("signatures")
    if not isinstance(signatures, list):
        raise ValueError(f"{path}.signatures must be an array")
    for index, signature in enumerate(signatures):
        _validate_index_signature(signature, f"{path}.signatures[{index}]")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{path}.sources must be a nonempty array")
    for index, source in enumerate(sources):
        source_path = f"{path}.sources[{index}]"
        if not isinstance(source, dict) or source.get("kind") not in EXPECTED_SOURCE_KINDS or not isinstance(source.get("locator"), str) or not source["locator"].strip():
            raise ValueError(f"{source_path} is invalid")
        digest = source.get("digest")
        if digest is not None and not is_sha256(digest):
            raise ValueError(f"{source_path}.digest is invalid")
    if "valueType" in value:
        _validate_type_reference(value["valueType"], f"{path}.valueType")
    if "documentation" in value and not isinstance(value["documentation"], dict):
        raise ValueError(f"{path}.documentation must be an object")


def read_index(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Sage API index cannot be read: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Sage API index must be a JSON object")
    required = ("schemaVersion", "sageVersion", "pythonVersion", "generatorVersion", "sourceDigests", "entries")
    missing = [field for field in required if field not in value]
    if missing:
        raise ValueError(f"Sage API index is missing {', '.join(missing)}")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != INDEX_SCHEMA_VERSION:
        raise ValueError("Sage API index schemaVersion must be 1")
    for field in ("sageVersion", "pythonVersion", "generatorVersion"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"Sage API index {field} is invalid")
    source_digests = value["sourceDigests"]
    if not isinstance(source_digests, dict):
        raise ValueError("Sage API index sourceDigests must be an object")
    for locator, digest in source_digests.items():
        if not isinstance(locator, str) or not locator.strip() or not is_sha256(digest):
            raise ValueError("Sage API index sourceDigests contains an invalid digest")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise ValueError("Sage API index entries must be an array")
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        _validate_index_entry(entry, f"entries[{index}]")
        key = (entry["qualifiedName"], entry["kind"])
        if key in seen:
            raise ValueError(f"Sage API index contains duplicate entry {key[0]} ({key[1]})")
        seen.add(key)
        for source in entry["sources"]:
            locator = source_locator_key(source["locator"])
            if locator not in source_digests:
                raise ValueError(f"Sage API index source locator is not declared: {locator}")
            if source.get("digest") != source_digests[locator]:
                raise ValueError(f"Sage API index source digest mismatch: {locator}")
    return value


def index_entry_map(index: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for position, entry in enumerate(index["entries"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Sage API index entry {position} must be an object")
        key = (entry.get("qualifiedName"), entry.get("kind"))
        if not isinstance(key[0], str) or key[1] not in EXPECTED_KINDS:
            raise ValueError(f"Sage API index entry {position} identity is invalid")
        if key in result:
            raise ValueError(f"Sage API index contains duplicate entry {key[0]} ({key[1]})")
        result[key] = entry
    return result


def validate_index_quality(index: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    entries = index_entry_map(index)
    quality = validate_quality_contract(contract, require_nonempty=True)
    checked: list[dict[str, Any]] = []
    source_digests = index.get("sourceDigests", {})
    for item in quality:
        key = (item["qualifiedName"], item["kind"])
        entry = entries.get(key)
        if entry is None:
            raise ValueError(f"Sage API quality contract entry is missing: {key[0]} ({key[1]})")
        sources = entry.get("sources")
        source_spec = item["source"]
        if not isinstance(sources, list) or not any(
            isinstance(source, dict)
            and source.get("kind") == source_spec["kind"]
            and isinstance(source.get("locator"), str)
            and (source["locator"] == source_spec["locatorPrefix"] or source["locator"].startswith(source_spec["locatorPrefix"]))
            and source.get("digest") == source_spec["digest"]
            and source_digests.get(source_locator_key(source["locator"])) == source_spec["digest"]
            for source in sources
        ):
            raise ValueError(f"Sage API quality source mismatch: {key[0]} ({key[1]})")
        actual_signatures = entry.get("signatures")
        if not isinstance(actual_signatures, list) or len(actual_signatures) != len(item["signatures"]):
            raise ValueError(f"Sage API quality signature count mismatch: {key[0]} ({key[1]})")
        for signature_index, (actual, expected) in enumerate(zip(actual_signatures, item["signatures"])):
            actual_parameters = actual.get("parameters") if isinstance(actual, dict) else None
            if not isinstance(actual_parameters, list) or len(actual_parameters) != len(expected["parameters"]):
                raise ValueError(f"Sage API quality parameter count mismatch: {key[0]} signature {signature_index}")
            for parameter_index, (actual_parameter, expected_parameter) in enumerate(zip(actual_parameters, expected["parameters"])):
                for field in ("name", "optional", "keywordOnly", "variadic", "defaultValue"):
                    if field in expected_parameter and actual_parameter.get(field) != expected_parameter[field]:
                        raise ValueError(f"Sage API quality parameter mismatch: {key[0]} parameter {parameter_index} {field}")
                actual_type = actual_parameter.get("type")
                if not isinstance(actual_type, dict) or actual_type.get("state") != expected_parameter["typeState"] or ("typeExpression" in expected_parameter and actual_type.get("expression") != expected_parameter["typeExpression"]):
                    raise ValueError(f"Sage API quality parameter type mismatch: {key[0]} parameter {parameter_index}")
            actual_return = actual.get("returnType")
            expected_return = expected["returnType"]
            if not isinstance(actual_return, dict) or actual_return.get("state") != expected_return["state"] or ("expression" in expected_return and actual_return.get("expression") != expected_return["expression"]):
                raise ValueError(f"Sage API quality return type mismatch: {key[0]} signature {signature_index}")
        documentation = entry.get("documentation")
        required_documentation = item["documentation"]["required"]
        non_empty_documentation = item["documentation"]["nonEmpty"]
        non_empty_array_documentation = item["documentation"].get("nonEmptyArrays", [])
        if not isinstance(documentation, dict):
            raise ValueError(f"Sage API quality documentation is missing: {key[0]} ({key[1]})")
        for field in required_documentation:
            if field not in documentation:
                raise ValueError(f"Sage API quality documentation field is missing: {key[0]} {field}")
        for field in non_empty_documentation:
            if not isinstance(documentation.get(field), str) or not documentation[field].strip():
                raise ValueError(f"Sage API quality documentation field is empty: {key[0]} {field}")
        for field in non_empty_array_documentation:
            if not isinstance(documentation.get(field), list) or not documentation[field]:
                raise ValueError(f"Sage API quality documentation array is empty: {key[0]} {field}")
            if any(not isinstance(value, str) for value in documentation[field]):
                raise ValueError(f"Sage API quality documentation array is invalid: {key[0]} {field}")
        checked.append({"qualifiedName": key[0], "kind": key[1]})
    return {"contractVersion": QUALITY_CONTRACT_VERSION, "checkedCount": len(checked), "checked": checked}


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
        "kind": SOURCE_PROVENANCE_KIND,
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
            "kind": SOURCE_PROVENANCE_KIND,
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
        "sourceFileDigests": metadata["fileDigests"],
        "stubFileCount": len([path for path in paths if path.suffix == ".pyi"]),
        "sourceFileCount": metadata["fileCount"],
        "treeDigest": metadata["treeDigest"],
        "generationReport": report_summary(report, report_path),
        "provenance": provenance,
    }
    return manifest, receipt


def canonical_artifact_path(path: Path, output: Path) -> str:
    return path.resolve().relative_to(output.resolve()).as_posix()


def canonical_output_value(value: str, output: Path) -> str:
    try:
        path = Path(value)
        return canonical_artifact_path(path, output) if path.is_absolute() else value
    except (OSError, ValueError):
        return value


def canonical_command(command: list[str], output: Path) -> list[str]:
    return [canonical_output_value(value, output) for value in command]


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
    inventory_path = output / "api-inventory.json"
    envelope_path = output / "sage-api-index-envelope.json"
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
        "--inventory-output", str(inventory_path),
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
            "qualityCount": len(expected_contract.get("quality", [])),
            "qualityContractVersion": expected_contract.get("qualityContractVersion"),
        }
    else:
        receipt["expected"] = {"count": 0, "scope": "UNSCOPED", "qualityCount": 0}
    generator_timeout = getattr(args, "generator_timeout", 900.0)
    receipt["generator"] = {
        "command": canonical_command(command, output),
        "timeoutSeconds": generator_timeout,
        "status": "running",
        "returncode": None,
        "outputs": {"index": "sage-api-index.json", "coverage": "coverage.json", "raw": "raw.json", "inventory": "api-inventory.json"},
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
        if not index_path.is_file() or not coverage_path.is_file() or not raw_path.is_file() or not inventory_path.is_file():
            raise ValueError("Sage API post-generator outputs are missing")
        index = read_index(index_path)
        if index["sageVersion"] != manifest["sageVersion"] or index["pythonVersion"] != manifest["pythonVersion"]:
            raise ValueError("Sage API index version identity does not match manifest")
        coverage_report = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage = coverage_summary(coverage_report)
        inventory = validate_inventory(json.loads(inventory_path.read_text(encoding="utf-8")))
        index_ids = {identity_key(entry, "index.entries") for entry in index["entries"]}
        inventory_ids = {identity_key(item, "inventory.identities") for item in inventory["identities"]}
        if index_ids != inventory_ids:
            raise ValueError("Sage API inventory identities do not match normalized index entries")
        if inventory["identityCount"] != len(index_ids):
            raise ValueError("Sage API inventory identityCount does not match normalized index entries")
        if inventory["sageVersion"] != manifest["sageVersion"] or inventory["pythonVersion"] != manifest["pythonVersion"]:
            raise ValueError("Sage API inventory version identity does not match manifest")
        source_spec = manifest["sources"][0]
        expected_inventory_sources = {
            source_spec["locator"] + "/" + path: digest
            for path, digest in source_spec["fileDigests"].items()
        }
        if inventory["sourceDigests"] != expected_inventory_sources:
            raise ValueError("Sage API inventory source digests do not match source manifest")
        quality = None
        if expected_contract is not None and expected_contract.get("quality"):
            quality = validate_index_quality(index, expected_contract)
        if expected_contract is not None:
            expected_ids = [identity_key(item, "expected.symbols") for item in expected_contract["symbols"]]
            if len(set(expected_ids)) != len(expected_ids):
                raise ValueError("Sage API expected symbols contain duplicates")
            coverage_ids = {}
            for field in ("expected", "covered", "missing"):
                values = coverage_report[field]
                ids = [identity_key(item, f"coverage.{field}") for item in values]
                if len(set(ids)) != len(ids):
                    raise ValueError(f"Sage API coverage {field} contains duplicates")
                coverage_ids[field] = set(ids)
            expected_set = set(expected_ids)
            if coverage_ids["expected"] != expected_set or coverage_ids["covered"] | coverage_ids["missing"] != expected_set or coverage_ids["covered"] & coverage_ids["missing"]:
                raise ValueError("Sage API coverage identities do not match expected contract")
            if coverage["expectedCount"] != len(expected_set) or coverage["coveredCount"] != len(coverage_ids["covered"]) or coverage["missingCount"] != len(coverage_ids["missing"]):
                raise ValueError("Sage API coverage counts do not match expected identities")
            if coverage["isComplete"] != (not coverage_ids["missing"] and not coverage_report["conflicts"]):
                raise ValueError("Sage API coverage isComplete is inconsistent")
        envelope = {
            "schemaVersion": INDEX_ENVELOPE_SCHEMA_VERSION,
            "scope": "SCOPED" if expected_contract is not None else "UNSCOPED",
            "apiCoverage": {
                "scope": "FULL",
                "expectedCount": inventory["identityCount"],
                "coveredCount": len(index["entries"]),
                "missingCount": 0,
                "coverageRatio": 1.0,
                "isComplete": True,
                "identityDigest": inventory["identityDigest"],
            },
            "artifactId": manifest["artifactId"],
            "sageVersion": manifest["sageVersion"],
            "pythonVersion": manifest["pythonVersion"],
            "generatorVersion": index["generatorVersion"],
            "provenance": manifest["provenance"],
            "sourceManifest": {"path": "source-manifest.json", "digest": sha256(manifest_path)},
            "artifactReceipt": {"path": "artifact-receipt.json"},
            "probe": {"mode": probe_mode, "digest": probe_digest_value, "path": probe_path},
            "treeDigest": receipt["treeDigest"],
            "index": {"path": "sage-api-index.json", "sha256": sha256(index_path), "entryCount": len(index["entries"])},
            "inventory": {"path": "api-inventory.json", "sha256": sha256(inventory_path)},
            "coverage": coverage,
            "diagnostics": {"count": len(coverage_report["diagnostics"]), "conflictCount": len(coverage_report["conflicts"]), "conflicts": coverage_report["conflicts"]},
            "quality": quality,
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        message = f"Sage API post-generator validation failed: {error}"
        persist_generator_failure(receipt_path, receipt, message, result.returncode)
        raise ValueError(message) from error
    receipt["coverage"] = coverage
    receipt["inventory"] = {"path": "api-inventory.json", "sha256": envelope["inventory"]["sha256"], "identityCount": inventory["identityCount"], "identityDigest": inventory["identityDigest"]}
    receipt["index"] = {"path": "sage-api-index.json", "sha256": envelope["index"]["sha256"], "entryCount": envelope["index"]["entryCount"]}
    receipt["quality"] = quality
    receipt["envelope"] = {"path": "sage-api-index-envelope.json", "schemaVersion": INDEX_ENVELOPE_SCHEMA_VERSION}
    receipt["generator"] = {
        "command": canonical_command(command, output),
        "timeoutSeconds": generator_timeout,
        "status": "completed",
        "returncode": result.returncode,
        "summary": summary,
        "diagnostics": {"count": len(coverage_report["diagnostics"]), "conflictCount": len(coverage_report["conflicts"])},
        "outputs": {"index": "sage-api-index.json", "coverage": "coverage.json", "raw": "raw.json", "inventory": "api-inventory.json"},
    }
    receipt["generator"]["commandDigest"] = hashlib.sha256(canonical_json(canonical_command(command, output)).encode("utf-8")).hexdigest()
    write_json(envelope_path, envelope)
    receipt["envelope"]["digest"] = sha256(envelope_path)
    write_json(receipt_path, receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    base = Path(__file__).resolve().parent
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--distro", default="Ubuntu")
    result.add_argument(
        "--conda",
        default=AUTO_CONDA,
        help="WSL Conda executable, or 'auto' to resolve it from the current WSL user's HOME/PATH",
    )
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
