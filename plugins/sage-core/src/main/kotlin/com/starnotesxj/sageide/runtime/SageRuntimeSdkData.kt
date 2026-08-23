package com.starnotesxj.sageide.runtime

import com.intellij.openapi.projectRoots.SdkAdditionalData
import com.starnotesxj.sagemath.runtime.CpuArchitecture
import com.starnotesxj.sagemath.runtime.Libc
import com.starnotesxj.sagemath.runtime.OperatingSystem
import com.starnotesxj.sagemath.runtime.PlatformTriple
import com.starnotesxj.sagemath.runtime.RuntimePathMapping
import com.starnotesxj.sagemath.runtime.RuntimeSdkBinding
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import com.starnotesxj.sagemath.runtime.kindName
import org.jdom.Element
import java.nio.file.Path

/**
 * Immutable identity carried by an IntelliJ SDK entry. The manifest owns
 * executable paths; this data identifies only the verified runtime and target.
 */
class SageRuntimeSdkAdditionalData(
    val runtimeId: com.starnotesxj.sagemath.runtime.SageRuntimeId,
    var target: RuntimeTarget,
) : SdkAdditionalData {
    fun binding(): RuntimeSdkBinding = RuntimeSdkBinding(runtimeId, target)

    fun copyData(): SageRuntimeSdkAdditionalData = SageRuntimeSdkAdditionalData(runtimeId, target)

    fun save(element: Element) {
        element.setAttribute("runtimeVersion", runtimeId.version)
        element.setAttribute("runtimeDistribution", runtimeId.distribution)
        element.setAttribute("runtimeOs", runtimeId.platform.os.name)
        element.setAttribute("runtimeArchitecture", runtimeId.platform.architecture.name)
        runtimeId.platform.libc?.let { element.setAttribute("runtimeLibc", it.name) }
        element.setAttribute("targetKind", target.kindName())
        val selectedTarget = target
        when (selectedTarget) {
            RuntimeTarget.Native -> Unit
            is RuntimeTarget.Wsl -> {
                element.setAttribute("targetDistribution", selectedTarget.distribution)
                savePlatform(element, selectedTarget.targetPlatform)
                saveMapping(element, selectedTarget.pathMapping)
            }
            is RuntimeTarget.Docker -> {
                element.setAttribute("targetImage", selectedTarget.image)
                savePlatform(element, selectedTarget.targetPlatform)
                saveMapping(element, selectedTarget.pathMapping)
            }
            is RuntimeTarget.RemoteSsh -> {
                element.setAttribute("targetHost", selectedTarget.host)
                selectedTarget.user?.let { element.setAttribute("targetUser", it) }
                element.setAttribute("targetPort", selectedTarget.port.toString())
                selectedTarget.runtimeRoot?.let { element.setAttribute("targetRuntimeRoot", it) }
                selectedTarget.targetPlatform?.let { savePlatform(element, it) }
                saveMapping(element, selectedTarget.pathMapping)
            }
        }
    }

    override fun markAsCommited() {
        // The data is mutated through SdkModificator by the SDK editor. The
        // SDK framework owns the final committed snapshot.
    }

    companion object {
        fun load(element: Element): SageRuntimeSdkAdditionalData? = runCatching {
            val runtimeId = com.starnotesxj.sagemath.runtime.SageRuntimeId(
                version = element.required("runtimeVersion"),
                platform = PlatformTriple(
                    os = enumValue<OperatingSystem>(element.required("runtimeOs")),
                    architecture = enumValue<CpuArchitecture>(element.required("runtimeArchitecture")),
                    libc = element.getAttributeValue("runtimeLibc")?.let { enumValue<Libc>(it) },
                ),
                distribution = element.required("runtimeDistribution"),
            )
            SageRuntimeSdkAdditionalData(runtimeId, loadTarget(element))
        }.getOrNull()

        private fun loadTarget(element: Element): RuntimeTarget = when (element.required("targetKind")) {
            "native" -> RuntimeTarget.Native
            "wsl" -> RuntimeTarget.Wsl(
                distribution = element.required("targetDistribution"),
                pathMapping = loadMapping(element),
                targetPlatform = loadPlatform(element) ?: PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.UNKNOWN),
            )
            "docker" -> RuntimeTarget.Docker(
                image = element.required("targetImage"),
                pathMapping = loadMapping(element),
                targetPlatform = loadPlatform(element) ?: PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.UNKNOWN),
            )
            "ssh" -> RuntimeTarget.RemoteSsh(
                host = element.required("targetHost"),
                user = element.getAttributeValue("targetUser"),
                port = element.getAttributeValue("targetPort")?.toIntOrNull() ?: 22,
                pathMapping = loadMapping(element),
                runtimeRoot = element.getAttributeValue("targetRuntimeRoot"),
                targetPlatform = loadPlatform(element),
            )
            else -> error("Unknown Sage runtime target")
        }

        private fun savePlatform(element: Element, platform: PlatformTriple) {
            element.setAttribute("targetOs", platform.os.name)
            element.setAttribute("targetArchitecture", platform.architecture.name)
            platform.libc?.let { element.setAttribute("targetLibc", it.name) }
        }

        private fun loadPlatform(element: Element): PlatformTriple? = element.getAttributeValue("targetOs")?.let {
            PlatformTriple(
                os = enumValue(it),
                architecture = enumValue(element.required("targetArchitecture")),
                libc = element.getAttributeValue("targetLibc")?.let { value -> enumValue<Libc>(value) },
            )
        }

        private fun saveMapping(element: Element, mapping: RuntimePathMapping?) {
            mapping ?: return
            element.setAttribute("mappingLocalRoot", mapping.localRoot.toString())
            element.setAttribute("mappingTargetRoot", mapping.targetRoot)
        }

        private fun loadMapping(element: Element): RuntimePathMapping? {
            val local = element.getAttributeValue("mappingLocalRoot") ?: return null
            val target = element.getAttributeValue("mappingTargetRoot") ?: return null
            return RuntimePathMapping(Path.of(local), target)
        }

        private fun Element.required(name: String): String = getAttributeValue(name)
            ?.takeIf { it.isNotBlank() }
            ?: error("Missing Sage runtime SDK field: $name")

        private inline fun <reified T : Enum<T>> enumValue(value: String): T = enumValueOf(value)
    }
}

object SageRuntimeSdkDisplay {
    fun runtimeLabel(id: com.starnotesxj.sagemath.runtime.SageRuntimeId): String = buildString {
        append("SageMath ")
        append(id.version)
        append(" · ")
        append(id.platform)
        append(" · ")
        append(id.distribution)
    }

    fun targetLabel(target: RuntimeTarget): String = when (target) {
        RuntimeTarget.Native -> "Native"
        is RuntimeTarget.Wsl -> "WSL: ${target.distribution}"
        is RuntimeTarget.Docker -> "Docker: ${target.image}"
        is RuntimeTarget.RemoteSsh -> "SSH: ${target.user?.let { "$it@" } ?: ""}${target.host}:${target.port}${target.runtimeRoot?.let { " ($it)" } ?: ""}"
    }

    fun sdkName(binding: RuntimeSdkBinding): String = "${runtimeLabel(binding.runtimeId)} (${targetLabel(binding.target)})"

    fun homePath(runtimeRoot: Path): String = runtimeRoot.toAbsolutePath().normalize().toString()
}

enum class SageRuntimeSdkState {
    VALID,
    MISSING,
    INVALID,
    TARGET_MISMATCH,
}

data class SageRuntimeSdkPresentation(
    val sdkName: String,
    val runtimeLabel: String,
    val targetLabel: String,
    val state: SageRuntimeSdkState,
    val diagnostic: String? = null,
) {
    val displayText: String
        get() = buildString {
            append(runtimeLabel)
            append(" — ")
            append(targetLabel)
            if (state != SageRuntimeSdkState.VALID) {
                append(" [")
                append(state.name.lowercase())
                append("]")
            }
        }
}

fun presentationFor(
    sdkName: String,
    binding: RuntimeSdkBinding,
    diagnostics: List<com.starnotesxj.sagemath.runtime.RuntimeDiagnostic> = emptyList(),
): SageRuntimeSdkPresentation {
    val diagnostic = diagnostics.firstOrNull()
    val state = when (diagnostic?.code) {
        com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode.TARGET_MISMATCH -> SageRuntimeSdkState.TARGET_MISMATCH
        com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED -> SageRuntimeSdkState.MISSING
        com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode.RUNTIME_INVALID,
        com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode.CURRENT_RUNTIME_INVALID,
        -> SageRuntimeSdkState.INVALID
        null -> SageRuntimeSdkState.VALID
        else -> SageRuntimeSdkState.INVALID
    }
    return SageRuntimeSdkPresentation(
        sdkName = sdkName,
        runtimeLabel = SageRuntimeSdkDisplay.runtimeLabel(binding.runtimeId),
        targetLabel = SageRuntimeSdkDisplay.targetLabel(binding.target),
        state = state,
        diagnostic = diagnostic?.message,
    )
}
