package com.starnotesxj.sageide.completion

import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SageApiIndexServiceTest : SagePluginTestBase() {
    private val memberKinds = setOf(
        SageApiSymbolKind.METHOD,
        SageApiSymbolKind.PROPERTY,
        SageApiSymbolKind.CONSTANT,
    )
    fun testConfiguredExternalIndexIsAuthoritativeAndExposesState() {
        val fixture = javaClass.classLoader.getResourceAsStream("sage-api-index.json")
            ?: error("bundled sage-api-index.json is missing")
        val temporary = Files.createTempFile("sage-api-index-service-", ".json")
        try {
            val bytes = fixture.use { it.readBytes() }
            Files.write(temporary, bytes)
            val service = SageApiIndexService.getInstance()
            val previousProperty = System.getProperty(SageApiIndexService.INDEX_PATH_PROPERTY)
            // Environment variables cannot be safely mutated in a test; use the
            // property path, which is the product's explicit JVM configuration.
            try {
                System.setProperty(SageApiIndexService.INDEX_PATH_PROPERTY, temporary.toString())
                assertTrue(service.reloadConfigured())
                val state = service.loadState()
                assertEquals(SageApiIndexOrigin.EXTERNAL, state.origin)
                assertEquals(temporary.toAbsolutePath().normalize(), state.path)
                assertEquals(1, state.schemaVersion)
                assertEquals("10.6", state.sageVersion)
                assertEquals("3.11", state.pythonVersion)
                assertEquals("sage-api-index-py/0.1", state.generatorVersion)
                assertEquals(8, state.sourceDigestCount)
                assertEquals(setOf("STUB"), state.sourceKinds)
                assertEquals(45, state.entryCount)
                assertEquals(temporary.toFile().length(), state.sizeBytes)
                assertNotNull(service.query())

                System.setProperty(
                    SageApiIndexService.INDEX_PATH_PROPERTY,
                    temporary.resolveSibling("missing-index.json").toString(),
                )
                assertFalse(service.reloadConfigured())
                assertEquals(SageApiIndexOrigin.UNAVAILABLE, service.loadState().origin)
                assertEquals(null, service.query())
            } finally {
                if (previousProperty == null) System.clearProperty(SageApiIndexService.INDEX_PATH_PROPERTY)
                else System.setProperty(SageApiIndexService.INDEX_PATH_PROPERTY, previousProperty)
                service.install(null)
            }
        } finally {
            Files.deleteIfExists(temporary)
        }
    }

    fun testOversizedExternalIndexIsRejectedBeforeParsing() {
        val temporary = Files.createTempFile("sage-api-index-oversized-", ".json")
        try {
            java.io.RandomAccessFile(temporary.toFile(), "rw").use { it.setLength(SageApiIndexService.MAX_EXTERNAL_INDEX_BYTES + 1) }
            val service = SageApiIndexService.getInstance()
            assertFalse(service.reload(temporary))
            val state = service.loadState()
            assertEquals(SageApiIndexOrigin.UNAVAILABLE, state.origin)
            assertEquals(SageApiIndexService.MAX_EXTERNAL_INDEX_BYTES + 1, state.sizeBytes)
            assertTrue(state.error?.contains("maximum supported size") == true)
            assertEquals(null, service.query())
        } finally {
            Files.deleteIfExists(temporary)
        }
    }

    /**
     * Opt-in integration probe for the ignored real Sage artifact. It never
     * discovers a path: callers must pass -Psage.external.fullIndex=<file>.
     */
    fun testConfiguredRealFullIndexLoadsAndResolvesRepresentativeSymbols() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            if (!service.reload(path)) error(service.loadState().error ?: "external full index load failed without diagnostics")
            val state = service.loadState()
            assertEquals(SageApiIndexOrigin.EXTERNAL, state.origin)
            assertEquals(path.toAbsolutePath().normalize(), state.path)
            assertEquals("10.9", state.sageVersion)
            assertEquals("3.13", state.pythonVersion)
            assertEquals(2_839, state.sourceDigestCount)
            assertEquals(setOf("STUB"), state.sourceKinds)
            assertEquals(84_159, state.entryCount)

            val query = requireNotNull(service.query())
            val unresolved = query.index.entries.asSequence()
                .filter { entry -> query.find(entry.qualifiedName, entry.kind) == null }
                .map { entry -> "${entry.kind}:${entry.qualifiedName}" }
                .take(10)
                .toList()
            assertTrue(unresolved.isEmpty(), "Full external index exposes unresolved canonical entries: $unresolved")
            assertNotNull(query.resolve("sage.arith.misc.factor"))
            assertNotNull(query.resolve("sage.matrix.matrix2.Matrix"))
            assertNotNull(query.resolve("sage.matrix.matrix2.Matrix.solve_right"))
            assertNotNull(query.documentation("sage.matrix.matrix2.Matrix"))
            assertTrue(query.signatures("sage.matrix.matrix2.Matrix.solve_right").isNotEmpty())
            val rootEntries = query.namespaceEntries("sage.all")
            assertEquals(2_158, rootEntries.size)
            assertEquals(2_158, rootEntries.map { it.qualifiedName.substringAfterLast('.') }.distinct().size)
            assertTrue(rootEntries.any { it.qualifiedName == "sage.all.factor" })

            val memberEntries = query.index.entries.filter { it.kind in memberKinds }
            val missingFromOwnerQuery = memberEntries.asSequence()
                .filter { entry -> entry.ownerName?.let { owner -> entry !in query.members(owner) } ?: true }
                .map { entry -> "${entry.kind}:${entry.qualifiedName}" }
                .take(10)
                .toList()
            assertTrue(missingFromOwnerQuery.isEmpty(), "Full external member metadata is not queryable by owner: $missingFromOwnerQuery")

            val signed = query.index.entries.filter { it.signatures.isNotEmpty() }
            val missingSignatures = signed.asSequence()
                .filter { entry -> query.signatures(entry.qualifiedName).isEmpty() }
                .map { entry -> "${entry.kind}:${entry.qualifiedName}" }
                .take(10)
                .toList()
            assertTrue(missingSignatures.isEmpty(), "Indexed signatures are not exposed: $missingSignatures")

            val documented = query.index.entries.filter { it.documentation != null }
            val missingDocumentation = documented.asSequence()
                .filter { entry -> query.documentation(entry.qualifiedName) == null }
                .map { entry -> "${entry.kind}:${entry.qualifiedName}" }
                .take(10)
                .toList()
            assertTrue(missingDocumentation.isEmpty(), "Indexed documentation is not exposed: $missingDocumentation")

            val exactKnownReturns = query.index.entries.filter { entry ->
                entry.signatures.isNotEmpty() &&
                    entry.signatures.all { signature ->
                        signature.returnType.state.name == "KNOWN" &&
                            !signature.returnType.expression.isNullOrBlank() &&
                            '|' !in signature.returnType.expression.orEmpty()
                    } &&
                    entry.signatures.map { it.returnType.expression }.distinct().size == 1
            }
            val missingExactReturns = exactKnownReturns.asSequence()
                .filter { entry -> query.uniqueKnownReturnType(entry.qualifiedName) == null }
                .map { entry -> "${entry.kind}:${entry.qualifiedName}" }
                .take(10)
                .toList()
            assertTrue(missingExactReturns.isEmpty(), "Safe KNOWN returns are not exposed for propagation: $missingExactReturns")

            val nonExactReturns = query.index.entries.filter { entry ->
                entry.signatures.isNotEmpty() && entry !in exactKnownReturns
            }
            val fabricatedReturns = nonExactReturns.asSequence()
                .filter { entry -> query.uniqueKnownReturnType(entry.qualifiedName) != null }
                .map { entry -> "${entry.kind}:${entry.qualifiedName}" }
                .take(10)
                .toList()
            assertTrue(fabricatedReturns.isEmpty(), "DYNAMIC or UNKNOWN returns were incorrectly promoted to KNOWN: $fabricatedReturns")
        } finally {
            service.install(null)
        }
    }

    fun testManualInstallStateDoesNotClaimBundledOrExternalOrigin() {
        val resource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")
            ?: error("bundled sage-api-index.json is missing")
        val query = SageApiIndexQuery(SageApiIndexJsonReader.read(resource.bufferedReader().use { it.readText() }))
        val service = SageApiIndexService.getInstance()
        service.install(query)
        try {
            assertEquals(SageApiIndexOrigin.MANUAL, service.loadState().origin)
            assertEquals(query.index.entries.size, service.loadState().entryCount)
        } finally {
            service.install(null)
        }
    }
}
