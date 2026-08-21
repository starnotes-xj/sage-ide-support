[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $CommunityRoot,
  [Parameter(Mandatory = $true)] [string] $OverlayRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$community = (Resolve-Path -LiteralPath $CommunityRoot).Path
$overlay = (Resolve-Path -LiteralPath $OverlayRoot).Path
$productSource = Join-Path $overlay 'product-properties/SageMathCommunityProperties.kt'
$targetDir = Join-Path $community 'python/build/src/org/jetbrains/intellij/build/pycharm'
if (-not (Test-Path -LiteralPath $productSource -PathType Leaf)) {
  throw "Missing product properties source: $productSource"
}
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Copy-Item -LiteralPath $productSource -Destination (Join-Path $targetDir 'SageMathCommunityProperties.kt') -Force

$appInfoSource = Join-Path $community 'python/ide-common/resources/idea/PyCharmCoreApplicationInfo.xml'
$appInfo = Get-Content -LiteralPath $appInfoSource -Raw
$appInfo = $appInfo.Replace('build number="PC-__BUILD__"', 'build number="SMC-__BUILD__"')
$appInfo = $appInfo.Replace('<names product="PyCharm" script="pycharm" motto="Python IDE for Professional Developers"/>', '<names product="SageMath CTF IDE" script="sage" motto="SageMath CTF development environment"/>')
Set-Content -LiteralPath $appInfoSource -Value $appInfo -Encoding UTF8

$registryPath = Join-Path $community 'build/dev-build.json'
$registry = Get-Content -LiteralPath $registryPath -Raw | ConvertFrom-Json
$sageProduct = [pscustomobject]@{
  modules = @('intellij.pycharm.community.build', 'intellij.idea.community.build.dependencies', 'intellij.platform.buildScripts')
  class = 'org.jetbrains.intellij.build.pycharm.SageMathCommunityProperties'
}
$registry.products | Add-Member -MemberType NoteProperty -Name SageMath -Value $sageProduct -Force
$registry | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $registryPath -Encoding UTF8

$buildFile = Join-Path $community 'build/BUILD.bazel'
$buildText = Get-Content -LiteralPath $buildFile -Raw
if ($buildText -notmatch 'name = "sage_math"') {
  Add-Content -LiteralPath $buildFile -Value @'

# SageMath CTF IDE product target, staged by sage-math-ctf-ide.
intellij_dev_binary_community(
    name = "sage_math",
    platform_prefix = "SageMath",
)
'@
}

$pythonBuildFile = Join-Path $community 'python/build/BUILD.bazel'
$pythonText = Get-Content -LiteralPath $pythonBuildFile -Raw
if ($pythonText -notmatch 'name = "sage_i_build_target"') {
  Add-Content -LiteralPath $pythonBuildFile -Value @'

# SageMath CTF IDE installer target, staged by sage-math-ctf-ide.
java_binary(
    name = "sage_i_build_target",
    add_opens = INTELLIJ_ADD_OPENS,
    data = ALL_COMMUNITY_TARGETS + [BAZEL_TARGETS_JSON_COMMUNITY],
    jvm_flags = [
        "-Dintellij.build.bazel.targets.json.file=$(rlocationpath %s)" % BAZEL_TARGETS_JSON_COMMUNITY,
    ],
    main_class = "SageMathCommunityInstallersBuildTarget",
    runtime_deps = [":build"],
)
'@
}

$installerSource = @'
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.jetbrains.intellij.build.BuildOptions
import org.jetbrains.intellij.build.BuildPaths.Companion.COMMUNITY_ROOT
import org.jetbrains.intellij.build.impl.buildDistributions
import org.jetbrains.intellij.build.impl.createBuildContext
import org.jetbrains.intellij.build.pycharm.SageMathCommunityProperties

object SageMathCommunityInstallersBuildTarget {
  @JvmStatic
  fun main(args: Array<String>) {
    runBlocking(Dispatchers.Default) {
      val options = BuildOptions().apply {
        incrementalCompilation = true
        useCompiledClassesFromProjectOutput = false
        buildStepsToSkip += listOf(
          BuildOptions.MAC_SIGN_STEP,
          BuildOptions.WIN_SIGN_STEP,
          BuildOptions.CROSS_PLATFORM_DISTRIBUTION_STEP,
          BuildOptions.WINDOWS_ZIP_STEP,
        )
      }
      val context = createBuildContext(
        projectHome = COMMUNITY_ROOT.communityRoot,
        productProperties = SageMathCommunityProperties(COMMUNITY_ROOT.communityRoot),
        options = options,
      )
      buildDistributions(context)
    }
  }
}
'@
Set-Content -LiteralPath (Join-Path $community 'python/build/src/SageMathCommunityInstallersBuildTarget.kt') -Value $installerSource -Encoding UTF8

Write-Output "Applied SageMath product overlay to $community"
