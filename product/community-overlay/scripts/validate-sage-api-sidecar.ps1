[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $ArtifactDirectory,
  [string] $DestinationDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$artifact = (Resolve-Path -LiteralPath $ArtifactDirectory).Path
$indexPath = Join-Path $artifact 'sage-api-index.json'
$envelopePath = Join-Path $artifact 'sage-api-index-envelope.json'
$receiptPath = Join-Path $artifact 'artifact-receipt.json'
foreach ($file in @($indexPath, $envelopePath, $receiptPath)) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing Sage API sidecar artifact: $file" }
}

$index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
$envelope = Get-Content -LiteralPath $envelopePath -Raw | ConvertFrom-Json
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ([int]$index.schemaVersion -ne 1) { throw "Unsupported Sage API index schema: $($index.schemaVersion)" }
if ([int]$envelope.schemaVersion -ne 1) { throw "Unsupported Sage API envelope schema: $($envelope.schemaVersion)" }
if ($index.sageVersion -ne '10.9' -or $index.pythonVersion -ne '3.13') { throw "Unexpected Sage/Python version: $($index.sageVersion)/$($index.pythonVersion)" }
if ($envelope.apiCoverage.scope -ne 'FULL') { throw 'Sage API envelope is not FULL coverage' }
if (-not [bool]$envelope.apiCoverage.isComplete) { throw 'Sage API envelope is incomplete' }
if ($envelope.index.path -ne 'sage-api-index.json') { throw "Unexpected envelope index path: $($envelope.index.path)" }
if ($receipt.artifactId -ne $envelope.artifactId) { throw 'Artifact receipt and envelope IDs differ' }
if ($receipt.index.path -ne 'sage-api-index.json') { throw "Unexpected receipt index path: $($receipt.index.path)" }
$actualHash = (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $envelope.index.sha256.ToLowerInvariant()) { throw 'Index SHA-256 does not match envelope' }
if ($actualHash -ne $receipt.index.sha256.ToLowerInvariant()) { throw 'Index SHA-256 does not match receipt' }
if ([int]$index.entries.Count -ne [int]$envelope.index.entryCount) { throw 'Index entry count does not match envelope' }
if ([int]$index.entries.Count -ne [int]$receipt.index.entryCount) { throw 'Index entry count does not match receipt' }

if ($DestinationDirectory) {
  $destination = [IO.Path]::GetFullPath($DestinationDirectory)
  New-Item -ItemType Directory -Force -Path $destination | Out-Null
  Copy-Item -LiteralPath $indexPath -Destination (Join-Path $destination 'sage-api-index.json') -Force
  Copy-Item -LiteralPath $envelopePath -Destination (Join-Path $destination 'sage-api-index-envelope.json') -Force
  Copy-Item -LiteralPath $receiptPath -Destination (Join-Path $destination 'artifact-receipt.json') -Force
}

[pscustomobject]@{
  artifactId = [string]$envelope.artifactId
  sageVersion = [string]$index.sageVersion
  pythonVersion = [string]$index.pythonVersion
  entryCount = [int]$index.entries.Count
  sha256 = $actualHash
  destination = $DestinationDirectory
} | ConvertTo-Json -Compress
