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
    }

    @Test
    fun `WSL debug wrapper uses explicit bundled Python path`() {
        val command = wslDebugScript(
            "sage",
            "/home/user/miniconda3/envs/sage/bin/sage",
            "/opt/sage/local/bin/python3",
        )
        assertEquals(true, command.contains("conda activate 'sage'"))
        assertEquals(true, command.contains("host_ip="))
        assertEquals(true, command.contains("python_executable='/opt/sage/local/bin/python3'"))
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
