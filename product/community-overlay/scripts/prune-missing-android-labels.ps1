[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $CommunityRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $CommunityRoot).Path
$androidRoot = Join-Path $root 'android'
if (Test-Path -LiteralPath $androidRoot) {
  Write-Output 'Android source tree exists; no label pruning required.'
  exit 0
}

# Remove Android .iml entries from the project model when the pinned checkout
# omits the entire Android source tree.
$moduleFile = Join-Path $root '.idea/modules.xml'
if (Test-Path -LiteralPath $moduleFile -PathType Leaf) {
  $moduleText = Get-Content -LiteralPath $moduleFile -Raw
  $moduleLines = $moduleText -split [Environment]::NewLine
  $keptModuleLines = $moduleLines | Where-Object { $_ -notmatch 'fileurl="file://\$PROJECT_DIR\$/android/' }
  $newModuleText = $keptModuleLines -join [Environment]::NewLine
  if ($newModuleText -ne $moduleText) {
    $moduleBackup = "$moduleFile.sage-android-backup"
    Copy-Item -LiteralPath $moduleFile -Destination $moduleBackup -Force
    Set-Content -LiteralPath $moduleFile -Value $newModuleText -NoNewline
    try {
      $xmlDocument = [System.Xml.XmlDocument]::new()
      $xmlDocument.Load($moduleFile)
    } catch {
      Copy-Item -LiteralPath $moduleBackup -Destination $moduleFile -Force
      throw "Android module pruning produced malformed XML: $moduleFile"
    }
  }
}

$changed = [System.Collections.Generic.List[object]]::new()
$files = @(
  Get-ChildItem -LiteralPath $root -Filter 'BUILD.bazel' -File -Recurse -Force
  Get-ChildItem -LiteralPath $root -Filter '*.bzl' -File -Recurse -Force
)
foreach ($file in $files) {
  $text = Get-Content -LiteralPath $file.FullName -Raw
  if ($text -notmatch '//android/') { continue }
  $lines = $text -split "`r?`n"
  $kept = $lines | Where-Object { $_ -notmatch '//android/' }
  $newText = $kept -join "`n"
  if ($newText -ne $text) {
    $before = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    Set-Content -LiteralPath $file.FullName -Value $newText -NoNewline
    $after = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $changed.Add([pscustomobject]@{
      path = $file.FullName.Substring($root.Length + 1).Replace('\', '/')
      removedLines = @($lines | Where-Object { $_ -match '//android/' }).Count
      beforeSha256 = $before
      afterSha256 = $after
    })
  }
}

$manifestDir = Join-Path $root 'build/sage-overlay'
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
[pscustomobject]@{
  schema = 1
  mode = 'staging-only-missing-android-labels'
  reason = 'The pinned Community checkout omits the Android source tree but retains generated BUILD references to it.'
  files = @($changed)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $manifestDir 'android-label-filter-manifest.json') -Encoding UTF8
Write-Output "Removed Android labels from $($changed.Count) staged BUILD/Bzl files."
