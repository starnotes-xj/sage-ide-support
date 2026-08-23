[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $StagingTree,
  [Parameter(Mandatory = $true)] [string] $Jdk25Home,
  [string] $PluginPath,
  [switch] $LegacyExternalPlugin,
  [switch] $BuildDev,
  [switch] $BuildInstaller,
  [switch] $KeepStaging,
  [string] $AsciiBuildRoot = 'G:\sage-build'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$stage = (Resolve-Path -LiteralPath $StagingTree).Path
$jdk = (Resolve-Path -LiteralPath $Jdk25Home).Path
$buildRoot = [IO.Path]::GetFullPath($AsciiBuildRoot)
$userHome = Join-Path $buildRoot 'user-home'
$appData = Join-Path $buildRoot 'appdata'
$localAppData = Join-Path $buildRoot 'localappdata'
$outputRoot = Join-Path $buildRoot 'bazel-output'
# The staged product's nested Bazel invocation uses this independent ASCII root.
# Keep it outside Bazel's own output tree so Bazel never treats its execroot as a workspace.
$nestedBazelRoot = Join-Path $buildRoot 'nested-bazel'
$tempRoot = Join-Path $buildRoot 'tmp'
foreach ($path in @($userHome, $appData, $localAppData, $outputRoot, $nestedBazelRoot, $tempRoot)) { New-Item -ItemType Directory -Force -Path $path | Out-Null }

$env:JAVA_HOME = $jdk
$env:Path = "$jdk\bin;$env:Path"
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$env:USERPROFILE = $userHome
$env:HOME = $userHome
$env:APPDATA = $appData
$env:LOCALAPPDATA = $localAppData
$env:BAZELISK_HOME = $userHome
$env:HOMEDRIVE = 'G:'
$env:HOMEPATH = '\sage-build\bundled-next\user-home'
$env:USERNAME = 'sagebuild'
$env:SAGEMATH_PLUGIN_PATH = if ($LegacyExternalPlugin -and $PluginPath) { $PluginPath } else { '' }
$env:SAGEMATH_BAZEL_ASCII_ROOT = $nestedBazelRoot
$env:SAGEMATH_BAZEL_WORKSPACE_ROOT = $stage
# Product builds invoke a second Bazel process for bundled plugins. Bazel
# rejects being launched from an output-tree cwd, so force that child back to
# the staged workspace rather than inheriting the product builder's execroot.
$env:BUILD_WORKSPACE_DIRECTORY = $stage
$env:BUILD_WORKING_DIRECTORY = $stage
$env:BAZEL_SH = 'C:\WINDOWS\system32\bash.exe'

$bazel = Join-Path $stage 'bazel.cmd'
if (-not (Test-Path -LiteralPath $bazel -PathType Leaf)) { throw "Missing staged Bazel wrapper: $bazel" }
if ($LegacyExternalPlugin) {
  $plugin = if ($PluginPath) { $PluginPath } else { Join-Path $stage 'build/sage-core-plugin/sage-core' }
  if (-not (Test-Path -LiteralPath (Join-Path $plugin 'lib') -PathType Container)) { throw "Missing staged plugin lib directory: $plugin" }
  if (-not (Get-ChildItem -LiteralPath (Join-Path $plugin 'lib') -Filter '*.jar' -File)) { throw "Staged plugin has no lib/*.jar: $plugin" }
} else {
  $plugin = $null
  if (-not (Test-Path -LiteralPath (Join-Path $stage 'plugins/sage-core/BUILD.bazel') -PathType Leaf)) { throw "Missing bundled Sage Core BUILD.bazel" }
}

function Invoke-Bazel([string[]] $Arguments) {
  & $bazel @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Bazel failed with exit code $LASTEXITCODE" }
}

$common = @(
  '--batch',
  "--output_user_root=$outputRoot",
  "--host_jvm_args=-Duser.home=$userHome",
  "--host_jvm_args=-Djava.io.tmpdir=$tempRoot"
)
$property = if ($LegacyExternalPlugin) { "--jvm_flag=-Dsagemath.plugin.path=$plugin" } else { $null }
Push-Location $stage
try {
  if (-not $BuildDev -and -not $BuildInstaller) { $BuildDev = $true }
  if ($BuildDev) {
    Write-Output 'Running staged SageMath development target.'
    $args = @('run', '//build:sage_math', '--')
    if ($property) { $args += $property }
    $args += '--jvm_flag=-Dintellij.build.build.plugins.by.bazel=true'
    Invoke-Bazel ($common + $args)
  }
  if ($BuildInstaller) {
    Write-Output 'Running staged SageMath installer target.'
    $args = @('run', '//python/build:sage_i_build_target', '--')
    if ($property) { $args += $property }
    $args += '--jvm_flag=-Dintellij.build.plugins.by.bazel=true'
    $args += '--jvm_flag=-Dintellij.build.build.plugins.by.bazel=true'
    $args += '--jvm_flag=-Dintellij.build.target.os=current'
    Invoke-Bazel ($common + $args)
  }
}
finally {
  Pop-Location
  if (-not $KeepStaging) {
    & git -C $stage worktree remove --force $stage 2>$null
  }
}
