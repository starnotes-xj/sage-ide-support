// Copyright 2026 SageMath CTF IDE contributors.
// Distributed under the Apache License, Version 2.0, together with the product source.
package org.jetbrains.intellij.build.pycharm

import kotlinx.collections.immutable.persistentListOf
import kotlinx.collections.immutable.persistentMapOf
import kotlinx.collections.immutable.plus
import kotlinx.collections.immutable.toPersistentList
import org.jetbrains.intellij.build.ApplicationInfoProperties
import org.jetbrains.intellij.build.BuildContext
import org.jetbrains.intellij.build.FileAssociation
import org.jetbrains.intellij.build.JvmArchitecture
import org.jetbrains.intellij.build.LinuxDistributionCustomizer
import org.jetbrains.intellij.build.MacDistributionCustomizer
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

/**
 * SageMath CTF IDE Community product built on PyCharm Community modules.
 *
 * This class is copied into the staged Community checkout by the product build script.
 * Python stays a bundled JetBrains plugin. SageMath Core is an external plugin during this
 * migration step, but the official product builder copies it into both dev distributions
 * and installers through [getAdditionalPluginPaths].
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
    productLayout.bundledPluginModules +=
      sequenceOf(
        "intellij.python.community.plugin",
        "intellij.pycharm.community.customization",
        "intellij.pycharm.community.customization.shared",
        "intellij.vcs.github",
        "intellij.vcs.gitlab") +
      Files.readAllLines(communityHome.resolve("python/build/plugin-list.txt"))

    productLayout.pluginLayouts = productLayout.pluginLayouts
      .filterNot { it.mainModule.startsWith("intellij.android.") }
      .toPersistentList()

    productLayout.skipUnresolvedContentModules = true
    baseDownloadUrl = "https://download.jetbrains.com/python/"
    mavenArtifacts.forIdeModules = true
    additionalVmOptions = persistentListOf("-Dllm.show.ai.promotion.window.on.start=false")
    qodanaProductProperties = QodanaProductProperties("QDPYC", "Qodana Community for Python")
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

  override suspend fun getAdditionalPluginPaths(context: BuildContext): List<Path> {
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
    copyFileToDir(context.paths.communityHomeDir.resolve("LICENSE.txt"), targetDir.resolve("license"))
    copyFileToDir(context.paths.communityHomeDir.resolve("NOTICE.txt"), targetDir.resolve("license"))
  }

  override fun createWindowsCustomizer(projectHome: Path): WindowsDistributionCustomizer = windowsCustomizer(communityHome) {
    fileAssociations = SUPPORTED_FILE_EXTENSIONS
    fullName { "SageMath CTF IDE Community" }
    installDirNameHandler { "SageMath CTF IDE" }
    copyAdditionalFiles { targetDir, _, context ->
      PyCharmBuildUtils.copySkeletons(context, targetDir, "skeletons-win*.zip")
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
