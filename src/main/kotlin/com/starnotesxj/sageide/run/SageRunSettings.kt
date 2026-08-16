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
enum class ExecutionMode { NATIVE, WSL, DOCKER }

@State(name = "SageRunSettings", storages = [Storage("sage-ide-support.xml")])
class SageRunSettings : PersistentStateComponent<SageRunSettings.State> {

    class State {
        var executionMode: String = ExecutionMode.WSL.name
        var sageExecutable: String = ""
        var wslDistribution: String = "Ubuntu"
        var dockerImage: String = "sagemath/sagemath"
        var dockerContainerDir: String = "/mnt/sage"
        var dockerCommand: String = "sage"
        var sageParameters: String = ""
    }

    private var myState: State = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    companion object {
        @JvmStatic
        fun getInstance(): SageRunSettings =
            ApplicationManager.getApplication().getService(SageRunSettings::class.java)
    }
}
