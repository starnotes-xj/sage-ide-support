// Copyright 2026 SageMath CTF IDE contributors.
// Distributed under the Apache License, Version 2.0, together with the product source.
package org.jetbrains.intellij.build.pycharm

import kotlinx.collections.immutable.persistentListOf
import kotlinx.collections.immutable.persistentMapOf
import kotlinx.collections.immutable.persistentSetOf
import kotlinx.collections.immutable.plus
import kotlinx.collections.immutable.toPersistentList
import com.intellij.platform.buildScripts.licenses.SoftwareBillOfMaterials
import com.intellij.platform.buildScripts.licenses.SoftwareBillOfMaterials.Companion.Suppliers
import org.jetbrains.intellij.build.ApplicationInfoProperties
import org.jetbrains.intellij.build.BuildContext
import org.jetbrains.intellij.build.FileAssociation
import org.jetbrains.intellij.build.JvmArchitecture
import org.jetbrains.intellij.build.LinuxDistributionCustomizer
import org.jetbrains.intellij.build.MacDistributionCustomizer
import org.jetbrains.intellij.build.OsFamily
import org.jetbrains.intellij.build.WindowsDistributionCustomizer
import org.jetbrains.intellij.build.impl.qodana.QodanaProductProperties
import org.jetbrains.intellij.build.io.copyFileToDir
import org.jetbrains.intellij.build.knownMissingModuleDependencies
import org.jetbrains.intellij.build.productLayout.CommunityModuleSets
import org.jetbrains.intellij.build.productLayout.CommunityProductFragments
import org.jetbrains.intellij.build.productLayout.ProductModulesContentSpec
import org.jetbrains.intellij.build.productLayout.productModules
import org.jetbrains.intellij.build.windowsCustomizer
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

/**
 * SageMath CTF IDE Community product built on PyCharm Community modules.
 *
 * This class is copied into the staged Community checkout by the product build script.
 * Python and SageMath Core are bundled Community plugins. The legacy external-plugin hook
 * remains only as an explicit migration fallback for older staged trees.
 */
open class SageMathCommunityProperties(private val communityHome: Path) : PyCharmPropertiesBase(enlargeWelcomeScreen = true) {
  override val customProductCode: String
    get() = "SMC"

  override val baseFileName: String
    get() = "sage"

  init {
    platformPrefix = "PyCharmCore"
    applicationInfoModule = "intellij.pycharm.community"
    brandingResourcePaths = listOf(communityHome.resolve("python/resources"))
    customJvmMemoryOptions = persistentMapOf("-Xms" to "256m", "-Xmx" to "1500m")
    scrambleMainJar = false
    buildSourcesArchive = true
    imagesDirectoryPath = communityHome.resolve("python/build/images")

    productLayout.productImplementationModules = listOf(
      "intellij.platform.starter",
      "intellij.pycharm.community",
    )
    // Keep staged packaging bounded to the explicit Sage/Python plugin set.
    productLayout.pluginModulesToPublish = persistentSetOf()
    productLayout.bundledPluginModules = persistentListOf(
      "intellij.java.aetherDependencyResolver.plugin",
      "intellij.jcef.plugin",
      "intellij.libraries.misc.plugin",
      "intellij.platform.bookmarks.plugin",
      "intellij.grid.core.plugin",
      "intellij.platform.navbar.plugin",
      "intellij.platform.problemView.plugin",
      "intellij.platform.testRunner.plugin",
      "intellij.platform.recentFiles.plugin",
      "intellij.platform.structuralSearch.plugin",
      "intellij.platform.structureView.plugin",
      "intellij.platform.tasks.plugin",
      "intellij.platform.execution.serviceView.plugin",
      "intellij.platform.todo.plugin",
      "intellij.platform.vcs.plugin",
      "intellij.platform.images",
      "intellij.python.community.plugin",
      "intellij.pycharm.community.customization",
      "intellij.pycharm.community.customization.shared",
      "intellij.sagemath.ctf.sage-core",
      "intellij.vcs.github",
      "intellij.vcs.gitlab",
    )

    productLayout.pluginLayouts = productLayout.pluginLayouts
      .filter { it.mainModule in productLayout.bundledPluginModules }
      .filterNot { it.mainModule.startsWith("intellij.android.") }
      .toPersistentList()

    productLayout.skipUnresolvedContentModules = true
    // The Sage product declares its bundled plugins explicitly. Do not launch a
    // nested dev IDE merely to discover and build every compatible marketplace
    // plugin during the installer build.
    productLayout.buildAllCompatiblePlugins = false
    productLayout.prepareCustomPluginRepositoryForPublishedPlugins = false
    baseDownloadUrl = "https://download.jetbrains.com/python/"
    mavenArtifacts.forIdeModules = true
    additionalVmOptions = persistentListOf("-Dllm.show.ai.promotion.window.on.start=false")
    qodanaProductProperties = QodanaProductProperties("QDPYC", "Qodana Community for Python")
    sbomOptions.creator = "Organization: SageMath CTF IDE contributors"
    sbomOptions.license = SoftwareBillOfMaterials.Options.DistributionLicense(
      name = "Apache-2.0",
      text = "Apache License, Version 2.0",
      url = "https://www.apache.org/licenses/LICENSE-2.0",
      copyrightText = "Copyright 2026 SageMath CTF IDE contributors",
    )
    sbomOptions.documentNamespace = "https://sagemath-ctf-ide.invalid/spdx"
  }

  override fun getProductContentDescriptor(): ProductModulesContentSpec = productModules {
    alias("com.intellij.modules.pycharm.community")
    alias("com.intellij.modules.python-core-capable")
    alias("com.intellij.platform.ide.provisioner")
    module("intellij.platform.ide.newUiOnboarding")
    module("intellij.ide.startup.importSettings")
    moduleSet(CommunityModuleSets.ideCommon())
    moduleSet(CommunityModuleSets.rdCommon())
    include(CommunityProductFragments.pycharmCoreFragment())
    deprecatedInclude("intellij.pycharm.community", "META-INF/pycharm-core-customization.xml")
    allowMissingDependencies(knownMissingModuleDependencies)
    allowMissingDependencies("intellij.platform.commercial.dependencies")
    bundledPlugins(productLayout.bundledPluginModules)
  }

  /**
   * Legacy external injection is opt-in for older staged trees only. New product builds
   * resolve Sage Core through productLayout.bundledPluginModules and never need this hook.
   */
  override suspend fun getAdditionalPluginPaths(context: BuildContext): List<Path> {
    if (System.getProperty("sagemath.plugin.legacyExternal") != "true") return emptyList()
    val configuredPath = System.getProperty("sagemath.plugin.path")
    val pluginPath = configuredPath?.let(Path::of)
      ?: communityHome.resolve("build/sage-core-plugin/sage-core")
    require(Files.isDirectory(pluginPath)) {
      "SageMath Core plugin directory does not exist: $pluginPath"
    }
    require(Files.list(pluginPath.resolve("lib")).use { stream -> stream.anyMatch { it.fileName.toString().endsWith(".jar") } }) {
      "SageMath Core plugin has no lib/*.jar files: $pluginPath"
    }
    return listOf(pluginPath)
  }

  override suspend fun copyAdditionalFiles(targetDir: Path, context: BuildContext) {
    super.copyAdditionalFiles(targetDir, context)
    copySageApiSidecar(targetDir, context)
    copyFileToDir(context.paths.communityHomeDir.resolve("LICENSE.txt"), targetDir.resolve("license"))
    copyFileToDir(context.paths.communityHomeDir.resolve("NOTICE.txt"), targetDir.resolve("license"))
    copyFileToDir(context.paths.communityHomeDir.resolve("LICENSE.txt"), targetDir)
    copyFileToDir(context.paths.communityHomeDir.resolve("NOTICE.txt"), targetDir)
  }

  override suspend fun copyAdditionalOsSpecificFiles(runDir: Path, os: OsFamily, arch: JvmArchitecture, context: BuildContext) {
    super.copyAdditionalOsSpecificFiles(runDir, os, arch, context)
    copySageApiSidecar(runDir, context)
  }

  private fun copySageApiSidecar(targetDir: Path, context: BuildContext) {
    val configured = System.getProperty("sagemath.api.artifact")?.trim()?.takeIf { it.isNotEmpty() }
    val artifactDir = configured?.let(Path::of) ?: context.paths.communityHomeDir.resolve("sage-api/10.9")
    val index = artifactDir.resolve("sage-api-index.json")
    val envelope = artifactDir.resolve("sage-api-index-envelope.json")
    val receipt = artifactDir.resolve("artifact-receipt.json")
    val present = listOf(index, envelope, receipt).all(Files::isRegularFile)
    if (!present) {
      require(configured == null) { "Validated Sage API sidecar is missing under $artifactDir" }
      return
    }
    val target = targetDir.resolve("sage-api/10.9")
    Files.createDirectories(target)
    for (source in listOf(index, envelope, receipt)) {
      Files.copy(source, target.resolve(source.fileName), StandardCopyOption.REPLACE_EXISTING)
    }
  }

  override fun createWindowsCustomizer(projectHome: Path): WindowsDistributionCustomizer = windowsCustomizer(communityHome) {
    fileAssociations = SUPPORTED_FILE_EXTENSIONS
    fullName { "SageMath CTF IDE Community" }
    installDirNameHandler { "SageMath CTF IDE" }
    useBigNsisInstaller = true
    copyAdditionalFiles { targetDir, _, context ->
      PyCharmBuildUtils.copySkeletons(context, targetDir, "skeletons-win*.zip")
      // Windows OS-specific distributions do not inherit ProductProperties.copyAdditionalFiles(distAllDir).
      copySageApiSidecar(targetDir, context)
      copyFileToDir(context.paths.communityHomeDir.resolve("LICENSE.txt"), targetDir.resolve("license"))
      copyFileToDir(context.paths.communityHomeDir.resolve("NOTICE.txt"), targetDir.resolve("license"))
      copyFileToDir(context.paths.communityHomeDir.resolve("LICENSE.txt"), targetDir)
      copyFileToDir(context.paths.communityHomeDir.resolve("NOTICE.txt"), targetDir)
    }
  }

  override fun createMacCustomizer(projectHome: Path): MacDistributionCustomizer = object : MacDistributionCustomizer() {
    init {
      bundleIdentifier = "org.sagemath.ctf.ide.community"
      fileAssociations = SUPPORTED_FILE_EXTENSIONS.map(::FileAssociation)
    }

    override fun getRootDirectoryName(appInfo: ApplicationInfoProperties, buildNumber: String): String = "SageMath CTF IDE.app"

    override suspend fun copyAdditionalFiles(context: BuildContext, targetDir: Path, arch: JvmArchitecture) {
      super.copyAdditionalFiles(context, targetDir, arch)
      PyCharmBuildUtils.copySkeletons(context, targetDir, "skeletons-mac*.zip")
    }
  }

  override fun createLinuxCustomizer(projectHome: Path): LinuxDistributionCustomizer = object : LinuxDistributionCustomizer() {
    override fun getRootDirectoryName(appInfo: ApplicationInfoProperties, buildNumber: String): String = "sage-math-ctf-ide"
  }

  override fun getSystemSelector(appInfo: ApplicationInfoProperties, buildNumber: String): String {
    return "SageMath${appInfo.majorVersion}.${appInfo.minorVersionMainPart}"
  }

  override fun getBaseArtifactName(appInfo: ApplicationInfoProperties, buildNumber: String): String = "sageMath-$buildNumber"

  override fun getOutputDirectoryName(appInfo: ApplicationInfoProperties): String = "sage-math"
}

/** Pro keeps a separate product identity so commercial modules can be added later. */
class SageMathProProperties(communityHome: Path) : SageMathCommunityProperties(communityHome) {
  override val customProductCode: String
    get() = "SMP"
}
