# Windows release audit

The read-only audit entry point is **tools/release/windows-release-audit.ps1**. It checks a release artifact directory without changing artifacts or build/staging trees. The installer execution smoke test is **tools/release/windows-installer-smoke.ps1** and is intentionally separate because it mutates an isolated install directory.

## Usage

~~~powershell
pwsh -NoProfile -File .\product\tools\release\windows-release-audit.ps1 -ArtifactsRoot 'G:\sage-build\artifacts' -Recurse -Version '0.1.0' -OutputJson 'G:\sage-build\audit\windows-release.json' -OutputMarkdown 'G:\sage-build\audit\windows-release.md'
~~~

The script writes JSON/Markdown only when output paths are supplied. With no output paths it prints JSON to stdout and performs no writes. Output directories are created only for explicitly requested report files.

## Installer smoke test

Run the generated x64 or ARM64 installer with the upstream NSIS switches and verify the bundled launcher, `bin/Uninstall.exe`, and `plugins/sage-core/lib/*.jar`, then invoke the generated quiet uninstall:

~~~powershell
pwsh -NoProfile -File .\product\tools\release\windows-installer-smoke.ps1 `\
  -Installer 'G:\sage-build\staging-build6\out\sage-math\artifacts\sageMath-263.SNAPSHOT.exe' `\
  -InstallRoot 'G:\sage-build\smoke\SageMathCTFIDE'
~~~

The smoke script uses `mode=user`, `launcher64=0`, `updatePATH=0`, and `updateContextMenu=0` by default. The generated NSIS contract is `/S /CONFIG=<file> /LOG=<file> /D=<directory>`; NSIS requires `/D` to be the final argument, and this helper therefore requires a whitespace-free install root. Uninstallation uses `/S`. Run it only in a disposable install root; it changes files and registry state under the test installation.

## Checks

- Enumerates release extensions and computes lower-case SHA-256 hashes.
- Classifies installer and uninstaller artifacts independently; names containing uninstall, uninstaller, or remove are never counted as installers.
- Inspects Authenticode for PE/package files and records non-Valid statuses as warnings. An unsigned or unavailable signature is a warning, not an implicit pass.
- Performs static legal checks for LICENSE, NOTICE, COPYING, and third-party license files.
- Searches scanned text files for SPDX-License-Identifier tags.
- Emits passed, counts, artifact records, legal findings, warnings, and errors in JSON; Markdown includes the hash/signature table and warning summary.

## Exit status

By default the audit exits non-zero only for errors. Add -FailOnWarnings when a release gate must reject missing artifacts, unsigned files, missing legal files, or missing SPDX tags.

## Scope and limitations

This is a static artifact audit, not an installer execution test, SBOM validator, malware scan, or legal opinion. It does not modify protected upstream checkouts, staging trees, artifacts, or source files. Authenticode inspection uses Get-AuthenticodeSignature and may report Unavailable on non-Windows hosts.
