package com.starnotesxj.sagemath.ctf.model

/**
 * Where SageMath or a CTF helper process executes.
 *
 * This type deliberately has no IntelliJ dependency. Platform adapters can
 * translate it into run configurations, terminals, Jupyter kernels, or remote
 * process launchers without changing the product domain model.
 */
sealed interface ExecutionTarget {
    data object Native : ExecutionTarget

    data class Wsl(
        val distribution: String,
    ) : ExecutionTarget

    data class Container(
        val image: String,
        val runtime: ContainerRuntime = ContainerRuntime.DOCKER,
    ) : ExecutionTarget

    data class Ssh(
        val host: String,
        val user: String? = null,
        val port: Int = 22,
    ) : ExecutionTarget
}

enum class ContainerRuntime {
    DOCKER,
    PODMAN,
}
