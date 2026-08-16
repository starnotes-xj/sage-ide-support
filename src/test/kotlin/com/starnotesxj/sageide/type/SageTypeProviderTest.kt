package com.starnotesxj.sageide.type

import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.jetbrains.python.psi.PyTargetExpression
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer

class SageTypeProviderTest : BasePlatformTestCase() {

    private val provider = SageTypeProvider()

    fun testProviderDefersForNonSageFiles() {
        myFixture.configureByText("plain.py", "R.<x> = GF(2)[]\n")
        val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            .firstOrNull()!!
        assertNull(provider.getReferenceType(target, defaultContext(), null))
    }

    private fun defaultContext() = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
        myFixture.file.project,
        myFixture.file,
    )
}
