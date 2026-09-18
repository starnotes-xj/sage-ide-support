package com.starnotesxj.sageide.type

import com.intellij.psi.util.PsiTreeUtil
import com.intellij.psi.PsiDocumentManager
import com.intellij.codeInsight.lookup.LookupElement
import com.intellij.util.ProcessingContext
import com.starnotesxj.sageide.SagePluginTestBase
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyNamedParameter
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyType
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiTypeParameter
import com.starnotesxj.sagemath.sageapi.SageApiTypeParameterKind
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiSourceRef
import com.starnotesxj.sagemath.sageapi.SageApiSourceKind
import com.starnotesxj.sagemath.sageapi.SageApiReturnEvidence
import com.starnotesxj.sagemath.sageapi.SageApiReturnEvidenceKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery

class SageTypeProviderTest : SagePluginTestBase() {

    private val provider = SageTypeProvider()

    fun testPolynomialGeneratorArithmeticPropagatesConcreteDerivativeReceiver() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "polynomial.pyi")
        val finiteField = "sage.rings.finite_rings.finite_field_base.FiniteField"
        val finiteElement = "sage.rings.finite_rings.integer_mod.IntegerMod_int"
        val ring = "sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p"
        val polynomial = "sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(finiteField, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(finiteElement, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(ring, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(polynomial, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.GF",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(finiteField))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "sage.all.PolynomialRing",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(
                    parameters = listOf(SageApiParameter("base_ring", SageTypeRef.known(finiteField))),
                    returnType = SageTypeRef.known(ring),
                )),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$finiteField.__call__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(finiteElement))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$ring.gen",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__pow__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__mul__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__add__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.derivative",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.addFileToProject("site-packages/sage/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/finite_rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/polynomial/__init__.pyi", "")
            myFixture.addFileToProject(
                "site-packages/sage/all.pyi",
                "from sage.rings.finite_rings.finite_field_base import FiniteField\n" +
                    "from sage.rings.polynomial.polynomial_ring import PolynomialRing_dense_mod_p\n" +
                    "def GF(*args, **kwargs) -> FiniteField: ...\n" +
                    "def PolynomialRing(base_ring, *args, **kwargs) -> PolynomialRing_dense_mod_p: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/finite_field_base.pyi",
                "class FiniteField:\n" +
                    "    def __call__(self, value) -> IntegerMod_int: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/integer_mod.pyi",
                "class IntegerMod_int: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/polynomial/polynomial_ring.pyi",
                "from sage.rings.polynomial.polynomial_modn_dense_ntl import Polynomial_dense_mod_p\n" +
                    "class PolynomialRing_dense_mod_p:\n" +
                    "    def gen(self, n=0) -> Polynomial_dense_mod_p: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/polynomial/polynomial_modn_dense_ntl.pyi",
                "class Polynomial_dense_mod_p:\n" +
                    "    def __pow__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def __mul__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def __rmul__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def __add__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def derivative(self, *args) -> Polynomial_dense_mod_p: ...\n",
            )
            myFixture.configureByText(
                "polynomial-chain.sage",
                "F = GF(11)\nR.<x> = PolynomialRing(F)\nf = x^3 + F(2)*x + F(1)\nf.der<caret>ivative()\n",
            )
            myFixture.enableInspections(com.jetbrains.python.inspections.PyTypeCheckerInspection())
            val highlights = myFixture.doHighlighting()
            assertTrue(
                highlights.none { it.description?.contains("Expected type 'Polynomial_dense_mod_p'") == true },
                "Sage generator assignment was treated as Python tuple unpacking: ${highlights.mapNotNull { it.description }}",
            )
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .associateBy { it.name }
            val context = defaultContext()
            val xType = context.getType(checkNotNull(targets["x"])) as? PyClassType
            val xContextClassName = xType?.pyClass?.let(SageStubIndex::canonicalQualifiedName)
            assertEquals("x type=$xType", polynomial, xContextClassName)
            val fType = context.getType(checkNotNull(targets["f"])) as? PyClassType
            assertEquals("f type=$fType", polynomial, fType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val derivativeCall = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "derivative" }
            val derivativeType = context.getType(derivativeCall) as? PyClassType
            assertEquals("derivative return type=$derivativeType", polynomial, derivativeType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("derivative" in lookup, "polynomial completion=$lookup")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testSageNumericAssignmentReferencesUseIntegerInsteadOfPythonLiteral() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "numeric.pyi")
        val integer = "sage.rings.integer.Integer"
        val finiteField = "sage.rings.finite_rings.finite_field_base.FiniteField"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(integer, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(finiteField, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.GF",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("p", SageTypeRef.known(integer))),
                        returnType = SageTypeRef.known(finiteField),
                    ),
                ),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.addFileToProject("site-packages/sage/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/integer.pyi", "class Integer: ...\n")
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/finite_field_base.pyi",
                "class FiniteField: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/all.pyi",
                "from sage.rings.integer import Integer\n" +
                    "from sage.rings.finite_rings.finite_field_base import FiniteField\n" +
                    "def GF(p: Integer) -> FiniteField: ...\n",
            )
            myFixture.configureByText(
                "numeric-reference.sage",
                "p = 4368590184733545720227961182704359358435747188309319510520316493183539079703\n" +
                    "F = GF(p)\n" +
                    "G = GF(4368590184733545720227961182704359358435747188309319510520316493183539079703)\n",
            )
            val context = defaultContext()
            val pReference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .single { it.referencedName == "p" }
            val pType = context.getType(pReference) as? PyClassType
            assertEquals(integer, pType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val pTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "p" }
            val pTargetType = context.getType(pTarget) as? PyClassType
            assertEquals(integer, pTargetType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            myFixture.enableInspections(com.jetbrains.python.inspections.PyTypeCheckerInspection())
            val highlights = myFixture.doHighlighting()
            assertTrue(
                highlights.none { it.description?.contains("Literal[") == true },
                "Sage numeric assignment still reports a Python literal: ${highlights.mapNotNull { it.description }}",
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testFiniteFieldFactoryUnionKeepsElementMembersAvailable() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "finite-field-union.pyi")
        val givaroField = "sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro"
        val primeField = "sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn"
        val givaroElement = "sage.rings.finite_rings.element_givaro.FiniteField_givaroElement"
        val primeElement = "sage.rings.finite_rings.integer_mod.IntegerMod_int"
        val integer = "sage.rings.integer.Integer"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(givaroField, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(primeField, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(givaroElement, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(primeElement, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(integer, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.GF",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("args", variadic = true),
                            SageApiParameter(
                                "implementation",
                                SageTypeRef.known("typing.Literal[givaro]"),
                                defaultValue = "'givaro'",
                                keywordOnly = true,
                            ),
                            SageApiParameter("kwargs", keywordOnly = true, variadic = true),
                        ),
                        returnType = SageTypeRef.known(givaroField),
                    ),
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("args", variadic = true),
                            SageApiParameter("kwargs", keywordOnly = true, variadic = true),
                        ),
                        returnType = SageTypeRef.known("$givaroField | $primeField"),
                    ),
                ),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$givaroField.__call__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(givaroElement))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$primeField.__call__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(primeElement))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$givaroElement.multiplicative_order",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(integer))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$primeElement.multiplicative_order",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(integer))),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.addFileToProject("site-packages/sage/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/finite_rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/integer.pyi", "class Integer: ...\n")
            myFixture.addFileToProject(
                "site-packages/sage/all.pyi",
                "from sage.rings.finite_rings.finite_field_givaro import FiniteField_givaro\n" +
                    "def GF(*args, **kwargs) -> FiniteField_givaro: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/finite_field_givaro.pyi",
                "class FiniteField_givaro:\n    def __call__(self, value): ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/finite_field_prime_modn.pyi",
                "class FiniteField_prime_modn:\n    def __call__(self, value): ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/element_givaro.pyi",
                "class FiniteField_givaroElement: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/integer_mod.pyi",
                "class IntegerMod_int: ...\n",
            )
            myFixture.configureByText(
                "finite-field-union.sage",
                "F = GF(11)\nc = F(2)\nc.multiplicative_<caret>\n",
            )
            val context = defaultContext()
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "c" }
            val cType = context.getType(target)
            val cTypeName = cType?.name.orEmpty()
            assertTrue(cTypeName.contains("FiniteField_givaroElement"), "c lost concrete finite-field element union: $cType")
            assertTrue(cTypeName.contains("IntegerMod_int"), "c lost the prime-field element branch: $cType")
            val directVariants = cType?.getCompletionVariants("multiplicative_", myFixture.file, ProcessingContext())
                ?.filterIsInstance<LookupElement>()
                ?.map { it.lookupString }
                .orEmpty()
            assertTrue("multiplicative_order" in directVariants, "finite-field element type=$cTypeName direct=$directVariants")

            myFixture.configureByText(
                "finite-field-union-empty-member.sage",
                "F = GF(11)\nc = F(2)\nc.<caret>\n",
            )
            myFixture.doHighlighting()
            val emptyMemberTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "c" }
            val emptyMemberType = defaultContext().getType(emptyMemberTarget)
            assertTrue(
                emptyMemberType != null,
                "empty member target type=${emptyMemberType} assigned=${emptyMemberTarget.findAssignedValue()?.text} " +
                    "file=${myFixture.file.fileType.name}",
            )
            val emptyMemberLookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            val emptyMemberText = myFixture.file.text
            assertTrue(
                "multiplicative_order" in emptyMemberLookup || "multiplicative_order" in emptyMemberText,
                "empty member completion=$emptyMemberLookup text=$emptyMemberText",
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedOwnersKeepCompletionWorkingWithoutSagePsiStubs() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "finite-field-no-skeleton.pyi")
        val field = "sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro"
        val element = "sage.rings.finite_rings.element_givaro.FiniteField_givaroElement"
        val integer = "sage.rings.integer.Integer"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(field, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(element, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(integer, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.GF",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(field))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$field.__call__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(element))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$element.multiplicative_order",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(integer))),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            // Deliberately do not add any Sage `.pyi` files.  This is the
            // remote-WSL skeleton failure mode: the immutable index still
            // contains exact concrete owners and member contracts.
            myFixture.configureByText(
                "finite-field-no-skeleton.sage",
                "F = GF(11)\nc = F(2)\nc.multiplicative_<caret>\n",
            )
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "c" }
            assertEquals(
                setOf(element),
                SageIndexedTypeResolver.ownersForTarget(target),
                "index-only owner traversal must retain the concrete element class",
            )
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue(
                "multiplicative_order" in lookup || "multiplicative_order" in myFixture.file.text,
                "index-only Sage completion omitted multiplicative_order: $lookup; " +
                    "text=${myFixture.file.text}; " +
                    "fileType=${myFixture.file.fileType.name}; refs=" +
                    PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                        .joinToString { "${it.javaClass.simpleName}:${it.text}:qualified=${it.isQualified}" },
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testGenericGcdCallPropagatesConcretePolynomialReturn() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "arith-misc.pyi")
        val finiteField = "sage.rings.finite_rings.finite_field_base.FiniteField"
        val ring = "sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p"
        val polynomial = "sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(finiteField, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(ring, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(polynomial, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.GF",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(finiteField))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "sage.all.PolynomialRing",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(
                    parameters = listOf(SageApiParameter("base_ring", SageTypeRef.known(finiteField))),
                    returnType = SageTypeRef.known(ring),
                )),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$ring.gen",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__pow__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__add__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__mul__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$polynomial.__rmul__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(polynomial))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "sage.arith.misc.gcd",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("a", SageTypeRef.known("GcdT")),
                            SageApiParameter("b", SageTypeRef.known("GcdT")),
                        ),
                        returnType = SageTypeRef.known("GcdT"),
                        typeParameters = listOf(SageApiTypeParameter("GcdT", SageApiTypeParameterKind.TYPE_VARIABLE)),
                    ),
                ),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.addFileToProject("site-packages/sage/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/arith/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/finite_rings/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/rings/polynomial/__init__.pyi", "")
            myFixture.addFileToProject(
                "site-packages/sage/all.pyi",
                "from sage.rings.finite_rings.finite_field_base import FiniteField\n" +
                    "from sage.rings.polynomial.polynomial_ring import PolynomialRing_dense_mod_p\n" +
                    "from sage.arith.misc import gcd\n" +
                    "def GF(*args, **kwargs) -> FiniteField: ...\n" +
                    "def PolynomialRing(base_ring, *args, **kwargs) -> PolynomialRing_dense_mod_p: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/arith/misc.pyi",
                "from typing import TypeVar\n" +
                    "GcdT = TypeVar(\"GcdT\")\n" +
                    "def gcd(a: GcdT, b: GcdT, **kwargs) -> GcdT: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/finite_rings/finite_field_base.pyi",
                "class FiniteField: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/polynomial/polynomial_ring.pyi",
                "from sage.rings.polynomial.polynomial_modn_dense_ntl import Polynomial_dense_mod_p\n" +
                    "class PolynomialRing_dense_mod_p:\n" +
                    "    def gen(self, n=0) -> Polynomial_dense_mod_p: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/rings/polynomial/polynomial_modn_dense_ntl.pyi",
                "class Polynomial_dense_mod_p:\n" +
                    "    def __pow__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def __add__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def __mul__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def __rmul__(self, other) -> Polynomial_dense_mod_p: ...\n" +
                    "    def derivative(self, *args) -> Polynomial_dense_mod_p: ...\n",
            )
            myFixture.configureByText(
                "generic-gcd.sage",
                "F = GF(11)\nR.<x> = PolynomialRing(F)\nf = x^3 + F(2)*x + F(1)\ng = gcd(f, f.derivative())\ng.der<caret>ivative()\n",
            )
            val context = defaultContext()
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .associateBy { it.name }
            val gType = context.getType(checkNotNull(targets["g"])) as? PyClassType
            assertEquals(polynomial, gType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val gcdCall = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "gcd" }
            val gcdType = context.getType(gcdCall) as? PyClassType
            assertEquals(polynomial, gcdType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("derivative" in lookup, "generic gcd completion=$lookup")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testCtfMatrixFactoryUsesConcreteMatrix2InsteadOfMatrix0() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "matrix2.pyi")
        val matrix0 = "sage.matrix.matrix0.Matrix"
        val matrix2 = "sage.matrix.matrix2.Matrix"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(matrix0, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(matrix2, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.matrix",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(matrix2))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$matrix2.solve_right",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(matrix2))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$matrix2.determinant",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("int"))),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix0.pyi", "site-packages/sage/matrix/matrix0.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix2.pyi", "site-packages/sage/matrix/matrix2.pyi")
            myFixture.configureByText("ctf-matrix.sage", "A = matrix([[1]])\n")
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "A" }
            val type = provider.getReferenceType(target, defaultContext(), null)?.get() as? PyClassType
            assertEquals(matrix2, type?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            assertTrue(type?.pyClass?.let(SageStubIndex::canonicalQualifiedName) != matrix0)
            assertTrue(
                type != null && com.starnotesxj.sageide.completion.SageApiClassMembersProvider()
                    .getMembers(type, myFixture.file, defaultContext())
                    .map { it.name }
                    .contains("solve_right"),
                "concrete Matrix2 did not expose solve_right",
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testCtfFiniteFieldEllipticFactoryProducesFinitePoints() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "ell_finite_field.pyi")
        val finiteField = "sage.rings.finite_rings.finite_field_base.FiniteField"
        val genericCurve = "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic"
        val finiteCurve = "sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field"
        val genericPoint = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint"
        val finitePoint = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(finiteField, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(genericCurve, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(finiteCurve, SageApiSymbolKind.CLASS, parents = listOf(genericCurve), sources = listOf(source)),
            SageApiEntry(genericPoint, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(finitePoint, SageApiSymbolKind.CLASS, parents = listOf(genericPoint), sources = listOf(source)),
            SageApiEntry(
                "$finitePoint.log",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(
                    parameters = listOf(SageApiParameter("base", SageTypeRef.unknown())),
                    returnType = SageTypeRef.known("sage.rings.integer.Integer"),
                )),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$finitePoint.curve",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(finiteCurve))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "sage.all.GF",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(finiteField))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "sage.all.EllipticCurve",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("R", SageTypeRef.known(finiteField)),
                            SageApiParameter("coefficients", SageTypeRef.unknown()),
                        ),
                        returnType = SageTypeRef.known(finiteCurve),
                    ),
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("label", SageTypeRef.known("str"))),
                        returnType = SageTypeRef.known(genericCurve),
                    ),
                ),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$finiteCurve.__call__",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(
                    parameters = listOf(
                        SageApiParameter("args", SageTypeRef.unknown(), variadic = true),
                        SageApiParameter("kwargs", SageTypeRef.unknown(), variadic = true, keywordOnly = true),
                    ),
                    returnType = SageTypeRef.known(finitePoint),
                )),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$finiteCurve.gen",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(
                    parameters = listOf(SageApiParameter("i", SageTypeRef.known("int"))),
                    returnType = SageTypeRef.known(finitePoint),
                )),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/all.pyi", "site-packages/sage/all.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/rings/finite_rings/finite_field_base.pyi", "site-packages/sage/rings/finite_rings/finite_field_base.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/rings/integer.pyi", "site-packages/sage/rings/integer.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/schemes/elliptic_curves/ell_point.pyi", "site-packages/sage/schemes/elliptic_curves/ell_point.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/schemes/elliptic_curves/ell_generic.pyi", "site-packages/sage/schemes/elliptic_curves/ell_generic.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/schemes/elliptic_curves/ell_finite_field.pyi", "site-packages/sage/schemes/elliptic_curves/ell_finite_field.pyi")
            myFixture.configureByText(
                "finite-elliptic.sage",
                "E = EllipticCurve(GF(11), [1, 1])\nP = E(0, 1)\nG = E.gen(0)\nC = P.curve()\nL = P.log(G)\n",
            )
            myFixture.doHighlighting()
            val calls = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
            val ellipticCall = calls.single { it.callee?.name == "EllipticCurve" }
            val ellipticType = SageTypeLowering.lowerCallReturnType(
                index.signatures("sage.all.EllipticCurve"),
                ellipticCall,
                defaultContext(),
                index,
                "sage.all.EllipticCurve",
            ) as? PyClassType
            assertEquals("EllipticCurve overload type", finiteCurve, ellipticType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .associateBy { it.name }
            val eType = defaultContext().getType(checkNotNull(targets["E"])) as? PyClassType
            assertEquals("E type", finiteCurve, eType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            for ((name, expected) in mapOf("P" to finitePoint, "G" to finitePoint, "C" to finiteCurve)) {
                val type = defaultContext().getType(checkNotNull(targets[name])) as? PyClassType
                assertEquals("$name type", expected, type?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            }
            val logType = defaultContext().getType(checkNotNull(targets["L"])) as? PyClassType
            assertEquals("P.log(G) return type=${logType?.pyClass?.let(SageStubIndex::canonicalQualifiedName)}", "sage.rings.integer.Integer", logType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val pointType = defaultContext().getType(checkNotNull(targets["P"])) as? PyClassType
            val pointMembers = com.starnotesxj.sageide.completion.SageApiClassMembersProvider()
                .getMembers(checkNotNull(pointType), myFixture.file, defaultContext())
                .map { it.name }
            assertTrue("log" in pointMembers, "finite-field point completion=$pointMembers")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testCtfSolveRightOverloadNarrowsMatrixArgument() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "matrix2.pyi")
        val matrix = "sage.matrix.matrix2.Matrix"
        val vector = "sage.modules.free_module_element.FreeModuleElement"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(matrix, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(vector, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "sage.all.matrix",
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(matrix))),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$matrix.solve_right",
                SageApiSymbolKind.METHOD,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("B", SageTypeRef.known(vector)),
                            SageApiParameter("check", SageTypeRef.known("bool"), defaultValue = "True"),
                            SageApiParameter("extend", SageTypeRef.known("bool"), defaultValue = "True", keywordOnly = true),
                        ),
                        returnType = SageTypeRef.known(vector),
                    ),
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("B", SageTypeRef.known(matrix)),
                            SageApiParameter("check", SageTypeRef.known("bool"), defaultValue = "True"),
                            SageApiParameter("extend", SageTypeRef.known("bool"), defaultValue = "True", keywordOnly = true),
                        ),
                        returnType = SageTypeRef.known(matrix),
                    ),
                ),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix2_union.pyi", "site-packages/sage/matrix/matrix2.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/modules/free_module_element.pyi", "site-packages/sage/modules/free_module_element.pyi")
            myFixture.configureByText("ctf-solve-right.sage", "A = matrix([[1]])\nB = A.solve_right(A)\n")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "solve_right" }
            val declaration = SageStubIndex.findClassByCanonicalName(myFixture.project, matrix)
                ?.findMethodByName("solve_right", false, defaultContext())
            checkNotNull(declaration) { "Matrix.solve_right fixture declaration was not indexed" }
            // This invokes PyCharm's call-type provider directly. The active
            // stub still declares the broad union; exactness comes solely from
            // the index's documented overload contract and the type of A.
            // A light fixture project has no interpreter module resolver, so
            // its copied .pyi declaration does not receive a qualified name.
            // Production supplies that identity; preserve it here to exercise
            // the real provider/lowering call without fabricating any type.
            val indexedMethod = object : PyFunction by declaration {
                override fun getQualifiedName(): String = "$matrix.solve_right"
            }
            val type = provider.getCallType(indexedMethod, call, defaultContext())?.get() as? PyClassType
            assertEquals(matrix, type?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testRealEllipticPointReturnPropagatesToCanonicalCurveCompletion() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "ell_point.pyi")
        val point = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint"
        val curve = "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(point, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(curve, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$point.curve", SageApiSymbolKind.METHOD, signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known(curve)),
            ), sources = listOf(source)),
            SageApiEntry("$point.order", SageApiSymbolKind.METHOD, signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known("sage.rings.integer.Integer")),
            ), sources = listOf(source)),
            SageApiEntry("$curve.a_invariants", SageApiSymbolKind.METHOD, signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known("tuple")),
            ), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/schemes/elliptic_curves/ell_point.pyi", "site-packages/sage/schemes/elliptic_curves/ell_point.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/schemes/elliptic_curves/ell_generic.pyi", "site-packages/sage/schemes/elliptic_curves/ell_generic.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/rings/integer-external-only.pyi", "site-packages/sage/rings/integer.pyi")
            assertEquals(point, SageStubIndex.findClassByCanonicalName(myFixture.project, point)?.let(SageStubIndex::canonicalQualifiedName))
            assertEquals(curve, SageStubIndex.findClassByCanonicalName(myFixture.project, curve)?.let(SageStubIndex::canonicalQualifiedName))
            myFixture.configureByText("elliptic-chain.sage", "def smart_attack(P, Q, p):\n    E = P.curve()\n    E.a_invariants()\n    return P.order()\n")
            myFixture.doHighlighting()
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            val pType = provider.getParameterType(parameter, function, defaultContext())?.get() as? PyClassType
            assertEquals(point, pType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val eTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java).single { it.name == "E" }
            val eType = defaultContext().getType(eTarget) as? PyClassType
            assertEquals(curve, eType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            assertTrue(SageStubIndex.isSageStubFile(eType?.pyClass?.containingFile))
            assertTrue(index.members(curve).any { it.qualifiedName == "$curve.a_invariants" })
            assertTrue(
                SageApiIndexService.getInstance().query()?.members(curve)
                    ?.any { it.qualifiedName == "$curve.a_invariants" } == true,
            )
            assertTrue(
                eType != null && com.starnotesxj.sageide.completion.SageApiClassMembersProvider()
                    .getMembers(eType, myFixture.file, defaultContext())
                    .any { it.name == "a_invariants" },
                "indexed elliptic curve members were not materialized",
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testInheritedDirectMemberWitnessInfersUniqueOwnerParameter() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val owner = "sage.generic.owner_a.DerivedOwner"
        val baseOwner = "sage.generic.owner_a.OwnerA"
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(owner, SageApiSymbolKind.CLASS, parents = listOf(baseOwner), sources = listOf(source)),
                    SageApiEntry("sage.generic.curve.Curve", SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry(baseOwner, SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry("$baseOwner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("sage.generic.curve.Curve"))), sources = listOf(source)),
                    SageApiEntry("$baseOwner.order", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("sage.rings.integer.Integer"))), sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "site-packages/sage/generic/owner_a.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/result.pyi", "site-packages/sage/generic/result.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/curve.pyi", "site-packages/sage/generic/curve.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/rings/integer-external-only.pyi", "site-packages/sage/rings/integer.pyi")
            myFixture.configureByText(
                "owner-inference.sage",
                "def smart_attack(P, Q, p):\n    E = P.curve()\n    return P.order()\n",
            )
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            val inferred = provider.getParameterType(parameter, function, defaultContext())?.get() as? PyClassType
            assertEquals("OwnerA", inferred?.name)
            assertEquals(baseOwner, inferred?.pyClass?.let { SageStubIndex.canonicalQualifiedName(it) })
            val receiver = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .first { it.referencedName == "P" && it.parent is PyReferenceExpression }
            val receiverType = defaultContext().getType(receiver) as? PyClassType
            assertEquals("OwnerA", receiverType?.name)
            assertTrue(SageStubIndex.isSageStubFile(receiverType?.pyClass?.containingFile))
            val eTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "E" }
            val eType = defaultContext().getType(eTarget) as? PyClassType
            val directType = provider.getReferenceType(eTarget, defaultContext(), null)?.get() as? PyClassType
            assertEquals("Curve", directType?.name)
            assertEquals("sage.generic.curve.Curve", eType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            myFixture.configureByText("owner-inference.sage", "def smart_attack(P, Q, p):\n    E = P.curve()\n    E.<caret>\n    return P.order()\n")
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("curve_method" in lookup, "concrete E completion=$lookup")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testUnknownWitnessReturnCannotSelectHyperellipticOwner() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "generic.pyi")
        val ellipticOwner = "sage.generic.owner_a.OwnerA"
        val hyperellipticOwner = "sage.generic.owner_b.OwnerB"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(ellipticOwner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$ellipticOwner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("sage.generic.curve.Curve"))), sources = listOf(source)),
            SageApiEntry(hyperellipticOwner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$hyperellipticOwner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("sage.generic.curve.Curve"))), sources = listOf(source)),
            SageApiEntry("$hyperellipticOwner.order", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature(parameters = listOf(SageApiParameter("required", SageTypeRef.known("int"))), returnType = SageTypeRef.known("sage.rings.integer.Integer"))), sources = listOf(source)),
            SageApiEntry("sage.generic.curve.Curve", SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("sage.rings.integer.Integer", SageApiSymbolKind.CLASS, sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_b.pyi", "sage/generic/owner_b.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/result.pyi", "sage/generic/result.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/rings/integer-external-only.pyi", "sage/rings/integer-external-only.pyi")
            myFixture.configureByText("owner-unknown-witness.sage", "def f(P):\n    E = P.curve()\n    return P.order()\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testAmbiguousMemberWitnessOwnersFailClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "generic.pyi")
        val ownerA = "sage.generic.owner_a.OwnerA"
        val ownerB = "sage.generic.owner_b.OwnerB"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(ownerA, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$ownerA.compute", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
            SageApiEntry(ownerB, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$ownerB.compute", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_b.pyi", "sage/generic/owner_b.pyi")
            myFixture.configureByText("ambiguous.sage", "def f(x):\n    return x.compute()\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("x")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally { SageApiIndexService.getInstance().install(null) }
    }

    fun testUnequalDepthAmbiguousWitnessOwnersFailClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "generic.pyi")
        val shallowOwner = "sage.generic.owner_b.OwnerB"
        val baseOwner = "sage.generic.owner_c.BaseOwner"
        val deepOwner = "sage.generic.owner_c.DeepOwner"
        val curve = "sage.generic.curve.Curve"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(shallowOwner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "$shallowOwner.compute",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(curve))),
                sources = listOf(source),
            ),
            SageApiEntry(baseOwner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(deepOwner, SageApiSymbolKind.CLASS, parents = listOf(baseOwner), sources = listOf(source)),
            SageApiEntry(
                "$deepOwner.compute",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(curve))),
                sources = listOf(source),
            ),
            SageApiEntry(curve, SageApiSymbolKind.CLASS, sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_b.pyi", "sage/generic/owner_b.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_c.pyi", "sage/generic/owner_c.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/curve.pyi", "sage/generic/curve.pyi")
            myFixture.configureByText("ambiguous-depth.sage", "def f(x):\n    return x.compute()\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("x")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally { SageApiIndexService.getInstance().install(null) }
    }

    fun testUnannotatedMemberInferenceFailsClosedOutsideSageFiles() {
        myFixture.configureByText("plain.py", "def f(P):\n    return P.curve()\n")
        val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
        val parameter = function.parameterList.findParameterByName("P")!!
        assertNull(provider.getParameterType(parameter, function, defaultContext()))
    }

    fun testArgumentBearingMemberCallIsNotAWitness() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val owner = "sage.generic.owner_a.OwnerA"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$owner.compute", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.configureByText("argument-witness.sage", "def f(x):\n    return x.compute(1)\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("x")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally { SageApiIndexService.getInstance().install(null) }
    }

    fun testMissingIndexedOwnerFailsClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val owner = "sage.generic.owner_a.OwnerA"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry("$owner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.configureByText("missing-owner.sage", "def f(P):\n    return P.curve()\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally { SageApiIndexService.getInstance().install(null) }
    }

    fun testReassignmentBeforeMemberWitnessFailsClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val owner = "sage.generic.owner_a.OwnerA"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$owner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.configureByText("reassigned.sage", "def f(P):\n    P = other\n    return P.curve()\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally { SageApiIndexService.getInstance().install(null) }
    }

    fun testAnnotatedParameterRemainsNative() {
        myFixture.configureByText("annotated.sage", "def f(P: str):\n    return P.curve()\n")
        val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
        val parameter = function.parameterList.findParameterByName("P")!!
        assertNull(provider.getParameterType(parameter, function, defaultContext()))
    }

    fun testNestedLambdaBodyFailsClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val owner = "sage.generic.owner_a.OwnerA"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$owner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.configureByText("lambda-witness.sage", "def f(P):\n    g = lambda q: q.compute()\n    return P.curve()\n")
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            assertNull(provider.getParameterType(parameter, function, defaultContext()))
        } finally { SageApiIndexService.getInstance().install(null) }
    }

    fun testTrustedReturnEvidencePropagatesMemberAssignment() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val manifestSource = SageApiSourceRef(
            SageApiSourceKind.SIGNATURE,
            "trusted/return-evidence.json",
            "ab".repeat(32),
        )
        val owner = "sage.generic.owner_a.OwnerA"
        val result = "sage.generic.result.Result"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "$owner.curve",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(result), trustedReturnEvidence = listOf(
                    SageApiReturnEvidence(SageApiReturnEvidenceKind.TRUSTED_MANIFEST, SageTypeRef.known(result), manifestSource),
                ))),
                sources = listOf(source),
            ),
            SageApiEntry(result, SageApiSymbolKind.CLASS, sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/result.pyi", "sage/generic/result.pyi")
            myFixture.configureByText(
                "trusted-return.sage",
                "def smart_attack(P):\n    E = P.curve()\n    return E.result_method()\n",
            )
            myFixture.doHighlighting()
            val function = PsiTreeUtil.collectElementsOfType(myFixture.file, PyFunction::class.java).single()
            val parameter = function.parameterList.findParameterByName("P")!!
            val inferred = provider.getParameterType(parameter, function, defaultContext())?.get() as? PyClassType
            assertEquals("OwnerA", inferred?.name)
            val eTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "E" }
            val eType = defaultContext().getType(eTarget) as? PyClassType
            assertEquals("Result", eType?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testTrustedReturnEnablesMemberCompletion() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val manifestSource = SageApiSourceRef(
            SageApiSourceKind.SIGNATURE,
            "trusted/return-evidence.json",
            "cd".repeat(32),
        )
        val owner = "sage.generic.owner_a.OwnerA"
        val result = "sage.generic.result.Result"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                "$owner.curve",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(result), trustedReturnEvidence = listOf(
                    SageApiReturnEvidence(SageApiReturnEvidenceKind.TRUSTED_MANIFEST, SageTypeRef.known(result), manifestSource),
                ))),
                sources = listOf(source),
            ),
            SageApiEntry(result, SageApiSymbolKind.CLASS, sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/result.pyi", "sage/generic/result.pyi")
            myFixture.configureByText(
                "trusted-completion.sage",
                "def f(P):\n    E = P.curve()\n    E.result_met<caret>hod\n",
            )
            myFixture.doHighlighting()
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("result_method" in lookup, "trusted return member completion=$lookup")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testUnknownMemberReturnFailsClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "owner_a.pyi")
        val owner = "sage.generic.owner_a.OwnerA"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry("$owner.curve", SageApiSymbolKind.METHOD, signatures = listOf(SageApiSignature()), sources = listOf(source)),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/generic/owner_a.pyi", "sage/generic/owner_a.pyi")
            myFixture.configureByText(
                "unknown-return.sage",
                "def f(P):\n    E = P.curve()\n    return E\n",
            )
            myFixture.doHighlighting()
            val eTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "E" }
            val eType = defaultContext().getType(eTarget)
            assertTrue(eType !is PyClassType, "ordinary UNKNOWN member return must stay fail-closed, got $eType")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testCanonicalFactoryTypesRequireAnActiveUniqueSageStub() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "factory.pyi")
        val owner = "sage.factory.real.RealFactory"
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.all.make_real",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(returnType = SageTypeRef.known(owner)),
                        ),
                        sources = listOf(source),
                    ),
                    SageApiEntry(owner, SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.configureByText("factory-resolution.sage", "value = make_real()\nvalue.<caret>")
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "value" }
            val context = defaultContext()
            assertNull(
                SageTypeLowering.lower(SageTypeRef.known(owner), target, context, index),
                "canonical lowering must not select an unrelated short-name class",
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testBareNumericLiteralInferenceFailsClosedWithoutCanonicalStub() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "literal.pyi")
        val integer = "sage.rings.integer.Integer"
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(SageApiEntry(integer, SageApiSymbolKind.CLASS, sources = listOf(source))),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/rings/integer-external-only.pyi", "sage/rings/integer-external-only.pyi")
            myFixture.configureByText("literal.sage", "value = 2432\n")
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "value" }
            val inferred = provider.getReferenceType(target, defaultContext(), null)?.get() as? PyClassType
            assertNull(inferred, "literal inference must fail closed when no active canonical class is present")
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testProviderDefersForNonSageFiles() {
        myFixture.configureByText("plain.py", "R.<x> = GF(2)[]\n")
        val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            .firstOrNull()!!
        assertNull(provider.getReferenceType(target, defaultContext(), null))
    }

    fun testImplicitSageRootReferenceTypeIsIndexBackedOnlyInSageFiles() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "root.pyi")
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
                                parameters = emptyList(),
                                returnType = SageTypeRef.known("sage.matrix.matrix.Matrix"),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                    SageApiEntry("sage.matrix.matrix.Matrix", SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.configureByText("implicit-root.sage", "RootFactory<caret>\n")
            myFixture.doHighlighting()
            val reference = PsiTreeUtil.collectElementsOfType(
                myFixture.file,
                com.jetbrains.python.psi.PyReferenceExpression::class.java,
            ).single { it.referencedName == "RootFactory" }
            val installed = SageApiIndexService.getInstance().query()
            assertTrue(installed === index, "service query did not use synthetic index")
            val signatures = installed.signatures("sage.all.RootFactory")
            assertEquals(1, signatures.size, "synthetic root signatures missing")
            val matrixType = SageTypeLowering.lower(SageTypeRef.known("sage.matrix.matrix.Matrix"), reference, defaultContext(), index)
            assertTrue(matrixType != null, "indexed Matrix lowering failed")
            assertTrue(SageStubIndex.findClassByCanonicalName(myFixture.project, "sage.matrix.matrix.Matrix") != null, "Matrix PSI lookup failed")
            val directReturn = SageTypeLowering.lower(signatures.single().returnType, reference, defaultContext(), index)
            assertTrue(directReturn != null, "direct root return lowering failed")
            val direct = SageTypeLowering.lowerSignature(
                signatures.single().copy(parameters = emptyList()),
                reference,
                defaultContext(),
                index,
            )
            assertTrue(direct != null, "direct root signature lowering failed")
            val facadeSignatures = com.starnotesxj.sageide.completion.SageApiIntelligenceFacade.getInstance()
                .signatures("sage.all.RootFactory")
            assertEquals(1, facadeSignatures.size, "facade root signatures missing")
            val callable = provider.getReferenceExpressionType(reference, defaultContext())
            assertTrue(callable != null, "root callable type was null")
            assertTrue(callable is com.jetbrains.python.psi.types.PyCallableType)

            myFixture.configureByText(
                "implicit-root-chain.sage",
                "A = RootFactory()\nA.solve_right(A).det<caret>\n",
            )
            myFixture.doHighlighting()
            val chainTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "A" }
            val chainContext = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            assertEquals("Matrix", (chainContext.getType(chainTarget) as? PyClassType)?.name)
            val chainLookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue(
                "determinant" in chainLookup || "det" in myFixture.file.text,
                "implicit root chained completion=$chainLookup text=${myFixture.file.text}",
            )

            myFixture.configureByText("implicit-root.py", "RootFactory<caret>\n")
            myFixture.doHighlighting()
            val pythonReference = PsiTreeUtil.collectElementsOfType(
                myFixture.file,
                com.jetbrains.python.psi.PyReferenceExpression::class.java,
            ).single { it.referencedName == "RootFactory" }
            assertNull(provider.getReferenceExpressionType(pythonReference, defaultContext()))
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testExplicitSageFactoryTypesAssignedTargetInPythonFile() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        val index = SageApiIndexQuery(SageApiIndexJsonReader.read(indexResource.bufferedReader().use { it.readText() }))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix2.pyi", "sage/matrix/matrix2.pyi")
            myFixture.configureByText("matrix.py", "from sage.matrix.matrix import matrix\nA = matrix([[1]])\n")
            myFixture.doHighlighting()
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .first { it.name == "A" }
            val type = provider.getReferenceType(target, defaultContext(), null)?.get() as? PyClassType
            assertEquals("Matrix", type?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testNonSageFactoryDoesNotBorrowIndexedReturnInPythonFile() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        val index = SageApiIndexQuery(SageApiIndexJsonReader.read(indexResource.bufferedReader().use { it.readText() }))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.configureByText("matrix.py", """def matrix(rows):
    return None
A = matrix([[1]])
""")
            myFixture.doHighlighting()
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .first { it.name == "A" }
            assertNull(provider.getReferenceType(target, defaultContext(), null))
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedOverloadDispatchSelectsOnlyMatchingReturnType() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "overload.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry("sage.overload.pick", SageApiSymbolKind.FUNCTION, signatures = listOf(
                        SageApiSignature(listOf(SageApiParameter("value", SageTypeRef.known("int"))), SageTypeRef.known("sage.overload.IntegerResult")),
                        SageApiSignature(listOf(SageApiParameter("value", SageTypeRef.known("str"))), SageTypeRef.known("sage.overload.StringResult")),
                    ), sources = listOf(source)),
                    SageApiEntry("sage.overload.IntegerResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry("sage.overload.StringResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/overload/overload.pyi", "sage/overload.pyi")
            val overloadFunction = SageStubIndex.findDeclaration(myFixture.project, "pick") as? PyFunction
            checkNotNull(overloadFunction) { "overload fixture function was not indexed" }
            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(1)
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            val syntheticFunction = object : PyFunction by overloadFunction {
                override fun getQualifiedName(): String = "sage.overload.pick"
            }
            val evalContext = defaultContext()
            val type = provider.getCallType(syntheticFunction, call, evalContext)?.get() as? PyClassType
            assertEquals("IntegerResult", type?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedOverloadDispatchFailsClosedForAmbiguousArguments() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "overload.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry("sage.overload.pick", SageApiSymbolKind.FUNCTION, signatures = listOf(
                        SageApiSignature(listOf(SageApiParameter("value", SageTypeRef.unknown())), SageTypeRef.known("sage.overload.IntegerResult")),
                        SageApiSignature(listOf(SageApiParameter("value", SageTypeRef.unknown())), SageTypeRef.known("sage.overload.StringResult")),
                    ), sources = listOf(source)),
                    SageApiEntry("sage.overload.IntegerResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry("sage.overload.StringResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/overload/overload.pyi", "sage/overload.pyi")
            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(object())
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            val function = call.multiResolveCalleeFunction(com.jetbrains.python.psi.resolve.PyResolveContext.defaultContext(defaultContext()))
                .filterIsInstance<PyFunction>()
                .firstOrNull()
            assertNull(function?.let { provider.getCallType(it, call, defaultContext())?.get() })
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedOverloadDispatchHonorsKeywordOnlyDefaultsAndVariadics() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "overload.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.overload.configure",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(
                                listOf(
                                    SageApiParameter("value", SageTypeRef.known("int")),
                                    SageApiParameter("mode", SageTypeRef.known("str"), optional = true, defaultValue = "\"fast\""),
                                    SageApiParameter("limit", SageTypeRef.known("int"), keywordOnly = true, optional = true, defaultValue = "1"),
                                ),
                                SageTypeRef.known("sage.overload.IntegerResult"),
                            ),
                            SageApiSignature(
                                listOf(
                                    SageApiParameter("value", SageTypeRef.known("str")),
                                    SageApiParameter("options", SageTypeRef.known("object"), variadic = true, keywordOnly = true),
                                ),
                                SageTypeRef.known("sage.overload.StringResult"),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                    SageApiEntry("sage.overload.IntegerResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry("sage.overload.StringResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/overload/overload.pyi", "sage/overload.pyi")
            val overloadFunction = SageStubIndex.findDeclaration(myFixture.project, "configure") as? PyFunction
            checkNotNull(overloadFunction) { "configure fixture function was not indexed" }
            val syntheticFunction = object : PyFunction by overloadFunction {
                override fun getQualifiedName(): String = "sage.overload.configure"
            }

            myFixture.configureByText("overload.sage", """from sage.overload import configure
result = configure(1, limit=3)
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "configure" }
            val type = provider.getCallType(syntheticFunction, call, defaultContext())?.get() as? PyClassType
            assertEquals("IntegerResult", type?.name)

            myFixture.configureByText("overload.sage", """from sage.overload import configure
result = configure("x", debug=true)
""")
            myFixture.doHighlighting()
            val stringCall = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "configure" }
            val stringType = provider.getCallType(syntheticFunction, stringCall, defaultContext())?.get() as? PyClassType
            assertEquals("StringResult", stringType?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedOverloadRejectsMissingRequiredKeywordOnly() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "overload.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.overload.required",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(
                                listOf(
                                    SageApiParameter("value", SageTypeRef.known("int")),
                                    SageApiParameter("required", SageTypeRef.known("int"), keywordOnly = true),
                                ),
                                SageTypeRef.known("sage.overload.IntegerResult"),
                            ),
                            SageApiSignature(
                                listOf(SageApiParameter("value", SageTypeRef.known("int"))),
                                SageTypeRef.known("sage.overload.StringResult"),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                    SageApiEntry("sage.overload.IntegerResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry("sage.overload.StringResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/overload/overload.pyi", "sage/overload.pyi")
            val overloadFunction = SageStubIndex.findDeclaration(myFixture.project, "pick") as? PyFunction
            checkNotNull(overloadFunction) { "overload fixture function was not indexed" }
            val syntheticFunction = object : PyFunction by overloadFunction {
                override fun getQualifiedName(): String = "sage.overload.required"
            }
            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(1)
""")
            myFixture.doHighlighting()
            val missing = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            assertEquals("StringResult", (provider.getCallType(syntheticFunction, missing, defaultContext())?.get() as? PyClassType)?.name)

            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(1, required=2)
""")
            myFixture.doHighlighting()
            val supplied = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            assertEquals("IntegerResult", (provider.getCallType(syntheticFunction, supplied, defaultContext())?.get() as? PyClassType)?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedOverloadChecksTypedVariadicPayloads() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "overload.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.overload.variadic",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(
                                listOf(
                                    SageApiParameter("head", SageTypeRef.known("int")),
                                    SageApiParameter("items", SageTypeRef.known("int"), variadic = true),
                                ),
                                SageTypeRef.known("sage.overload.IntegerResult"),
                            ),
                            SageApiSignature(
                                listOf(
                                    SageApiParameter("head", SageTypeRef.known("str")),
                                    SageApiParameter("options", SageTypeRef.known("str"), variadic = true, keywordOnly = true),
                                ),
                                SageTypeRef.known("sage.overload.StringResult"),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                    SageApiEntry("sage.overload.IntegerResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                    SageApiEntry("sage.overload.StringResult", SageApiSymbolKind.CLASS, sources = listOf(source)),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/overload/overload.pyi", "sage/overload.pyi")
            val overloadFunction = SageStubIndex.findDeclaration(myFixture.project, "pick") as? PyFunction
            checkNotNull(overloadFunction) { "overload fixture function was not indexed" }
            val syntheticFunction = object : PyFunction by overloadFunction {
                override fun getQualifiedName(): String = "sage.overload.variadic"
            }

            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(1, 2)
""")
            myFixture.doHighlighting()
            val positional = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            assertEquals("IntegerResult", (provider.getCallType(syntheticFunction, positional, defaultContext())?.get() as? PyClassType)?.name)

            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(1, "bad")
""")
            myFixture.doHighlighting()
            val badPositional = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            assertNull(provider.getCallType(syntheticFunction, badPositional, defaultContext())?.get())

            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick("head", name=1)
""")
            myFixture.doHighlighting()
            val badKeyword = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            assertNull(provider.getCallType(syntheticFunction, badKeyword, defaultContext())?.get())

            myFixture.configureByText("overload.sage", """from sage.overload import pick
result = pick(*items)
""")
            myFixture.doHighlighting()
            val unpacked = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "pick" }
            assertNull(provider.getCallType(syntheticFunction, unpacked, defaultContext())?.get())
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testSelfReturnBindsToProvenInstanceReceiver() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "matrix.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.matrix.matrix.Matrix.fluent",
                        SageApiSymbolKind.METHOD,
                        signatures = listOf(
                            SageApiSignature(
                                parameters = listOf(SageApiParameter("value", SageTypeRef.known("Self"))),
                                returnType = SageTypeRef.known("Self"),
                                typeParameters = listOf(SageApiTypeParameter("Self", SageApiTypeParameterKind.SELF)),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            val declaration = SageStubIndex.findDeclaration(myFixture.project, "matrix") as? PyFunction
            checkNotNull(declaration)
            val syntheticFunction = object : PyFunction by declaration {
                override fun getQualifiedName(): String = "sage.matrix.matrix.Matrix.fluent"
            }
            myFixture.configureByText("self.sage", """from sage.matrix.matrix import matrix
value = matrix([[1]])
result = value.fluent(value)
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "fluent" }
            val type = provider.getCallType(syntheticFunction, call, defaultContext())?.get() as? PyClassType
            assertEquals("Matrix", type?.name)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testSelfReturnRejectsClassReceiver() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "matrix.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.matrix.matrix.Matrix.fluent",
                        SageApiSymbolKind.METHOD,
                        signatures = listOf(
                            SageApiSignature(
                                parameters = listOf(SageApiParameter("value", SageTypeRef.known("Self"))),
                                returnType = SageTypeRef.known("Self"),
                                typeParameters = listOf(SageApiTypeParameter("Self", SageApiTypeParameterKind.SELF)),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            val declaration = SageStubIndex.findDeclaration(myFixture.project, "matrix") as? PyFunction
            checkNotNull(declaration)
            val syntheticFunction = object : PyFunction by declaration {
                override fun getQualifiedName(): String = "sage.matrix.matrix.Matrix.fluent"
            }
            myFixture.configureByText("self.sage", """from sage.matrix.matrix import Matrix, matrix
result = Matrix.fluent(matrix([[1]]))
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "fluent" }
            assertNull(provider.getCallType(syntheticFunction, call, defaultContext())?.get())
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testGenericIdentityBindsAndSubstitutesTypeVariable() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "generic.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.generic.identity",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(
                                parameters = listOf(SageApiParameter("value", SageTypeRef.known("T"))),
                                returnType = SageTypeRef.known("T"),
                                typeParameters = listOf(SageApiTypeParameter("T")),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            val overloadFunction = SageStubIndex.findDeclaration(myFixture.project, "matrix") as? PyFunction
            checkNotNull(overloadFunction) { "matrix fixture function was not indexed" }
            val syntheticFunction = object : PyFunction by overloadFunction {
                override fun getQualifiedName(): String = "sage.generic.identity"
            }
            myFixture.configureByText("generic.sage", """from sage.matrix.matrix import matrix
result = identity(matrix([[1]]))
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "identity" }
            val type = provider.getCallType(syntheticFunction, call, defaultContext())?.get() as? PyClassType
            assertEquals("Matrix", type?.name)
            assertTrue(type != null)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testStoredConstructorParameterGetterBindsReceiverGenericArgument() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "box.pyi")
        val payload = "sage.all.Payload"
        val box = "sage.all.Box"
        val factory = "sage.all.make_box"
        val stored = "_SageStoredsageallBoxValueT"
        val index = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry(payload, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(box, SageApiSymbolKind.CLASS, sources = listOf(source)),
            SageApiEntry(
                factory,
                SageApiSymbolKind.FUNCTION,
                signatures = listOf(SageApiSignature(
                    returnType = SageTypeRef.known("$box[$payload]"),
                )),
                sources = listOf(source),
            ),
            SageApiEntry(
                "$box.value",
                SageApiSymbolKind.METHOD,
                signatures = listOf(SageApiSignature(
                    returnType = SageTypeRef.known(stored),
                    typeParameters = listOf(SageApiTypeParameter(stored)),
                )),
                sources = listOf(source),
            ),
        )))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.addFileToProject("site-packages/sage/__init__.pyi", "")
            myFixture.addFileToProject(
                "site-packages/sage/all.pyi",
                "from typing import Generic, TypeVar\n" +
                    "$stored = TypeVar(\"$stored\")\n" +
                    "class Payload: ...\n" +
                    "class Box(Generic[$stored]):\n" +
                    "    def __init__(self, value: $stored) -> None: ...\n" +
                    "    def value(self) -> $stored: ...\n" +
                    "def make_box() -> Box[Payload]: ...\n",
            )
            myFixture.configureByText(
                "stored-generic.sage",
                "box = make_box()\nresult = box.value()\n",
            )
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "value" }
            val receiver = (call.callee as? com.jetbrains.python.psi.PyQualifiedExpression)?.qualifier
            val receiverType = receiver?.let(defaultContext()::getType) as? PyClassType
            assertEquals(box, receiverType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            assertEquals(1, receiverType?.typeArguments?.size)
            assertEquals(payload, (receiverType?.typeArguments?.singleOrNull() as? PyClassType)?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
            val declaration = SageStubIndex.findClassByCanonicalName(myFixture.project, box)
                ?.findMethodByName("value", false, defaultContext())
            checkNotNull(declaration) { "Box.value fixture declaration was not indexed" }
            val indexedMethod = object : PyFunction by declaration {
                override fun getQualifiedName(): String = "$box.value"
            }
            val type = provider.getCallType(indexedMethod, call, defaultContext())?.get() as? PyClassType
            assertEquals(payload, type?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testGenericBoundMismatchFailsClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "generic.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex("10.9", "3.13", listOf(
                SageApiEntry(
                    "sage.generic.identity",
                    SageApiSymbolKind.FUNCTION,
                    signatures = listOf(SageApiSignature(
                        parameters = listOf(SageApiParameter("value", SageTypeRef.known("T"))),
                        returnType = SageTypeRef.known("T"),
                        typeParameters = listOf(SageApiTypeParameter("T", bound = SageTypeRef.known("int"))),
                    )),
                    sources = listOf(source),
                ),
            )),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            val declaration = SageStubIndex.findDeclaration(myFixture.project, "matrix") as? PyFunction
            checkNotNull(declaration)
            val syntheticFunction = object : PyFunction by declaration {
                override fun getQualifiedName(): String = "sage.generic.identity"
            }
            myFixture.configureByText("generic.sage", """from sage.matrix.matrix import matrix
result = matrix("not an int")
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "matrix" }
            assertNull(provider.getCallType(syntheticFunction, call, defaultContext())?.get())
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testGenericParamSpecCallFailsClosed() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "generic.pyi")
        val index = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(
                        "sage.generic.decorated",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(
                            SageApiSignature(
                                parameters = listOf(SageApiParameter("value", SageTypeRef.known("T"))),
                                returnType = SageTypeRef.known("T"),
                                typeParameters = listOf(SageApiTypeParameter("P", SageApiTypeParameterKind.PARAM_SPEC), SageApiTypeParameter("T")),
                            ),
                        ),
                        sources = listOf(source),
                    ),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            val declaration = SageStubIndex.findDeclaration(myFixture.project, "matrix") as? PyFunction
            checkNotNull(declaration)
            val syntheticFunction = object : PyFunction by declaration {
                override fun getQualifiedName(): String = "sage.generic.decorated"
            }
            myFixture.configureByText("generic.sage", """from sage.matrix.matrix import matrix
result = matrix([[1]])
""")
            myFixture.doHighlighting()
            val call = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
                .single { it.callee?.name == "matrix" }
            assertNull(provider.getCallType(syntheticFunction, call, defaultContext())?.get())
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testIndexedMatrixFactoryTypesAssignedTarget() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        val index = SageApiIndexQuery(SageApiIndexJsonReader.read(indexResource.bufferedReader().use { it.readText() }))
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix2.pyi", "sage/matrix/matrix2.pyi")
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

    fun testLiveObservedWithCategoryTypeUsesImmediateConcreteStubParent() {
        val concrete = "sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field"
        myFixture.copyFileToProject(
            "testData/sage-stubs/sage/schemes/elliptic_curves/ell_finite_field.pyi",
            "site-packages/sage/schemes/elliptic_curves/ell_finite_field.pyi",
        )

        val resolved = SageObservedTypeResolver.resolve(
            myFixture.project,
            com.starnotesxj.sagemath.runtime.SageObservedType(
                "${concrete}_with_category",
                listOf("${concrete}_with_category", concrete, "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic"),
            ),
        ) as? PyClassType

        assertEquals(concrete, resolved?.pyClass?.let(SageStubIndex::canonicalQualifiedName))
    }

    fun testLiveObservedTypeDoesNotFallBackToPublicMroBase() {
        myFixture.copyFileToProject(
            "testData/sage-stubs/sage/schemes/elliptic_curves/ell_generic.pyi",
            "site-packages/sage/schemes/elliptic_curves/ell_generic.pyi",
        )

        val resolved = SageObservedTypeResolver.resolve(
            myFixture.project,
            com.starnotesxj.sagemath.runtime.SageObservedType(
                "sage.runtime_only.SpecializedCurve",
                listOf(
                    "sage.runtime_only.SpecializedCurve",
                    "sage.runtime_only.UnstubbedParent",
                    "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic",
                ),
            ),
        )

        assertNull(resolved)
    }

    fun testLiveSnapshotDemandIsLimitedToTopLevelMemberReceivers() {
        myFixture.configureByText(
            "probe-policy.sage",
            """P = dynamically_created_point()
P.log()
def local(T):
    T.log()
""",
        )
        val references = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
        val topLevelReceiver = references.single { it.referencedName == "P" }
        val functionReceiver = references.single { it.referencedName == "T" }
        val calls = PsiTreeUtil.collectElementsOfType(myFixture.file, PyCallExpression::class.java)
        val memberCall = calls.single { it.callee?.text == "P.log" }
        val globalFactoryCall = calls.single { it.callee?.text == "dynamically_created_point" }
        val service = SageLiveTypeSnapshotService.getInstance(myFixture.project)

        assertTrue(service.acceptsMemberProbe(topLevelReceiver))
        assertFalse(service.acceptsMemberProbe(functionReceiver))
        assertTrue(service.acceptsDynamicCallProbe(memberCall))
        assertFalse(service.acceptsDynamicCallProbe(globalFactoryCall))
    }

    fun testNormalRunEvidenceSupportsWhitespaceOnlyCompletionAppend() {
        val point = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
        myFixture.copyFileToProject(
            "testData/sage-stubs/sage/schemes/elliptic_curves/ell_point.pyi",
            "site-packages/sage/schemes/elliptic_curves/ell_point.pyi",
        )
        myFixture.configureByText("run-evidence.sage", "P = dynamically_created_point()\n")
        val settings = com.starnotesxj.sageide.run.SageRunSettings.getInstance().getState()
        val originalEnabled = settings.liveTypeProbingEnabled
        val originalMode = settings.executionMode
        val originalDistribution = settings.wslDistribution
        val originalExecutable = settings.wslSageExecutable
        try {
            settings.liveTypeProbingEnabled = true
            settings.executionMode = "WSL"
            settings.wslDistribution = "EvidenceTest"
            settings.wslSageExecutable = "/opt/sage/bin/sage"
            val file = myFixture.file.virtualFile
            val digest = java.security.MessageDigest.getInstance("SHA-256")
                .digest(file.contentsToByteArray())
                .joinToString("") { byte -> "%02x".format(byte) }
            SageLiveTypeSnapshotService.getInstance(myFixture.project).recordRunEvidence(
                file,
                digest,
                myFixture.file.text,
                SageLiveTypeSnapshotService.runtimeKey(
                    com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl("EvidenceTest"),
                    "/opt/sage/bin/sage",
                ),
                mapOf(
                    "P" to com.starnotesxj.sagemath.runtime.SageObservedType(
                        point,
                        listOf(point, "sage.structure.element.Element"),
                    ),
                ),
            )
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "P" }
            val observed = provider.getReferenceType(target, defaultContext(), null)?.get() as? PyClassType
            assertEquals(point, observed?.pyClass?.let(SageStubIndex::canonicalQualifiedName))

            val document = checkNotNull(com.intellij.openapi.fileEditor.FileDocumentManager.getInstance().getDocument(file))
            com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(myFixture.project) {
                document.insertString(document.textLength, "\nP.log\n")
                PsiDocumentManager.getInstance(myFixture.project).commitDocument(document)
            }
            val appendedReference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .single { it.referencedName == "P" && it.textRange.startOffset >= target.textRange.endOffset }
            val appendedType = provider.getReferenceExpressionType(appendedReference, defaultContext()) as? PyClassType
            assertEquals(point, appendedType?.pyClass?.let(SageStubIndex::canonicalQualifiedName))

            com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(myFixture.project) {
                document.insertString(0, "# unsaved change invalidates run evidence\n")
                PsiDocumentManager.getInstance(myFixture.project).commitDocument(document)
            }
            val changedTarget = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                .single { it.name == "P" }
            assertNull(provider.getReferenceType(changedTarget, defaultContext(), null)?.get())
        } finally {
            settings.liveTypeProbingEnabled = originalEnabled
            settings.executionMode = originalMode
            settings.wslDistribution = originalDistribution
            settings.wslSageExecutable = originalExecutable
        }
    }

    private fun defaultContext() = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
        myFixture.file.project,
        myFixture.file,
    )
}
