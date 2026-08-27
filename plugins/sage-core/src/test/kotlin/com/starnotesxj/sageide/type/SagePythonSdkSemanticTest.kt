package com.starnotesxj.sageide.type

import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.impl.PyBuiltinCache
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.PythonSdkPluginTestBase
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiSourceKind
import com.starnotesxj.sagemath.sageapi.SageApiSourceRef
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SagePythonSdkSemanticTest : PythonSdkPluginTestBase() {
    fun testRealPythonSdkLowersBuiltinSignatureParameters() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "sdk-root.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.all.RootFactory",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(
                                parameters = listOf(
                                    SageApiParameter("prec", SageTypeRef.known("int")),
                                    SageApiParameter("enabled", SageTypeRef.known("bool")),
                                    SageApiParameter("label", SageTypeRef.known("str")),
                                ),
                                returnType = SageTypeRef.known("sage.matrix.matrix.Matrix"),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                    SageApiEntry(
                        "sage.matrix.matrix.Matrix",
                        SageApiSymbolKind.CLASS,
                        sources = listOf(source),
                    ),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.configureByText("real-sdk-root.sage", "RootFactory<caret>")
            myFixture.doHighlighting()

            val reference = PsiTreeUtil.collectElementsOfType(
                myFixture.file,
                PyReferenceExpression::class.java,
            ).single { it.referencedName == "RootFactory" }
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            val builtins = PyBuiltinCache.getInstance(reference)
            assertTrue(
                builtins.isValid,
                "Python SDK builtin cache is invalid; sdk=${testSdk?.homePath} moduleSdk=${com.intellij.openapi.roots.ModuleRootManager.getInstance(myFixture.module).sdk?.homePath} " +
                    "fileSdk=${PyBuiltinCache.findSdkForFile(myFixture.file)?.homePath} builtins=${builtins.builtinsFile?.virtualFile?.path}",
            )
            assertNotNull(builtins.intType)
            assertNotNull(builtins.boolType)
            assertNotNull(builtins.strType)

            val callable = SageTypeProvider().getReferenceExpressionType(reference, context)
            val parameters = (callable as? PyCallableType)?.getParameters(context).orEmpty()
            assertEquals(listOf("prec", "enabled", "label"), parameters.map { it.name })
            assertEquals("int", (parameters[0].getType(context) as? PyClassType)?.name)
            assertEquals("bool", (parameters[1].getType(context) as? PyClassType)?.name)
            assertEquals("str", (parameters[2].getType(context) as? PyClassType)?.name)
            val callableType = callable as? PyCallableType
            assertNotNull(callableType)
            assertEquals(
                "Matrix",
                callableType!!.getReturnType(context).let { (it as? PyClassType)?.name },
            )
            assertTrue(
                SageStubIndex.findClassByCanonicalName(myFixture.project, "sage.matrix.matrix.Matrix") != null,
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }
}
