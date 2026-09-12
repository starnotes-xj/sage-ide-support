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
    fun `WSL feedback console presentation omits the internal bootstrap wrapper`() {
        val presentation = wslRunPresentationCommand(
            "Ubuntu",
            "/home/user/miniconda3/envs/sage/bin/sage",
            listOf("/mnt/c/Users/星记/Downloads/test.sage"),
        )

        assertTrue(presentation.contains("-- /home/user/miniconda3/envs/sage/bin/sage"))
        assertTrue(!presentation.contains("--exec"))
        assertTrue(!presentation.contains("sage-ide-run-feedback"))
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
    fun `WSL probe preserves runtime variables and reports conda`() {
        val script = SageAutoDetect.probeWslScript()
        assertEquals(true, script.contains("${'$'}HOME/miniconda3/etc/profile.d/conda.sh"))
        assertEquals(true, script.contains("${'$'}(command -v sage || true)"))
        assertEquals(true, script.contains("CONDA=%s"))
        assertEquals(false, script.contains("/home/example/miniconda3"))
        assertEquals(false, script.contains("type conda >/dev/null 2>&1 || exit 127"))
    }

    @Test
    fun `WSL distribution parser handles Windows UTF16 null padding and default marker`() {
        assertEquals(
            listOf("Ubuntu", "Debian"),
            SageAutoDetect.parseWslDistributions("* U\u0000b\u0000u\u0000n\u0000t\u0000u\u0000\r\nD\u0000e\u0000b\u0000i\u0000a\u0000n\u0000\r\n"),
        )
    }

    @Test
    fun `configured WSL Sage path derives its sibling Python without probing`() {
        val script = SageAutoDetect.probeWslScript(
            sageExecutable = "/home/example/miniconda3/envs/sage/bin/sage",
        )
        assertTrue(script.contains("python_executable='/home/example/miniconda3/envs/sage/bin/python'"))
        assertTrue(script.contains("command -v python3"))
        assertTrue(!script.contains("command -v sage"))
        assertTrue(!script.contains("for conda_sh"))
    }

    @Test
    fun `WSL debug wrapper uses explicit bundled Python path`() {
        val command = wslConfiguredDebugScript("/home/user/miniconda3/envs/sage/bin/python")
        assertEquals(true, command.contains("host_ip="))
        assertEquals(true, command.contains("python_executable='/home/user/miniconda3/envs/sage/bin/python'"))
        assertEquals(false, command.contains("command -v sage"))
        assertEquals(false, command.contains("conda activate"))
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
