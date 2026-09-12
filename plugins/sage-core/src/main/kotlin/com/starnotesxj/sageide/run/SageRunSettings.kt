package com.starnotesxj.sageide.run

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

/**
 * Global Sage execution settings (Settings | Tools | SageMath).
 *
 * Three execution modes are supported:
 * - NATIVE: the `sage` command on the local machine;
 * - WSL: `wsl.exe -d <distribution> -- sage ...`;
 * - DOCKER: `docker run --rm -v <scriptDir>:<containerDir> ...` which mounts
 *   the script directory into a Sage container, so no path mapping is needed.
 *
 * Design follows renpe/intellij-sagemath (Apache 2.0), extended with Docker.
 */
enum class ExecutionMode { NATIVE, WSL, DOCKER, SSH }

@State(name = "SageRunSettings", storages = [Storage("sage-ide-support.xml")])
class SageRunSettings : PersistentStateComponent<SageRunSettings.State> {

    class State {
        var executionMode: String = ExecutionMode.WSL.name
        /** Native executable only; never reused as a WSL or container path. */
        var nativeSageExecutable: String = ""
        /** Legacy field retained for settings XML migration; also supports direct WSL launch. */
        var sageExecutable: String = ""
        /** Optional absolute POSIX Sage executable inside WSL. */
        var wslSageExecutable: String = ""
        /** Optional absolute Python executable paired with the WSL Sage runtime. */
        var wslPythonExecutable: String = ""
        var wslDistribution: String = "Ubuntu"
        var wslCondaEnvironment: String = "sage"
        /** Optional absolute WSL path to conda; blank uses standard locations. */
        var wslCondaExecutable: String = ""
        /** Enabled by default; older settings without the migration marker are upgraded once. */
        var liveTypeProbingEnabled: Boolean = true
        var liveTypeProbingConfigured: Boolean = true
        var containerExecutable: String = "docker"
        var dockerImage: String = "sagemath/sagemath"
        var dockerContainerDir: String = "/mnt/sage"
        var dockerCommand: String = "sage"
        /** SSH host settings intentionally exclude passwords, proxy options and automatic sync. */
        var sshHost: String = ""
        var sshUser: String = ""
        var sshPort: Int = 22
        var sshKnownHostsFile: String = ""
        var sshAuthentication: String = "AGENT"
        var sshIdentityFile: String = ""
        var sshRuntimeRoot: String = ""
        var sshSageExecutable: String = ""
        var sshLocalRoot: String = ""
        var sshTargetRoot: String = ""
        var sshConnectTimeoutSeconds: Int = 10
        var sageParameters: String = ""
    }

    private var myState: State = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        if (state.nativeSageExecutable.isBlank() && state.sageExecutable.isNotBlank()) {
            state.nativeSageExecutable = state.sageExecutable
        }
        if (!state.liveTypeProbingConfigured) {
            state.liveTypeProbingEnabled = true
            state.liveTypeProbingConfigured = true
        }
        myState = state
    }

    companion object {
        @JvmStatic
        fun getInstance(): SageRunSettings =
            ApplicationManager.getApplication().getService(SageRunSettings::class.java)
    }
}
