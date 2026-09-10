package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SageLiveTypeProbeTest {
    @Test
    fun `probe sends source through stdin and keeps concrete runtime class with MRO`() {
        var captured: TargetProcessRequest? = null
        val executor = RuntimeTargetExecutor { request ->
            captured = request
            val payload = checkNotNull(request.standardInput).toString(StandardCharsets.UTF_8).lines()
            val marker = payload[2]
            val runtime = Base64.getEncoder().encodeToString(
                "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field".toByteArray(),
            )
            val mro = Base64.getEncoder().encodeToString(
                "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field\u001fsage.structure.element.Element".toByteArray(),
            )
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, "$marker\tP\t$runtime\t$mro\n", "", 1, false)
        }

        val result = SageLiveTypeProbe(executor).probe(
            SageLiveTypeProbeRequest(
                RuntimeTarget.Wsl("Ubuntu"),
                "/opt/sage/bin/sage",
                "P = E(0, 1)",
                setOf("P"),
            ),
        )

        assertEquals(RuntimeExecutionStatus.SUCCESS, result.status)
        assertEquals(
            "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field",
            result.observedTypes.getValue("P").runtimeClass,
        )
        assertEquals(
            listOf(
                "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field",
                "sage.structure.element.Element",
            ),
            result.observedTypes.getValue("P").methodResolutionOrder,
        )
        val request = checkNotNull(captured)
        assertEquals("-c", request.args.firstOrNull())
        assertTrue(request.args.getOrNull(1)?.contains("from sage.repl.preparse import preparse") == true)
        assertTrue(request.standardInput?.toString(StandardCharsets.UTF_8)?.contains("P = E(0, 1)") == false)
    }

    @Test
    fun `persistent worker protocol frames source and parses one response`() {
        val query = SageLiveTypeWorkerQuery("P = E(0, 1)", setOf("P"), "sample.sage")
        val request = SageLiveTypeWorkerProtocol.requestLine("request-1", query)
        val fields = request.trimEnd('\n').split('\t')
        assertEquals("request-1", fields[0])
        assertEquals("sample.sage", String(Base64.getDecoder().decode(fields[2]), StandardCharsets.UTF_8))
        assertTrue(!fields[1].contains("P = E(0, 1)"))

        val runtime = Base64.getEncoder().encodeToString("sage.point.Point".toByteArray())
        val mro = Base64.getEncoder().encodeToString("sage.point.Point\u001fsage.structure.element.Element".toByteArray())
        val payload = Base64.getEncoder().encodeToString("P|$runtime|$mro".toByteArray())
        val response = SageLiveTypeWorkerProtocol.decodeResponse(
            "${SageLiveTypeWorkerProtocol.MAGIC}\trequest-1\tOK\t$payload",
            "request-1",
        )

        assertEquals("sage.point.Point", response?.observedTypes?.getValue("P")?.runtimeClass)
        assertEquals("sage.structure.element.Element", response?.observedTypes?.getValue("P")?.methodResolutionOrder?.last())
    }

    @Test
    fun `empty worker query is a successful no-op`() {
        val result = SageLiveTypeWorker(
            RuntimeTarget.Native,
            "sage",
        ).probe(SageLiveTypeWorkerQuery("", emptySet()))

        assertEquals(RuntimeExecutionStatus.SUCCESS, result.status)
        assertTrue(result.observedTypes.isEmpty())
    }
}
