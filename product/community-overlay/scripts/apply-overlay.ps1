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

# Stage Sage Core as a first-class Community JPS/Bazel module. The external ZIP
# staging below remains available only for the explicit legacy fallback.
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $overlay '../..')).Path
$pluginSource = Join-Path $projectRoot 'plugins/sage-core'
$pluginTarget = Join-Path $community 'plugins/sage-core'
if (-not (Test-Path -LiteralPath $pluginSource -PathType Container)) {
  throw "Missing Sage Core source tree: $pluginSource"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pluginTarget) | Out-Null
Remove-Item -LiteralPath $pluginTarget -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $pluginSource -Destination $pluginTarget -Recurse -Force

# Bazel's installer aggregation compiles the plugin test library as part of the
# community target graph. Mirror the source module dependencies explicitly so
# Sage API/model/runtime test types and their Kotlin test libraries are visible.
$pluginBuildPath = Join-Path $pluginTarget 'BUILD.bazel'
$pluginBuildText = Get-Content -LiteralPath $pluginBuildPath -Raw
$testDependencyLines = @(
  '        "@lib//:kotlin-test",'
  '        "@lib//:kotlin-test-junit5",'
  '        "//platform/platform-api:ide",'
  '        "//platform/platform-api:ide_test_lib",'
  '        "//platform/projectModel-api:projectModel",'
  '        "//platform/projectModel-api:projectModel_test_lib",'
  '        "//platform/util/jdom",'
  '        "//platform/util/jdom:jdom_test_lib",'
  '        "//python/python-psi-api:psi_test_lib",'
  '        "//core/model:model",'
  '        "//core/model:model_test_lib",'
  '        "//core/runtime:runtime",'
  '        "//core/runtime:runtime_test_lib",'
  '        "//core/sage-api:sage-api",'
  '        "//core/sage-api:sage-api_test_lib",'
) -join [Environment]::NewLine
$pluginBuildText = $pluginBuildText.Replace(
  '        "//python/python-psi-api:psi_test_lib",',
  $testDependencyLines
)
Set-Content -LiteralPath $pluginBuildPath -Value $pluginBuildText -Encoding UTF8

# Stage product-owned core modules as source modules so the Community JPS/Bazel
# model can generate KtJvmInfo targets for Sage Core's formal dependencies.
foreach ($relativePath in @('core/model', 'core/runtime', 'core/sage-api')) {
  $source = Join-Path $projectRoot $relativePath
  $target = Join-Path $community $relativePath
  if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Missing product core module: $source"
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  $moduleName = switch ([IO.Path]::GetFileName($source)) {
    'model' { 'intellij.sagemath.ctf.model.iml' }
    'runtime' { 'intellij.sagemath.ctf.runtime.iml' }
    'sage-api' { 'intellij.sagemath.ctf.sage-api.iml' }
    default { throw "Unknown product core module: $source" }
  }
  foreach ($child in @('BUILD.bazel', $moduleName, 'src')) {
    $sourceChild = Join-Path $source $child
    if (-not (Test-Path -LiteralPath $sourceChild)) { throw "Missing product core module input: $sourceChild" }
    $targetChild = Join-Path $target $child
    if ((Get-Item -LiteralPath $sourceChild).PSIsContainer) {
      Copy-Item -LiteralPath $sourceChild -Destination $targetChild -Recurse -Force
    } else {
      Copy-Item -LiteralPath $sourceChild -Destination $targetChild -Force
    }
  }
}

# Keep the Bazel process launched by the installer on ASCII-only paths. Windows
# Bazel 9.1 can crash while resolving the Unicode default user.home.
# Publish plugin-content.yaml as a first-class Bazel output. The installer reads this
# metadata from the generated distribution target's parent directory; omitting it
# from DefaultInfo lets nested Bazel materialize only the package directory.
$ijPluginRulePath = Join-Path $community 'platform/build-scripts/bazel-rules/ij_plugin.bzl'
$ijPluginRuleText = Get-Content -LiteralPath $ijPluginRulePath -Raw
if ($ijPluginRuleText -notmatch 'DefaultInfo\(files = depset\(\[output_dir, content_yaml_file\]\)') {
  $ijPluginRuleText = [regex]::Replace(
    $ijPluginRuleText,
    'DefaultInfo\(files = depset\(\[output_dir\]\)\)',
    'DefaultInfo(files = depset([output_dir, content_yaml_file]))',
    1
  )
  Set-Content -LiteralPath $ijPluginRulePath -Value $ijPluginRuleText -Encoding UTF8
}

$bazelRunnerPath = Join-Path $community 'platform/build-scripts/src/org/jetbrains/intellij/build/impl/bazel/BazelRunner.kt'
$bazelRunnerText = Get-Content -LiteralPath $bazelRunnerPath -Raw
if ($bazelRunnerText -notmatch 'SAGEMATH_BAZEL_WORKSPACE_ROOT') {
  $bazelRunnerText = $bazelRunnerText.Replace(
    '  val bazelExecutable = projectHome.resolve("bazel.cmd")',
    '  val workspaceRoot = System.getenv("SAGEMATH_BAZEL_WORKSPACE_ROOT")?.takeIf { it.isNotBlank() }?.let { java.nio.file.Path.of(it) } ?: projectHome' + [Environment]::NewLine + '  val bazelExecutable = workspaceRoot.resolve("bazel.cmd")'
  ).Replace(
    '  runProcess(args, projectHome)',
    '  runProcess(args, workspaceRoot)'
  )
  Set-Content -LiteralPath $bazelRunnerPath -Value $bazelRunnerText -Encoding UTF8
}

# The upstream dev product runner publishes its classpath from an asynchronous
# child coroutine. Await the publication before constructing the runner so the
# installer does not fail with a race-dependent `newClassPath!!` NPE.
$devRunnerPath = Join-Path $community 'platform/build-scripts/src/org/jetbrains/intellij/build/productRunner/DevModeProductRunner.kt'
$devRunnerText = Get-Content -LiteralPath $devRunnerPath -Raw
if ($devRunnerText -notmatch 'SAGEMATH_AWAIT_PLATFORM_CLASSPATH') {
  $devRunnerText = $devRunnerText.Replace(
    'import kotlinx.coroutines.CoroutineScope',
    'import kotlinx.coroutines.CompletableDeferred' + [Environment]::NewLine + 'import kotlinx.coroutines.CoroutineScope'
  )
  $devRunnerText = $devRunnerText.Replace(
    '  var newClassPath: Collection<Path>? = null',
    '  // SAGEMATH_AWAIT_PLATFORM_CLASSPATH: buildProduct publishes this asynchronously.' + [Environment]::NewLine + '  val newClassPath = CompletableDeferred<Collection<Path>>()'
  ).Replace(
    '        newClassPath = classPath',
    '        newClassPath.complete(classPath)'
  ).Replace(
    '    DevModeProductRunner(context = context, homePath = runDir, classPath = newClassPath!!.map { it.toString() })',
    '    DevModeProductRunner(context = context, homePath = runDir, classPath = newClassPath.await().map { it.toString() })'
  )
  if ($devRunnerText -notmatch 'SAGEMATH_AWAIT_PLATFORM_CLASSPATH' -or $devRunnerText -notmatch 'newClassPath\.await\(\)') {
    throw "DevModeProductRunner.kt patch context not found: $devRunnerPath"
  }
  Set-Content -LiteralPath $devRunnerPath -Value $devRunnerText -Encoding UTF8
}
if ($bazelRunnerText -notmatch 'SAGEMATH_BAZEL_ASCII_ROOT') {
  $bazelRunnerOld = @'
  val args = mutableListOf(
    bazelExecutable.pathString,
    "build",
  )
  args.addAll(targets)
  runProcess(args, projectHome)
'@
  $bazelRunnerNew = @'
  val asciiBuildRoot = System.getenv("SAGEMATH_BAZEL_ASCII_ROOT")?.takeIf { it.isNotBlank() }
  val args = mutableListOf(
    bazelExecutable.pathString,
  )
  if (asciiBuildRoot != null) {
    val root = java.nio.file.Path.of(asciiBuildRoot)
    val userHome = root.resolve("user-home")
    val tempRoot = root.resolve("tmp")
    val appData = root.resolve("appdata")
    val localAppData = root.resolve("localappdata")
    java.nio.file.Files.createDirectories(userHome)
    java.nio.file.Files.createDirectories(tempRoot)
    java.nio.file.Files.createDirectories(appData)
    java.nio.file.Files.createDirectories(localAppData)
    args.add("--output_user_root=$root")
    args.add("--host_jvm_args=-Duser.home=$userHome")
    args.add("--host_jvm_args=-Djava.io.tmpdir=$tempRoot")
  }
  args.add("build")
  args.addAll(targets)
  runProcess(args, projectHome)
'@
  if (-not $bazelRunnerText.Contains($bazelRunnerOld)) {
    throw "BazelRunner.kt patch context not found: $bazelRunnerPath"
  }
  $bazelRunnerText = $bazelRunnerText.Replace($bazelRunnerOld, $bazelRunnerNew)
  Set-Content -LiteralPath $bazelRunnerPath -Value $bazelRunnerText -Encoding UTF8
}
elseif ($bazelRunnerText -match 'resolve\("nested-bazel"\)') {
  $bazelRunnerText = $bazelRunnerText.Replace(
    'java.nio.file.Path.of(asciiBuildRoot).resolve("nested-bazel")',
    'java.nio.file.Path.of(asciiBuildRoot)'
  )
  Set-Content -LiteralPath $bazelRunnerPath -Value $bazelRunnerText -Encoding UTF8
}

$winInstallerBuilderPath = Join-Path $community 'platform/build-scripts/src/org/jetbrains/intellij/build/impl/WinExeInstallerBuilder.kt'
$winInstallerBuilderText = Get-Content -LiteralPath $winInstallerBuilderPath -Raw
if ($winInstallerBuilderText -notmatch 'SAGEMATH_UNINSTALLER_CHECKSUMS') {
  $winInstallerOld = @'
  if (customizer.publishUninstaller) {
    val uninstallerFile = context.paths.artifactDir.resolve(uninstallerFileName)
    check(Files.exists(uninstallerFile)) { "Windows uninstaller is missing: $uninstallerFile" }
    context.notifyArtifactBuilt(uninstallerFile)
  }
'@
  $winInstallerNew = @'
  if (customizer.publishUninstaller) {
    val uninstallerFile = context.paths.artifactDir.resolve(uninstallerFileName)
    check(Files.exists(uninstallerFile)) { "Windows uninstaller is missing: $uninstallerFile" }
    // SAGEMATH_UNINSTALLER_CHECKSUMS: publish independent sidecars for the uninstaller.
    val uninstallerChecksums = Checksums.compute(
      uninstallerFile, Checksums.Algorithm.SHA256, Checksums.Algorithm.SHA512,
    )
    uninstallerChecksums.verifyOrWriteChecksumFile(Checksums.Algorithm.SHA256).also { context.notifyArtifactBuilt(it) }
    uninstallerChecksums.verifyOrWriteChecksumFile(Checksums.Algorithm.SHA512).also { context.notifyArtifactBuilt(it) }
    context.notifyArtifactBuilt(uninstallerFile)
  }
'@
  if (-not $winInstallerBuilderText.Contains($winInstallerOld)) {
    throw "WinExeInstallerBuilder.kt patch context not found: $winInstallerBuilderPath"
  }
  $winInstallerBuilderText = $winInstallerBuilderText.Replace($winInstallerOld, $winInstallerNew)
  Set-Content -LiteralPath $winInstallerBuilderPath -Value $winInstallerBuilderText -Encoding UTF8
}

$modulesFile = Join-Path $community '.idea/modules.xml'
$modulesText = Get-Content -LiteralPath $modulesFile -Raw
foreach ($moduleRelativePath in @(
  'core/model/intellij.sagemath.ctf.model.iml',
  'core/runtime/intellij.sagemath.ctf.runtime.iml',
  'core/sage-api/intellij.sagemath.ctf.sage-api.iml',
  'plugins/sage-core/intellij.sagemath.ctf.sage-core.iml'
)) {
  if ($modulesText -notmatch [regex]::Escape($moduleRelativePath)) {
    $moduleEntry = '      <module fileurl="file://$PROJECT_DIR$/' + $moduleRelativePath + '" filepath="$PROJECT_DIR$/' + $moduleRelativePath + '" />'
    $modulesText = $modulesText.Replace('    </modules>', "    $moduleEntry" + [Environment]::NewLine + "    </modules>")
  }
}
Set-Content -LiteralPath $modulesFile -Value $modulesText -Encoding UTF8

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

$stagedApiTarget = Join-Path $community 'core/sage-api'
$stagedApiFiles = @(Get-ChildItem -LiteralPath $stagedApiTarget -Recurse -File)
$emptyStagedApiFiles = @($stagedApiFiles | Where-Object { $_.Length -eq 0 -and $_.Extension -notin @('.kt', '.java', '.json', '.iml', '.bazel') })
if ($emptyStagedApiFiles) { throw "Sage API overlay contains unexpected zero-byte files: $($emptyStagedApiFiles.FullName -join ', ')" }

Write-Output "Applied SageMath product overlay to $community"
