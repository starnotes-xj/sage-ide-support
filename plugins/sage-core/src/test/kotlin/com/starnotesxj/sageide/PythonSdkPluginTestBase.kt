package com.starnotesxj.sageide

import com.intellij.openapi.projectRoots.ProjectJdkTable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.projectRoots.impl.SdkConfigurationUtil
import com.intellij.openapi.roots.ModuleRootModificationUtil
import com.jetbrains.python.sdk.PythonSdkAdditionalData
import com.jetbrains.python.sdk.PythonSdkType
import com.jetbrains.python.sdk.flavors.PyFlavorAndData
import com.jetbrains.python.sdk.flavors.PyFlavorData
import com.jetbrains.python.sdk.flavors.WinPythonSdkFlavor
import java.nio.file.Files
import java.nio.file.Path
import org.junit.Assume

/**
 * Opt-in fixture for semantic checks that require a real Python interpreter.
 *
 * Lightweight Sage PSI tests intentionally run without an SDK. This base is
 * only used by tests that explicitly receive [sage.python.testSdk], so the
 * global fixture suite remains fast and deterministic.
 */
abstract class PythonSdkPluginTestBase : SagePluginTestBase() {
    protected var testSdk: Sdk? = null

    override fun setUp() {
        super.setUp()

        val configured = System.getProperty("sage.python.testSdk")
        Assume.assumeTrue("sage.python.testSdk is not configured", !configured.isNullOrBlank())
        val executable = Path.of(configured!!).toAbsolutePath().normalize()
        Assume.assumeTrue("Python test SDK is not a regular file: $executable", Files.isRegularFile(executable))
        com.intellij.openapi.vfs.newvfs.impl.VfsRootAccess.allowRootAccess(testRootDisposable, executable.toString())

        val flavorData = createWindowsFlavorData()
        val sdk = SdkConfigurationUtil.createSdk(
            project,
            ProjectJdkTable.getInstance().allJdks.toList(),
            executable.toString(),
            PythonSdkType.getInstance(),
            PythonSdkAdditionalData(flavorData),
            null,
        )
        SdkConfigurationUtil.addSdk(sdk)
        testSdk = sdk
        ModuleRootModificationUtil.setModuleSdk(module, sdk)
        PythonSdkType.getInstance().setupSdkPaths(sdk)
    }

    override fun tearDown() {
        try {
            testSdk?.let { sdk ->
                if (ProjectJdkTable.getInstance().findJdk(sdk.name) != null) {
                    SdkConfigurationUtil.removeSdk(sdk)
                }
            }
        } finally {
            super.tearDown()
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun createWindowsFlavorData(): PyFlavorAndData<*, *> {
        val empty = Class.forName("com.jetbrains.python.sdk.flavors.PyFlavorData\$Empty")
            .getField("INSTANCE")
            .get(null) as PyFlavorData
        val flavor = WinPythonSdkFlavor.getInstance() as com.jetbrains.python.sdk.flavors.PythonSdkFlavor<PyFlavorData>
        return PyFlavorAndData(empty, flavor)
    }
}
