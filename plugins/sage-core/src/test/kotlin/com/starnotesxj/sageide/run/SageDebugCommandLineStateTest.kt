package com.starnotesxj.sageide.run

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SageDebugCommandLineStateTest {

    @Test
    fun `tokenizes quoted arguments like PyCharm`() {
        assertEquals(
            listOf("--define", "value with spaces", "--flag"),
            tokenizeArguments("--define \"value with spaces\" --flag"),
        )
    }

    @Test
    fun `tokenizes empty input`() {
        assertEquals(emptyList<String>(), tokenizeArguments("   "))
    }

    @Test
    fun `converts Windows paths to WSL paths`() {
        assertEquals("/mnt/c/Users/星记/test.sage", toWslPath("C:\\Users\\星记\\test.sage"))
        assertEquals("/home/user/test.sage", toWslPath("/home/user/test.sage"))
    }

    @Test
    fun `isolated WSL settings use independent executable paths`() {
        val state = SageRunSettings.State()
        state.nativeSageExecutable = "C:/Sage/sage.exe"
        state.wslSageExecutable = "/home/user/miniconda3/envs/sage/bin/sage"
        assertEquals("C:/Sage/sage.exe", state.nativeSageExecutable)
        assertEquals("/home/user/miniconda3/envs/sage/bin/sage", state.wslSageExecutable)
    }

    @Test
    fun `WSL probe rejects non POSIX configured paths`() {
        kotlin.test.assertFailsWith<IllegalArgumentException> {
            SageAutoDetect.detectWslRuntime("Ubuntu", "sage", "C:/conda.exe", "")
        }
    }

    @Test
    fun `direct WSL run arguments expose concise executable command`() {
        assertEquals(
            listOf("-d", "Ubuntu", "--", "/home/user/miniconda3/envs/sage/bin/sage", "/mnt/c/Users/星记/Downloads/test.sage"),
            wslDirectRunArguments(
                "Ubuntu",
                "/home/user/miniconda3/envs/sage/bin/sage",
                listOf("/mnt/c/Users/星记/Downloads/test.sage"),
            ),
        )
    }

    @Test
    fun `configured WSL executable prefers dedicated field and legacy POSIX fallback`() {
        val state = SageRunSettings.State()
        state.sageExecutable = "/legacy/sage"
        assertEquals("/legacy/sage", configuredWslSageExecutable(state))
        state.wslSageExecutable = "/dedicated/sage"
        assertEquals("/dedicated/sage", configuredWslSageExecutable(state))
    }

    @Test
    fun `activates configured conda environment before WSL run`() {
        val command = wslRunScript("sage", "/home/user/miniconda3/envs/sage/bin/sage", listOf("/mnt/c/test.sage"))
        assertEquals(true, command.contains("conda activate 'sage'"))
        assertEquals(true, command.contains("exec '/home/user/miniconda3/envs/sage/bin/sage' '/mnt/c/test.sage'"))
        assertEquals(true, command.contains("\"${'$'}HOME/miniconda3/etc/profile.d/conda.sh\""))
        assertEquals(true, command.contains("\"${'$'}{conda_sh%/etc/profile.d/conda.sh}/bin/conda\""))
    }

    @Test
    fun `configured WSL run wrapper resolves Sage inside the child shell`() {
        val command = wslConfiguredRunScript(
            environment = "sage",
            configuredExecutable = "",
            arguments = listOf("/mnt/c/test.sage"),
        )
        assertTrue(command.contains("conda activate 'sage'"))
        assertTrue(command.contains("exec sage '/mnt/c/test.sage'"))
        assertTrue(command.contains("${'$'}HOME/miniconda3/etc/profile.d/conda.sh"))
        assertTrue(command.contains("${'$'}HOME/.bashrc"))
        assertTrue(!command.contains("for conda_sh"))
        assertTrue(!command.contains("command -v sage"))
    }

    @Test
    fun `configured WSL run wrapper uses explicit conda without exposing discovery probes`() {
        val command = wslConfiguredRunScript(
            environment = "sage",
            configuredExecutable = "",
            arguments = listOf("/mnt/c/test.sage"),
            condaExecutable = "/home/user/miniconda3/bin/conda",
        )
        assertTrue(command.contains("eval \"${'$'}('/home/user/miniconda3/bin/conda' shell.bash hook)\""))
        assertTrue(command.contains("conda activate 'sage' >/dev/null 2>&1 && exec sage"))
        assertTrue(!command.contains(".bashrc"))
        assertTrue(!command.contains("for conda_sh"))
    }

    @Test
    fun `WSL probe preserves runtime variables and reports conda`() {
        val script = SageAutoDetect.probeWslScript()
        assertEquals(true, script.contains("${'$'}HOME/miniconda3/etc/profile.d/conda.sh"))
        assertEquals(true, script.contains("${'$'}(command -v sage || true)"))
        assertEquals(true, script.contains("CONDA=%s"))
        assertEquals(false, script.contains("/home/starnotes/miniconda3"))
    }

    @Test
    fun `explicit conda executable uses bash hook`() {
        val command = wslRunScript(
            "sage",
            "/home/user/miniconda3/envs/sage/bin/sage",
            emptyList(),
            "/home/user/miniconda3/bin/conda",
        )
        assertEquals(true, command.contains("conda_executable='/home/user/miniconda3/bin/conda'"))
        assertEquals(true, command.contains("shell.bash hook"))
        assertEquals(false, command.contains("conda_sh in"))
    }

    @Test
    fun `WSL debug wrapper uses explicit bundled Python path`() {
        val command = wslDebugScript(
            "sage",
            "/home/user/miniconda3/envs/sage/bin/sage",
            "/opt/sage/local/bin/python3",
            "/home/user/miniconda3/bin/conda",
        )
        assertEquals(true, command.contains("conda activate 'sage'"))
        assertEquals(true, command.contains("host_ip="))
        assertEquals(true, command.contains("python_executable='/opt/sage/local/bin/python3'"))
        assertEquals(true, command.contains("conda_executable='/home/user/miniconda3/bin/conda'"))
        assertEquals(false, command.contains("%/sage"))
        assertEquals(true, command.contains("exec \"${'$'}python_executable\""))
    }

    @Test
    fun `WSL debug wrapper fails closed without bundled Python`() {
        kotlin.test.assertFailsWith<IllegalStateException> {
            wslDebugScript("sage", "/opt/sage/bin/sage")
        }
    }

    @Test
    fun `container debug boundary is documented in source contract`() {
        val source = SageDebugCommandLineState::class.java
            .getDeclaredField("LAUNCHER_SOURCE")
        assertTrue(source.name == "LAUNCHER_SOURCE")
    }
}
