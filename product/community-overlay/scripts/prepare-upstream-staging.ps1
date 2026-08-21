[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $OfficialCheckout,
  [Parameter(Mandatory = $true)] [string] $StagingRoot,
  [Parameter(Mandatory = $true)] [string] $PluginZip,
  [Parameter(Mandatory = $true)] [string] $OverlayRoot,
  [string] $ExpectedCommit = 'b0001cd6c53979b384def7a1e3febe061e2ef687',
  [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Git([string[]] $Arguments) {
  & git @Arguments | ForEach-Object { Write-Host $_ }
  if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

$official = (Resolve-Path -LiteralPath $OfficialCheckout).Path
$overlay = (Resolve-Path -LiteralPath $OverlayRoot).Path
$stage = [IO.Path]::GetFullPath($StagingRoot)
if (-not [IO.Path]::IsPathFullyQualified($stage)) { throw "StagingRoot must be absolute: $stage" }

$status = (& git -C $official status --porcelain)
if ($status) { throw "Official checkout is not clean; refusing to stage it.`n$status" }
$actualCommit = (& git -C $official rev-parse HEAD).Trim()
if ($actualCommit -ne $ExpectedCommit) { throw "Unexpected official commit: $actualCommit (expected $ExpectedCommit)" }

if (Test-Path -LiteralPath $stage) {
  if (-not $Force) { throw "Staging path already exists: $stage (use -Force to replace it)" }
  if ((& git -C $stage rev-parse --is-inside-work-tree 2>$null) -eq 'true') {
    & git -C $stage worktree remove --force $stage 2>$null
  }
  Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stage) | Out-Null
& git -C $official worktree add --detach $stage $ExpectedCommit *> $null
if ($LASTEXITCODE -ne 0) { throw "git worktree add failed with exit code $LASTEXITCODE" }

try {
  & "$overlay/scripts/repair-modules-xml.ps1" -CommunityRoot $stage *> $null
  & "$overlay/scripts/prune-missing-android-labels.ps1" -CommunityRoot $stage *> $null
  & "$overlay/scripts/apply-overlay.ps1" -CommunityRoot $stage -OverlayRoot $overlay *> $null
  & "$overlay/scripts/stage-sage-plugin.ps1" -PluginZip $PluginZip -CommunityRoot $stage *> $null
  $record = [ordered]@{
    officialCheckout = $official
    stagingTree = $stage
    commit = $ExpectedCommit
    pluginZip = (Resolve-Path -LiteralPath $PluginZip).Path
    createdUtc = [DateTime]::UtcNow.ToString('O')
  }
  $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'build/sage-overlay/staging.json') -Encoding UTF8
  Write-Output $stage
}
catch {
  & git -C $official worktree remove --force $stage 2>$null
  throw
}
