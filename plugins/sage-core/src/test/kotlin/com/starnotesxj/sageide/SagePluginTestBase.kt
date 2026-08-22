package com.starnotesxj.sageide

import com.intellij.testFramework.fixtures.BasePlatformTestCase
import java.nio.file.Paths

abstract class SagePluginTestBase : BasePlatformTestCase() {
    override fun getTestDataPath(): String = Paths.get("src", "test", "resources").toAbsolutePath().toString()
}
