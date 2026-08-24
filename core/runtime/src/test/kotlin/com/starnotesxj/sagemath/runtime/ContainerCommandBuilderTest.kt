package com.starnotesxj.sagemath.runtime

import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ContainerCommandBuilderTest {
    @Test
    fun `docker and podman commands bind script directory and preserve argv`() {
        val common = ContainerRunSpec(
            engine = ContainerEngine.DOCKER,
            image = "sagemath/sagemath:10.9",
            containerCommand = "sage",
            hostScriptDirectory = Path.of("G:/Projects/my scripts"),
            containerWorkingDirectory = "/mnt/sage",
            scriptFileName = "solve.sage",
            sageArguments = listOf("--quiet"),
            scriptArguments = listOf("value with spaces", "$(not shell)", "it's safe"),
        )
        val docker = ContainerCommandBuilder.build(common)
        val podman = ContainerCommandBuilder.build(common.copy(engine = ContainerEngine.PODMAN))
        assertEquals("docker", docker.first())
        assertEquals("podman", podman.first())
        assertTrue(docker.contains("--mount"))
        assertTrue(docker.contains("type=bind,src=${Path.of("G:/Projects/my scripts").toAbsolutePath().normalize()},dst=/mnt/sage"))
        assertEquals(docker.drop(1), podman.drop(1))
        assertTrue(docker.contains("$(not shell)"))
        assertTrue(docker.contains("it's safe"))
    }

    @Test
    fun `invalid container working directory fails closed`() {
        assertFailsWith<IllegalArgumentException> {
            ContainerRunSpec(ContainerEngine.DOCKER, "sage", "sage", Path.of("."), "/mnt/../host", "solve.sage")
        }
    }

    @Test
    fun `container profile accepts only explicit engines and safe directory`() {
        assertTrue(ContainerProfileValidator.validate("docker", "sage", "sage", "/mnt/sage").succeeded)
        assertTrue(ContainerProfileValidator.validate("podman", "sage", "sage", "/mnt/sage").succeeded)
        assertTrue(!ContainerProfileValidator.validate("", "sage", "sage", "/mnt/sage").succeeded)
        assertTrue(!ContainerProfileValidator.validate("docker", "sage", "sage", "relative").succeeded)
    }

    @Test
    fun `image probe runs version then expression inside selected engine`() {
        val calls = mutableListOf<Pair<ContainerEngine, List<String>>>()
        val probe = ContainerRuntimeProbe(ContainerRuntimeExecutor { engine, image, command, _, _ ->
            calls += engine to (listOf(image) + command)
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, if (command.contains("--version")) "SageMath 10.9" else "4\n", "", 1, false)
        })
        val result = probe.probe(ContainerEngine.PODMAN, "sage:10.9")
        assertEquals(RuntimeExecutionStatus.SUCCESS, result.status)
        assertEquals("4", result.expressionOutput)
        assertEquals(2, calls.size)
        assertEquals(ContainerEngine.PODMAN, calls[0].first)
        assertEquals(listOf("sage:10.9", "sage", "--version"), calls[0].second)
        assertEquals(ContainerEngine.PODMAN, calls[1].first)
        assertEquals(listOf("sage:10.9", "sage", "-c", "print(2+2)"), calls[1].second)
    }

    @Test
    fun `image probe rejects a successful non Sage expression`() {
        val probe = ContainerRuntimeProbe(ContainerRuntimeExecutor { _, _, command, _, _ ->
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, if (command.contains("--version")) "version" else "5", "", 1, false)
        })
        val result = probe.probe(ContainerEngine.DOCKER, "image")
        assertEquals(RuntimeExecutionStatus.FAILED, result.status)
        assertTrue(result.diagnostics.any { it.code == RuntimeDiagnosticCode.TARGET_PROBE_FAILED })
    }

    @Test
    fun `production container executor builds image owned probe without mounts`() {
        val calls = mutableListOf<RuntimeProcessRequest>()
        val executor = JdkContainerRuntimeExecutor { request ->
            calls += request
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, "ok", "", 1, false)
        }
        executor.execute(
            ContainerEngine.PODMAN,
            "sage:10.9",
            listOf("sage", "--version"),
            RuntimeControl(),
            1024,
        )
        assertEquals(
            listOf("podman", "run", "--rm", "sage:10.9", "sage", "--version"),
            calls.single().command,
        )
        assertTrue(calls.single().command.none { it == "--mount" || it == "-v" || it == "--volume" })
    }
}
