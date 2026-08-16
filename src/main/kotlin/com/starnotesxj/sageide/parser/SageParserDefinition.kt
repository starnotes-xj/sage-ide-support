package com.starnotesxj.sageide.parser

import com.intellij.lang.PsiParser
import com.intellij.openapi.project.Project
import com.intellij.psi.tree.IFileElementType
import com.jetbrains.python.PythonParserDefinition
import com.jetbrains.python.parsing.SageParser
import com.starnotesxj.sageide.sugar.SageFileElementType

/**
 * Parser definition for the Sage dialect.  Reuses the Python parser
 * definition for everything (file PSI, element creation, comment and
 * whitespace tokens) and only swaps the parser and the file node type.
 */
class SageParserDefinition : PythonParserDefinition() {

    override fun getFileNodeType(): IFileElementType = SageFileElementType.INSTANCE

    override fun createParser(project: Project?): PsiParser = SageParser()
}
