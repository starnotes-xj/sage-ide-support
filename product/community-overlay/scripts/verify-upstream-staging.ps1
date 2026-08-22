[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $OfficialCheckout,
  [Parameter(Mandatory = $true)] [string] $StagingTree,
  [string] $ExpectedCommit = 'b0001cd6c53979b384def7a1e3febe061e2ef687',
  [switch] $FinalCheck,
  [switch] $LegacyExternalPlugin
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$official = (Resolve-Path -LiteralPath $OfficialCheckout).Path
$stage = (Resolve-Path -LiteralPath $StagingTree).Path
$officialStatus = @(& git -C $official status --porcelain) | Where-Object { $_ -and $_ -notmatch '^\?\? (\.codegraph[/\\]|hashcat_sessions\.db$|jupyter[/\\]\.gitignore$|notebooks[/\\]\.gitignore$)' }
if ($officialStatus) { throw "Official checkout became dirty:`n$officialStatus" }
$officialCommit = (& git -C $official rev-parse HEAD).Trim()
if ($officialCommit -ne $ExpectedCommit) { throw "Official checkout SHA changed: $officialCommit" }
$stageCommit = (& git -C $stage rev-parse HEAD).Trim()
if ($stageCommit -ne $ExpectedCommit) { throw "Staging SHA mismatch: $stageCommit" }

$manifest = Join-Path $stage 'build/sage-overlay/iml-filter-manifest.json'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw "Missing staging manifest: $manifest" }
$manifestData = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
if ($manifestData.mode -notin @('filtered-staging-only', 'unchanged')) { throw "Unexpected manifest mode: $($manifestData.mode)" }

if ($LegacyExternalPlugin) {
  $plugin = Join-Path $stage 'build/sage-core-plugin/sage-core'
  if (-not (Test-Path -LiteralPath (Join-Path $plugin 'lib') -PathType Container)) { throw "Staged plugin lib directory is missing" }
  if (-not (Get-ChildItem -LiteralPath (Join-Path $plugin 'lib') -Filter '*.jar' -File)) { throw "Staged plugin has no lib/*.jar" }
}
if (-not (Test-Path -LiteralPath (Join-Path $stage 'python/build/src/org/jetbrains/intellij/build/pycharm/SageMathCommunityProperties.kt') -PathType Leaf)) { throw 'Sage product properties are not staged' }
if (-not (Test-Path -LiteralPath (Join-Path $stage 'plugins/sage-core/BUILD.bazel') -PathType Leaf)) { throw 'Sage Core bundled BUILD.bazel is not staged' }
if (-not (Test-Path -LiteralPath (Join-Path $stage 'plugins/sage-core/intellij.sagemath.ctf.sage-core.iml') -PathType Leaf)) { throw 'Sage Core bundled JPS module is not staged' }
if (-not (Test-Path -LiteralPath (Join-Path $stage 'build/BUILD.bazel') -PathType Leaf)) { throw 'Staged Bazel build file is missing' }
$androidManifest = Join-Path $stage 'build/sage-overlay/android-label-filter-manifest.json'
if (-not (Test-Path -LiteralPath $androidManifest -PathType Leaf)) { throw 'Missing staged Android label manifest' }

$javaVersion = (& java -version 2>&1 | Out-String)
if ($javaVersion -notmatch 'version "25') { throw "Expected JDK 25, got:`n$javaVersion" }
Write-Output "Verified official checkout and Sage staging tree at $ExpectedCommit"
if ($FinalCheck) { Write-Output 'Final clean-check completed.' }
