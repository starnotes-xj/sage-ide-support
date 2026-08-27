[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $CommunityRoot,
  [switch] $CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $CommunityRoot).Path
$modulesFile = Join-Path $root '.idea/modules.xml'
$manifestDir = Join-Path $root 'build/sage-overlay'
$manifestFile = Join-Path $manifestDir 'iml-filter-manifest.json'
if (-not (Test-Path -LiteralPath $modulesFile -PathType Leaf)) {
  throw "Missing JPS module registry: $modulesFile"
}

$originalHash = (Get-FileHash -LiteralPath $modulesFile -Algorithm SHA256).Hash
$xml = Get-Content -LiteralPath $modulesFile -Raw
try {
  $xmlDocument = [System.Xml.XmlDocument]::new()
  $xmlDocument.LoadXml($xml)
} catch {
  throw "JPS module registry is malformed before repair: $modulesFile"
}
$missing = [System.Collections.Generic.List[string]]::new()
$lines = $xml -split "`r?`n"
$kept = foreach ($line in $lines) {
  if ($line -match 'filepath="\$PROJECT_DIR\$/([^"]+\.iml)"') {
    $relative = $Matches[1].Replace('/', [IO.Path]::DirectorySeparatorChar)
    $absolute = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $absolute -PathType Leaf)) {
      $missing.Add($Matches[1])
      continue
    }
  }
  $line
}

# A pinned Community snapshot can keep an existing .iml whose module dependencies
# point at .iml files from an omitted source tree. The JPS-to-Bazel generator
# resolves these dependencies transitively, so filtering only the missing registry
# entries is insufficient. Compute the dependency-pruning closure in staging.
$moduleEntries = foreach ($line in $kept) {
  if ($line -match 'filepath="\$PROJECT_DIR\$/([^"]+\.iml)"') {
    $relative = $Matches[1].Replace('/', [IO.Path]::DirectorySeparatorChar)
    [pscustomobject]@{
      name = [IO.Path]::GetFileNameWithoutExtension($relative)
      relative = $relative
      absolute = Join-Path $root $relative
    }
  }
}
$available = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($entry in $moduleEntries) { [void]$available.Add($entry.name) }
$prunedDependencies = [System.Collections.Generic.List[object]]::new()
while ($true) {
  $round = [System.Collections.Generic.List[object]]::new()
  foreach ($entry in $moduleEntries) {
    if (-not $available.Contains($entry.name)) { continue }
    $moduleText = Get-Content -LiteralPath $entry.absolute -Raw
    $dependencies = [System.Collections.Generic.List[string]]::new()
    foreach ($match in [regex]::Matches($moduleText, '<orderEntry\s+type="module"\s+module-name="([^"]+)"')) {
      $dependency = $match.Groups[1].Value
      if (-not $available.Contains($dependency) -and -not $dependencies.Contains($dependency)) {
        $dependencies.Add($dependency)
      }
    }
    if ($dependencies.Count -gt 0) {
      $round.Add([pscustomobject]@{
        name = $entry.name
        relative = $entry.relative
        missingDependencies = @($dependencies)
      })
    }
  }
  if ($round.Count -eq 0) { break }
  foreach ($entry in $round) {
    if ($available.Remove($entry.name)) {
      $prunedDependencies.Add($entry)
    }
  }
}
$prunedNames = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($entry in $prunedDependencies) { [void]$prunedNames.Add($entry.name) }
$filteredLines = foreach ($line in $kept) {
  if ($line -match 'filepath="\$PROJECT_DIR\$/([^"]+\.iml)"') {
    $relative = $Matches[1].Replace('/', [IO.Path]::DirectorySeparatorChar)
    $name = [IO.Path]::GetFileNameWithoutExtension($relative)
    if ($prunedNames.Contains($name)) { continue }
  }
  $line
}

$manifestDir | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
$removedDueToDependencies = @($prunedDependencies | ForEach-Object {
  [pscustomobject]@{
    module = $_.name
    path = $_.relative.Replace('\', '/')
    missingDependencies = @($_.missingDependencies)
  }
})
if ($missing.Count -eq 0 -and $removedDueToDependencies.Count -eq 0) {
  [pscustomobject]@{
    schema = 1
    mode = if ($CheckOnly) { 'check' } else { 'unchanged' }
    modulesFile = '.idea/modules.xml'
    originalSha256 = $originalHash
    filteredSha256 = $originalHash
    removed = @()
    removedDueToMissingDependencies = @()
  } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestFile -Encoding UTF8
  Write-Output 'JPS module registry is complete.'
  exit 0
}

Write-Output "Missing .iml entries: $($missing.Count)"
$missing | ForEach-Object { Write-Output "  $_" }
Write-Output "Modules pruned for missing dependencies: $($removedDueToDependencies.Count)"
$removedDueToDependencies | ForEach-Object { Write-Output "  $($_.module): $($_.missingDependencies -join ', ')" }
if ($CheckOnly) {
  [pscustomobject]@{
    schema = 1
    mode = 'check'
    modulesFile = '.idea/modules.xml'
    originalSha256 = $originalHash
    filteredSha256 = $null
    removed = @($missing)
    removedDueToMissingDependencies = $removedDueToDependencies
  } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestFile -Encoding UTF8
  exit 2
}

Copy-Item -LiteralPath $modulesFile -Destination "$modulesFile.sage-backup" -Force
Set-Content -LiteralPath $modulesFile -Value ($filteredLines -join "`r`n") -NoNewline
$filteredHash = (Get-FileHash -LiteralPath $modulesFile -Algorithm SHA256).Hash
[pscustomobject]@{
  schema = 1
  mode = 'filtered-staging-only'
  modulesFile = '.idea/modules.xml'
  originalSha256 = $originalHash
  filteredSha256 = $filteredHash
  removed = @($missing)
  removedDueToMissingDependencies = $removedDueToDependencies
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestFile -Encoding UTF8
Write-Output "Filtered stale entries in $modulesFile"
Write-Output "Manifest: $manifestFile"
