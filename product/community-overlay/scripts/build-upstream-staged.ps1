[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $StagingTree,
  [Parameter(Mandatory = $true)] [string] $Jdk25Home,
  [string] $PluginPath,
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
$outputRoot = Join-Path $buildRoot 'bazel-output'
$tempRoot = Join-Path $buildRoot 'tmp'
foreach ($path in @($userHome, $outputRoot, $tempRoot)) { New-Item -ItemType Directory -Force -Path $path | Out-Null }

$env:JAVA_HOME = $jdk
$env:Path = "$jdk\bin;$env:Path"
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$env:USERPROFILE = $userHome
$env:HOME = $userHome
$env:SAGEMATH_PLUGIN_PATH = if ($PluginPath) { $PluginPath } else { '' }

$bazel = Join-Path $stage 'bazel.cmd'
if (-not (Test-Path -LiteralPath $bazel -PathType Leaf)) { throw "Missing staged Bazel wrapper: $bazel" }
$plugin = if ($PluginPath) { $PluginPath } else { Join-Path $stage 'build/sage-core-plugin/sage-core' }
if (-not (Test-Path -LiteralPath (Join-Path $plugin 'lib') -PathType Container)) { throw "Missing staged plugin lib directory: $plugin" }
if (-not (Get-ChildItem -LiteralPath (Join-Path $plugin 'lib') -Filter '*.jar' -File)) { throw "Staged plugin has no lib/*.jar: $plugin" }

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
$property = "--jvm_flag=-Dsagemath.plugin.path=$plugin"
Push-Location $stage
try {
  if (-not $BuildDev -and -not $BuildInstaller) { $BuildDev = $true }
  if ($BuildDev) {
    Write-Output 'Running staged SageMath development target.'
    Invoke-Bazel ($common + @('run', '//build:sage_math', '--', $property))
  }
  if ($BuildInstaller) {
    Write-Output 'Running staged SageMath installer target.'
    Invoke-Bazel ($common + @('run', '//python/build:sage_i_build_target', '--', $property, '--jvm_flag=-Dintellij.build.target.os=current'))
  }
}
finally {
  Pop-Location
  if (-not $KeepStaging) {
    & git -C $stage worktree remove --force $stage 2>$null
  }
}
