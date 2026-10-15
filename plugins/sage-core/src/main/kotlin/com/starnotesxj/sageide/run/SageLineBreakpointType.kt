package com.starnotesxj.sageide.run

import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.psi.PsiManager
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.text.CharArrayUtil
import com.intellij.xdebugger.breakpoints.XBreakpointHandler
import com.intellij.xdebugger.breakpoints.XLineBreakpointTypeBase
import com.jetbrains.python.debugger.AbstractLineBreakpointHandler
import com.jetbrains.python.debugger.PyBreakpointHandlerFactory
import com.jetbrains.python.debugger.PyDebugProcess
import com.jetbrains.python.debugger.PyDebuggerEditorsProvider
import com.jetbrains.python.psi.PyStatement
import com.starnotesxj.sageide.SageBundle
import com.starnotesxj.sageide.sugar.SageFileUtils

/** A Python-protocol breakpoint type whose hover eligibility is limited to Sage source files. */
class SageLineBreakpointType : XLineBreakpointTypeBase(
    ID,
    SageBundle.message("run.debug.sage.breakpoint.type"),
    PyDebuggerEditorsProvider(),
) {
    override fun canPutAt(file: VirtualFile, line: Int, project: Project): Boolean {
        if (!SageFileUtils.isSageFile(file)) return false

        val document = FileDocumentManager.getInstance().getDocument(file) ?: return false
        if (line !in 0 until document.lineCount) return false

        val psiFile = PsiManager.getInstance(project).findFile(file) ?: return false
        val lineStart = document.getLineStartOffset(line)
        val lineEnd = document.getLineEndOffset(line)
        val firstCodeOffset = CharArrayUtil.shiftForward(document.charsSequence, lineStart, " \t")
        if (firstCodeOffset >= lineEnd) return false

        val leaf = psiFile.findElementAt(firstCodeOffset) ?: return false
        return PsiTreeUtil.getParentOfType(leaf, PyStatement::class.java, false) != null
    }

    companion object {
        const val ID = "sage-line"
    }
}

/** Adds Sage line breakpoints to PyCharm's existing pydevd debugger process. */
class SageBreakpointHandlerFactory : PyBreakpointHandlerFactory() {
    override fun createBreakpointHandler(debugProcess: PyDebugProcess): XBreakpointHandler<*> =
        SageLineBreakpointHandler(debugProcess)
}

private class SageLineBreakpointHandler(debugProcess: PyDebugProcess) :
    AbstractLineBreakpointHandler(SageLineBreakpointType::class.java, debugProcess)
