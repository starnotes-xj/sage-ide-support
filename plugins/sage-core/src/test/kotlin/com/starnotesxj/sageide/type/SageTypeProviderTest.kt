package com.starnotesxj.sageide.type

import com.intellij.psi.util.PsiTreeUtil
import com.starnotesxj.sageide.SagePluginTestBase
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyClassType
import kotlin.test.assertEquals
import kotlin.test.assertNull
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery

class SageTypeProviderTest : SagePluginTestBase() {

    private val provider = SageTypeProvider()

    fun testProviderDefersForNonSageFiles() {
        myFixture.configureByText("plain.py", "R.<x> = GF(2)[]\n")
        val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            .firstOrNull()!!
        assertNull(provider.getReferenceType(target, defaultContext(), null))
    }

    fun testIndexedMatrixFactoryTypesAssignedTarget() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        val index = SageApiIndexQuery(SageApiIndexJsonReader.read(indexResource.bufferedReader().use { it.readText() }))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.configureByText("matrix.sage", "from sage.matrix.matrix import matrix\nA = matrix([[1]])\n")
            myFixture.doHighlighting()
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .first { it.name == "A" }
            val type = provider.getReferenceType(target, defaultContext(), null)?.get() as? PyClassType
            assertEquals("Matrix", type?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    private fun defaultContext() = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
        myFixture.file.project,
        myFixture.file,
    )
}
