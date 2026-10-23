package com.starnotesxj.sageide.completion

import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import java.nio.file.Path

/**
 * Goal C equivalence gate: the PSI-built index must feed the rich query
 * layer (members/C3, signatures, parents) the same way the JSON index did —
 * so every consumer switching data sources is behaviour-neutral.
 */
class SagePsiApiIndexFactoryTest : BasePlatformTestCase() {

    fun testFactoryFeedsRichQueryLayer() {
        val mirror = copyFixtureIntoTemp()
        val fileSystem = LocalFileSystem.getInstance()
        val refreshAndFind = fileSystem.refreshAndFindFileByNioFile(mirror)
        assertNotNull("mirror not refreshed: $mirror", refreshAndFind)

        val index = SagePsiApiIndexFactory.build(project, refreshAndFind!!, "10.9", "3.13")
        assertNotNull("index built", index)
        val query = SageApiIndexQuery(index!!)

        // Module-level function with a precise annotated return.
        val factor = query.find("sage.arith.misc.factor")
        assertNotNull("factor entry", factor)
        assertEquals(SageApiSymbolKind.FUNCTION, factor!!.kind)
        val returns = query.callReturnTypes("sage.arith.misc.factor")
        assertTrue("factor return annotated: $returns", returns.any { it.expression?.contains("Integer") == true })

        // Class parents survive the PSI round trip: EllipticCurvePoint has
        // no base in the fixture; the finite_field subclass lists it.
        val point = query.find("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint")
        assertNotNull("class entry", point)
        val pointField = query.find("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field")
        assertNotNull("subclass entry", pointField)
        // Bases resolve to fully-qualified names through the import graph —
        // the same shape the JSON index always carried, which C3 relies on.
        assertEquals(
            listOf("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint"),
            pointField!!.parents,
        )

        // Inherited members through C3: finite_field subclass exposes
        // curve/order from the base plus its own log.
        val members = query.members("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field")
        val names = members.map { it.qualifiedName.substringAfterLast('.') }.toSet()
        assertTrue("inherited curve: $names", "curve" in names)
        assertTrue("inherited order: $names", "order" in names)
        assertTrue("own log: $names", "log" in names)

        // Signatures survive the round trip.
        val signatures = query.signatures("sage.arith.misc.factor")
        assertTrue("signature present", signatures.isNotEmpty())
    }

    /** The fixture tree under testData/sage-stubs copied to a temp dir (mirror layout). */
    private fun copyFixtureIntoTemp(): Path {
        val source = javaClass.classLoader.getResource("testData/sage-stubs/sage/arith/misc.pyi")
            ?: error("fixture sage-stubs missing")
        val temp = java.nio.file.Files.createTempDirectory("sage-psi-mirror-")
        val stubRoot = Path.of(source.toURI()).parent.parent.parent // .../sage-stubs
        stubRoot.resolve("sage").toFile().copyRecursively(temp.resolve("sage").toFile(), overwrite = true)
        return temp.resolve("sage")
    }
}
