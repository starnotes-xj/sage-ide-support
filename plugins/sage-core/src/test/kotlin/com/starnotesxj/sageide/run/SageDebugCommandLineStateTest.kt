package com.starnotesxj.sageide.run

import org.junit.Assert.assertEquals
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
    fun `activates configured conda environment before WSL run`() {
        val command = wslRunScript("sage", "/home/user/miniconda3/envs/sage/bin/sage", listOf("/mnt/c/test.sage"))
        assertEquals(true, command.contains("conda activate 'sage'"))
        assertEquals(true, command.contains("exec '/home/user/miniconda3/envs/sage/bin/sage' '/mnt/c/test.sage'"))
        assertEquals(true, command.contains("\"${'$'}HOME/miniconda3/etc/profile.d/conda.sh\""))
        assertEquals(true, command.contains("\"${'$'}{conda_sh%/etc/profile.d/conda.sh}/bin/conda\""))
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
}
