[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $PluginZip,
  [Parameter(Mandatory = $true)] [string] $CommunityRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$zip = (Resolve-Path -LiteralPath $PluginZip).Path
$destination = Join-Path $CommunityRoot 'build/sage-core-plugin'
$staging = Join-Path $CommunityRoot 'build/.sage-plugin-extract'

if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) {
  throw "SageMath plugin archive does not exist: $zip"
}

Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $staging | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $staging -Force

$pluginRoot = Join-Path $staging 'sage-core'
if (-not (Test-Path -LiteralPath (Join-Path $pluginRoot 'lib/sage-core-0.1.0-dev.jar') -PathType Leaf)) {
  throw "The archive must contain sage-core/lib/sage-core-0.1.0-dev.jar"
}

Remove-Item -LiteralPath $destination -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$final = Join-Path $destination 'sage-core'
Move-Item -LiteralPath $pluginRoot -Destination $final
Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue

Write-Output "SageMath Core staged at $final"
