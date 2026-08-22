package com.starnotesxj.sagemath.sageapi

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SageApiIndexTest {
    @Test
    fun normalizerBuildsVersionedIndexFromRuntimeSources() {
        val result = SageApiNormalizer().normalize(
            SageApiVersion(sage = "10.6", python = "3.11"),
            listOf(
                SageRawSymbol(
                    qualifiedName = "sage.all.RingElement",
                    kind = SageApiSymbolKind.ALIAS,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    aliases = listOf("sage.rings.ring.RingElement"),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.Integer",
                    kind = SageApiSymbolKind.CLASS,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    parents = listOf("sage.rings.ring.RingElement"),
                    documentation = SageApiDocumentation(summary = "An integer in Sage."),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.Integer.nth_root",
                    kind = SageApiSymbolKind.METHOD,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    signatures = listOf(
                        SageApiSignature(
                            parameters = listOf(
                                SageApiParameter("n", SageTypeRef.known("int")),
                                SageApiParameter("truncate", SageTypeRef.known("bool"), defaultValue = "False", optional = true),
                            ),
                            returnType = SageTypeRef.known("Integer"),
                        ),
                    ),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.factor",
                    kind = SageApiSymbolKind.FUNCTION,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    signatures = listOf(
                        SageApiSignature(
                            parameters = listOf(
                                SageApiParameter("n", SageTypeRef.known("Integer")),
                                SageApiParameter("proof", SageTypeRef.known("bool"), defaultValue = "True", optional = true),
                            ),
                            returnType = SageTypeRef.known("list[tuple[Integer, Integer]]"),
                        ),
                        SageApiSignature(
                            parameters = listOf(
                                SageApiParameter("n", SageTypeRef.known("int")),
                                SageApiParameter("proof", SageTypeRef.known("bool"), defaultValue = "True", optional = true),
                            ),
                            returnType = SageTypeRef.known("list[tuple[Integer, Integer]]"),
                        ),
                    ),
                ),
            ),
        )
        val index = result.index

        assertEquals(1, index.schemaVersion)
        assertEquals("10.6", index.sageVersion)
        assertEquals("3.11", index.pythonVersion)
        assertTrue(result.diagnostics.isEmpty(), result.diagnostics.joinToString())

        val integer = index.entry("sage.all.Integer", SageApiSymbolKind.CLASS)
        assertNotNull(integer)
        assertEquals(listOf("sage.rings.ring.RingElement"), integer.parents)
        assertEquals("An integer in Sage.", integer.documentation?.summary)

        val nthRoot = index.entry("sage.all.Integer.nth_root", SageApiSymbolKind.METHOD)
        assertNotNull(nthRoot)
        assertEquals(listOf("n", "truncate"), nthRoot.signatures.single().parameters.map { it.name })
        assertEquals("Integer", nthRoot.signatures.single().returnType.expression)

        val factor = index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION)
        assertNotNull(factor)
        assertEquals(2, factor.signatures.size)
        assertEquals("sage.rings.ring.RingElement", index.entry("sage.all.RingElement", SageApiSymbolKind.ALIAS)?.aliases?.single())
    }


    @Test
    fun extractorParsesClassesMethodsPropertiesAliasesAndOverloads() {
        val extracted = SageStubExtractor().extract(
            SageStubSource("sage.all", FIXTURE, "all.pyi"),
        )
        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), extracted)

        assertEquals(listOf("sage.rings.ring.RingElement"), result.index.entry("sage.all.RingElement", SageApiSymbolKind.ALIAS)?.aliases)
        assertEquals(listOf("sage.rings.ring.RingElement"), result.index.entry("sage.all.Integer", SageApiSymbolKind.CLASS)?.parents)
        assertEquals(SageApiSymbolKind.PROPERTY, result.index.entry("sage.all.Integer.numerator", SageApiSymbolKind.PROPERTY)?.kind)
        assertEquals(2, result.index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION)?.signatures?.size)
        assertEquals("all.pyi:4", result.index.entry("sage.all.Integer", SageApiSymbolKind.CLASS)?.sources?.single()?.locator)
    }

    @Test
    fun conflictingSameShapeSignaturesBecomeDynamicAndAreReported() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.factor",
                kind = SageApiSymbolKind.FUNCTION,
                source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("n", SageTypeRef.known("int"))),
                        returnType = SageTypeRef.known("Integer"),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.factor",
                kind = SageApiSymbolKind.FUNCTION,
                source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("n", SageTypeRef.known("int"))),
                        returnType = SageTypeRef.known("Rational"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION)
        assertNotNull(entry)
        assertEquals(1, result.diagnostics.count { it.kind == SageApiDiagnosticKind.CONFLICT })
        assertEquals(SageTypeState.DYNAMIC, entry.signatures.single().returnType.state)
        assertEquals(SageApiDynamicity.DYNAMIC, entry.dynamicity)
    }

    @Test
    fun coverageReportSeparatesMissingNoSignatureDynamicAndConflicts() {
        val result = SageApiNormalizer().normalize(
            SageApiVersion("10.6", "3.11"),
            listOf(
                SageRawSymbol(
                    qualifiedName = "sage.all.Integer",
                    kind = SageApiSymbolKind.CLASS,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.factor",
                    kind = SageApiSymbolKind.FUNCTION,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                    dynamicity = SageApiDynamicity.DYNAMIC,
                    signatures = listOf(SageApiSignature.dynamic()),
                ),
            ),
        )
        val report = SageApiCoverage.analyze(
            result.index,
            expected = listOf(
                SageApiExpectedSymbol("sage.all.Integer", SageApiSymbolKind.CLASS),
                SageApiExpectedSymbol("sage.all.factor", SageApiSymbolKind.FUNCTION),
                SageApiExpectedSymbol("sage.all.GF", SageApiSymbolKind.FUNCTION),
            ),
            normalizationDiagnostics = result.diagnostics,
        )

        assertEquals(3, report.expectedCount)
        assertEquals(2, report.coveredCount)
        assertEquals(1, report.missing.size)
        assertEquals("sage.all.GF", report.missing.single().qualifiedName)
        assertEquals(listOf("sage.all.Integer"), report.withoutSignature.map { it.qualifiedName })
        assertEquals(listOf("sage.all.factor"), report.dynamic.map { it.qualifiedName })
        assertEquals(0.6667, report.coverageRatio, 0.0001)
        assertFalse(report.isComplete)
        assertTrue(report.render().contains("missing=1"))
    }

    @Test
    fun jsonWriterIsStableAndCarriesSchemaVersion() {
        val result = SageApiNormalizer().normalize(
            SageApiVersion("10.6", "3.11"),
            listOf(
                SageRawSymbol(
                    qualifiedName = "sage.all.ZZ",
                    kind = SageApiSymbolKind.CONSTANT,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                    documentation = SageApiDocumentation(summary = "Integers"),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.GF",
                    kind = SageApiSymbolKind.FUNCTION,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                    signatures = listOf(SageApiSignature.dynamic()),
                ),
            ),
        )
        val json = SageApiIndexJsonWriter.write(result.index)

        assertTrue(json.startsWith("{\n  \"schemaVersion\": 1,"))
        assertTrue(json.indexOf("sage.all.GF") < json.indexOf("sage.all.ZZ"))
        assertTrue(json.contains("\"state\": \"DYNAMIC\""))
        assertTrue(json.contains("\"summary\": \"Integers\""))
    }

    @Test
    fun jsonReaderRoundTripsAndQueryFollowsParents() {
        val parent = SageApiEntry(
            qualifiedName = "sage.rings.RingElement",
            kind = SageApiSymbolKind.CLASS,
        )
        val child = SageApiEntry(
            qualifiedName = "sage.rings.Integer",
            kind = SageApiSymbolKind.CLASS,
            parents = listOf(parent.qualifiedName),
        )
        val method = SageApiEntry(
            qualifiedName = "sage.rings.RingElement.solve_right",
            kind = SageApiSymbolKind.METHOD,
            signatures = listOf(SageApiSignature.dynamic()),
        )
        val index = SageApiIndex("10.6", "3.11", listOf(method, child, parent))
        val loaded = SageApiIndexJsonReader.read(SageApiIndexJsonWriter.write(index))

        assertEquals(index.sageVersion, loaded.sageVersion)
        assertEquals(index.pythonVersion, loaded.pythonVersion)
        assertEquals(index.entries.toSet(), loaded.entries.toSet())
        assertTrue(SageApiIndexQuery(loaded).members("sage.rings.Integer").any { it.qualifiedName.endsWith("solve_right") })
    }

    @Test
    fun matrixFactoryAndGenericClassMembersAreQueryableWithoutMethodSpecialCases() {
        val matrix = SageApiEntry(
            qualifiedName = "sage.matrix.matrix",
            kind = SageApiSymbolKind.FUNCTION,
            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("sage.matrix.matrix.Matrix"))),
        )
        val matrixClass = SageApiEntry(
            qualifiedName = "sage.matrix.matrix.Matrix",
            kind = SageApiSymbolKind.CLASS,
            parents = listOf("sage.structure.SageObject"),
        )
        val solveRight = SageApiEntry(
            qualifiedName = "sage.matrix.matrix.Matrix.solve_right",
            kind = SageApiSymbolKind.METHOD,
        )
        val determinant = SageApiEntry(
            qualifiedName = "sage.matrix.matrix.Matrix.determinant",
            kind = SageApiSymbolKind.METHOD,
        )
        val index = SageApiIndex("10.6", "3.11", listOf(determinant, matrix, solveRight, matrixClass))
        val query = SageApiIndexQuery(index)

        assertEquals("sage.matrix.matrix.Matrix", query.callReturnTypes("sage.matrix.matrix").single().expression)
        assertEquals("sage.matrix.matrix.Matrix", query.uniqueKnownReturnType("sage.matrix.matrix")?.expression)
        assertEquals(setOf("solve_right", "determinant"), query.members("sage.matrix.matrix.Matrix").map { it.qualifiedName.substringAfterLast('.') }.toSet())
        assertEquals(SageApiSymbolKind.METHOD, query.members("sage.matrix.matrix.Matrix", "solve_right").single().kind)
    }

    @Test
    fun uniqueKnownReturnTypeRejectsDynamicOrAmbiguousReturns() {
        val function = SageApiEntry(
            qualifiedName = "sage.all.factory",
            kind = SageApiSymbolKind.FUNCTION,
            signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known("sage.all.Integer")),
                SageApiSignature(returnType = SageTypeRef.known("sage.all.Rational")),
            ),
        )
        val ambiguous = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(function)))
        assertEquals(null, ambiguous.uniqueKnownReturnType("sage.all.factory"))
        assertEquals(null, ambiguous.uniqueKnownReturnType("missing"))

        val dynamic = function.copy(signatures = listOf(SageApiSignature.dynamic()))
        val dynamicQuery = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(dynamic)))
        assertEquals(null, dynamicQuery.uniqueKnownReturnType("sage.all.factory"))
    }

    @Test
    fun resolveKnownClassNameRequiresOneCanonicalClass() {
        val unique = SageApiEntry("sage.matrix.Matrix", SageApiSymbolKind.CLASS, aliases = listOf("Matrix"))
        val uniqueQuery = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(unique)))
        assertEquals("sage.matrix.Matrix", uniqueQuery.resolveKnownClassName("Matrix"))
        assertEquals("sage.matrix.Matrix", uniqueQuery.resolveKnownClassName("sage.matrix.Matrix[Integer]"))

        val left = SageApiEntry("sage.left.Matrix", SageApiSymbolKind.CLASS)
        val right = SageApiEntry("sage.right.Matrix", SageApiSymbolKind.CLASS)
        val ambiguous = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(left, right)))
        assertEquals(null, ambiguous.resolveKnownClassName("Matrix"))
    }

    @Test
    fun uniqueKnownReturnTypeRejectsMixedKnownAndUnknownOverloads() {
        val factory = SageApiEntry(
            qualifiedName = "sage.all.factory",
            kind = SageApiSymbolKind.FUNCTION,
            signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known("sage.all.Integer")),
                SageApiSignature(returnType = SageTypeRef.unknown()),
            ),
        )
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(factory)))
        assertEquals(null, query.uniqueKnownReturnType("sage.all.factory"))
    }

    @Test
    fun jsonReaderRejectsDuplicateQualifiedNameAndKind() {
        val duplicate = """
            {
              "schemaVersion": 1,
              "sageVersion": "10.6",
              "pythonVersion": "3.11",
              "entries": [
                {"qualifiedName":"sage.all.Integer","kind":"CLASS"},
                {"qualifiedName":"sage.all.Integer","kind":"CLASS"}
              ]
            }
        """.trimIndent()
        val error = runCatching { SageApiIndexJsonReader.read(duplicate) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("duplicate qualified-name/kind"))
    }

    @Test
    fun jsonReaderRejectsKnownTypeWithoutExpression() {
        val invalid = """
            {
              "schemaVersion": 1,
              "sageVersion": "10.6",
              "pythonVersion": "3.11",
              "entries": [{
                "qualifiedName":"sage.all.factory",
                "kind":"FUNCTION",
                "signatures":[{
                  "returnType":{"state":"KNOWN","expression":null}
                }]
              }]
            }
        """.trimIndent()
        val error = runCatching { SageApiIndexJsonReader.read(invalid) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("Known Sage type references require an expression"))
    }

    @Test
    fun jsonReaderRejectsFractionalSchemaVersionAndWrongBooleanType() {
        val fractional = """{"schemaVersion":1.5,"sageVersion":"10.6","pythonVersion":"3.11","entries":[]}"""
        val fractionalError = runCatching { SageApiIndexJsonReader.read(fractional) }.exceptionOrNull()
        assertNotNull(fractionalError)
        assertTrue(fractionalError.message.orEmpty().contains("Expected integer"))

        val wrongBoolean = """{
          "schemaVersion":1,
          "sageVersion":"10.6",
          "pythonVersion":"3.11",
          "entries":[{
            "qualifiedName":"sage.all.factory",
            "kind":"FUNCTION",
            "signatures":[{
              "parameters":[{"name":"x","optional":"yes"}],
              "returnType":{"state":"UNKNOWN","expression":null}
            }]
          }]
        }"""
        val booleanError = runCatching { SageApiIndexJsonReader.read(wrongBoolean) }.exceptionOrNull()
        assertNotNull(booleanError)
        assertTrue(booleanError.message.orEmpty().contains("Expected boolean"))
    }

    @Test
    fun memberLookupPrefersChildDeclarationOverParentDeclaration() {
        val parent = SageApiEntry("sage.Parent", SageApiSymbolKind.CLASS)
        val child = SageApiEntry("sage.Child", SageApiSymbolKind.CLASS, parents = listOf("sage.Parent"))
        val parentSolve = SageApiEntry("sage.Parent.solve", SageApiSymbolKind.METHOD)
        val childSolve = SageApiEntry("sage.Child.solve", SageApiSymbolKind.METHOD)
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(parentSolve, parent, child, childSolve)))
        val result = query.members("sage.Child", "solve")
        assertEquals(1, result.size)
        assertEquals("sage.Child.solve", result.single().qualifiedName)
    }

    @Test
    fun jsonReaderRejectsDuplicateObjectKeys() {
        val duplicate = """{"schemaVersion":1,"schemaVersion":1,"sageVersion":"10.6","pythonVersion":"3.11","entries":[]}"""
        val error = runCatching { SageApiIndexJsonReader.read(duplicate) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("Duplicate JSON object key"))
    }

    @Test
    fun loaderReadsResourceAndRejectsMalformedExternalPath() {
        val loader = SageApiIndexLoader()
        val resource = loader.fromResource(javaClass.classLoader, "fixtures/index-empty.json")
        assertNotNull(resource)
        assertEquals("10.6", resource.sageVersion)
        assertEquals(null, loader.fromPath(java.nio.file.Path.of("G:/missing/sage-api-index.json")))
        assertEquals("10.6", loader.externalOrBundled(java.nio.file.Path.of("G:/missing/sage-api-index.json"), javaClass.classLoader, "fixtures/index-empty.json")?.sageVersion)
    }

    @Test
    fun qualifiedUnknownTypeDoesNotFallbackToSimpleName() {
        val matrix = SageApiEntry("sage.matrix.Matrix", SageApiSymbolKind.CLASS)
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(matrix)))
        assertEquals(null, query.resolveKnownClassName("foreign.Matrix"))
        assertEquals("sage.matrix.Matrix", query.resolveKnownClassName("Matrix"))
    }

    @Test
    fun jsonReaderRejectsUnsupportedSchema() {
        val error = runCatching {
            SageApiIndexJsonReader.read("{\"schemaVersion\": 99, \"sageVersion\": \"10\", \"pythonVersion\": \"3\", \"entries\": []}")
        }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("Unsupported Sage API schema version"))
    }

    private companion object {
        val FIXTURE = """
            from sage.rings.ring import RingElement as RingElement
            from sage.rings.integer import Integer as Integer

            class Integer(RingElement):
                /* An integer in Sage. */
                def nth_root(self, n: int, truncate: bool = False) -> Integer: ...
                @property
                def numerator(self) -> Integer: ...

            @overload
            def factor(n: Integer, proof: bool = True) -> list[tuple[Integer, Integer]]: ...
            @overload
            def factor(n: int, proof: bool = True) -> list[tuple[Integer, Integer]]: ...

            pi: RealNumber
        """.trimIndent()
    }
}
