package com.starnotesxj.sageide.run

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class SageRunConfigurationValidationTest {
    @Test
    fun `blank script is rejected without runtime probing`() {
        assertEquals(
            "The Sage script path is empty",
            configurationValidationError("", SageRunSettings.State()),
        )
    }

    @Test
    fun `WSL validation checks only local path shape`() {
        val state = SageRunSettings.State().apply {
            executionMode = ExecutionMode.WSL.name
            wslDistribution = "Ubuntu"
            wslCondaEnvironment = "sage"
            wslCondaExecutable = "C:/conda.exe"
        }
        assertEquals(
            "Conda executable must be an absolute POSIX path",
            configurationValidationError("test.sage", state),
        )
    }

    @Test
    fun `valid WSL settings do not launch a runtime probe`() {
        val state = SageRunSettings.State().apply {
            executionMode = ExecutionMode.WSL.name
            wslDistribution = "Ubuntu"
            wslCondaEnvironment = "sage"
            wslCondaExecutable = "/opt/conda/bin/conda"
            wslSageExecutable = "/opt/conda/envs/sage/bin/sage"
        }
        assertNull(configurationValidationError("test.sage", state))
    }

    @Test
    fun `unknown execution mode is rejected locally`() {
        val state = SageRunSettings.State().apply { executionMode = "BROKEN" }
        assertEquals(
            "Unknown Sage execution mode: BROKEN",
            configurationValidationError("test.sage", state),
        )
    }
}
