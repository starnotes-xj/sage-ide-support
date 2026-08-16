package com.starnotesxj.sageide

import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.jetbrains.python.PythonLanguage
import com.starnotesxj.sageide.sugar.SageFileType

/**
 * Guards the Sage file-type registration: `.sage` files must resolve to the
 * plugin's SageFileType (own identity) while keeping the Python language, so
 * all Python-language services (completion, inspections, type inference) apply.
 */
class SageFileTypeIdentityTest : BasePlatformTestCase() {

    fun testSageResolvesToTheSageFileType() {
        assertSame(
            SageFileType.INSTANCE,
            FileTypeManager.getInstance().getFileTypeByFileName("a.sage"),
        )
        assertSame(
            SageFileType.INSTANCE,
            FileTypeManager.getInstance().getFileTypeByExtension("sage"),
        )
    }

    fun testSageFileKeepsThePythonLanguage() {
        val file = myFixture.configureByText("sample.sage", "")
        assertSame(SageFileType.INSTANCE, file.fileType)
        assertEquals(PythonLanguage.INSTANCE, file.language)
    }

    fun testPythonFilesAreUntouched() {
        assertSame(
            com.jetbrains.python.PythonFileType.INSTANCE,
            FileTypeManager.getInstance().getFileTypeByFileName("a.py"),
        )
    }
}
