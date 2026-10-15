package com.starnotesxj.sageide.run

import com.intellij.xdebugger.breakpoints.XBreakpointType
import com.jetbrains.python.debugger.PyBreakpointHandlerFactory
import com.starnotesxj.sageide.SagePluginTestBase
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue

class SageLineBreakpointTypeTest : SagePluginTestBase() {

    fun testSageBreakpointTypeSupportsOnlyExecutableSageLines() {
        val sageFile = myFixture.configureByText("debug.sage", "# comment\n\nvalue = 1\n")
        val pythonFile = myFixture.addFileToProject("ordinary.py", "value = 1\n")
        val type = sageBreakpointType()

        assertFalse(type.canPutAt(sageFile.virtualFile, 0, myFixture.project))
        assertFalse(type.canPutAt(sageFile.virtualFile, 1, myFixture.project))
        assertTrue(type.canPutAt(sageFile.virtualFile, 2, myFixture.project))
        assertFalse(type.canPutAt(pythonFile.virtualFile, 0, myFixture.project))
    }

    fun testPythonDebuggerLoadsSageBreakpointHandlerFactory() {
        assertTrue(
            PyBreakpointHandlerFactory.EP_NAME.extensionList
                .any { it is SageBreakpointHandlerFactory },
        )
    }

    fun testSageBreakpointTypeIsRegisteredWithXDebugger() {
        val type = sageBreakpointType()
        assertNotNull(type)
        assertTrue(type.id == SageLineBreakpointType.ID)
    }

    private fun sageBreakpointType(): SageLineBreakpointType =
        XBreakpointType.EXTENSION_POINT_NAME.extensionList
            .filterIsInstance<SageLineBreakpointType>()
            .single()
}
