package com.starnotesxj.sagemath.runtime

import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.time.Duration

sealed interface SshAuthentication {
    data object Agent : SshAuthentication
    data class IdentityFile(val path: Path) : SshAuthentication
}

data class SshOpenSshSpec(
    val host: String,
    val user: String?,
    val port: Int,
    val knownHostsFile: Path,
    val authentication: SshAuthentication,
    val runtimeRoot: String,
    val pathMapping: RuntimePathMapping,
    val connectTimeout: Duration = Duration.ofSeconds(10),
) {
    init {
        require(SshCommandValidation.isSafeHost(host)) { "SSH host is invalid" }
        user?.let { require(SshCommandValidation.isSafeUser(it)) { "SSH user is invalid" } }
        require(port in 1..65535) { "SSH port must be valid" }
        require(connectTimeout.seconds in 1..300 && !connectTimeout.isNegative) { "SSH connect timeout must be between 1 and 300 seconds" }
        requireAbsoluteRegularFile(knownHostsFile, "SSH known_hosts file")
        when (val auth = authentication) {
            SshAuthentication.Agent -> Unit
            is SshAuthentication.IdentityFile -> requireAbsoluteRegularFile(auth.path, "SSH identity file")
        }
        require(SshCommandValidation.isAbsolutePosixRoot(runtimeRoot)) { "SSH runtime root must be an absolute normalized POSIX path" }
        require(SshCommandValidation.isAbsolutePosixRoot(pathMapping.targetRoot)) { "SSH target mapping root must be an absolute normalized POSIX path" }
        require(pathMapping.localRoot.isAbsolute) { "SSH local mapping root must be absolute" }
        require(pathMapping.localRoot == pathMapping.localRoot.toAbsolutePath().normalize()) { "SSH local mapping root must be normalized" }
    }

    private fun requireAbsoluteRegularFile(path: Path, label: String) {
        require(path.isAbsolute && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) { "$label must be an absolute regular file" }
    }
}

data class SshSageRunRequest(
    val transport: SshOpenSshSpec,
    val remoteSageExecutable: String,
    val remoteScriptPath: String,
    val sageArguments: List<String> = emptyList(),
    val scriptArguments: List<String> = emptyList(),
) {
    init {
        require(SshCommandValidation.isAbsolutePosixPath(remoteSageExecutable)) { "Remote Sage executable must be an absolute POSIX path" }
        require(SshCommandValidation.isAbsolutePosixPath(remoteScriptPath)) { "Remote script path must be an absolute POSIX path" }
        require(isUnder(remoteSageExecutable, transport.runtimeRoot)) { "Remote Sage executable must be inside the SSH runtime root" }
        require(isUnder(remoteScriptPath, transport.pathMapping.targetRoot)) { "Remote script must be inside the SSH target mapping root" }
        (sageArguments + scriptArguments).forEach { require(SshCommandValidation.isSafeShellValue(it)) { "SSH argument contains a control character" } }
    }

    private fun isUnder(path: String, root: String): Boolean {
        val normalizedPath = SshCommandValidation.normalizePosix(path)
        val normalizedRoot = SshCommandValidation.normalizePosix(root).trimEnd('/')
        return normalizedPath == normalizedRoot || normalizedPath.startsWith("$normalizedRoot/")
    }
}

/** Builds a strict, non-interactive system OpenSSH argv for one mapped Sage run. */
object SshOpenSshCommandBuilder {
    fun build(request: SshSageRunRequest): List<String> {
        val remoteDirectory = request.remoteScriptPath.substringBeforeLast('/', missingDelimiterValue = "/")
        val remoteCommand = buildString {
            append("cd -- ")
            append(quotePosixShellWord(remoteDirectory))
            append(" && exec ")
            append(quotePosixShellWord(request.remoteSageExecutable))
            (request.sageArguments + listOf(request.remoteScriptPath) + request.scriptArguments).forEach {
                append(' ')
                append(quotePosixShellWord(it))
            }
        }
        val args = mutableListOf(
            "ssh",
            "-F", "none",
            "-T",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=${request.transport.knownHostsFile.toAbsolutePath().normalize()}",
            "-o", "GlobalKnownHostsFile=none",
            "-o", "PreferredAuthentications=publickey",
            "-o", "PubkeyAuthentication=yes",
            "-o", "PasswordAuthentication=no",
            "-o", "KbdInteractiveAuthentication=no",
            "-o", "NumberOfPasswordPrompts=0",
            "-o", "ForwardAgent=no",
            "-o", "ClearAllForwardings=yes",
            "-o", "PermitLocalCommand=no",
            "-o", "ProxyCommand=none",
            "-o", "ProxyJump=none",
            "-o", "RemoteCommand=none",
            "-o", "ControlMaster=no",
            "-o", "ConnectTimeout=${request.transport.connectTimeout.seconds}",
            "-p", request.transport.port.toString(),
        )
        when (val authentication = request.transport.authentication) {
            SshAuthentication.Agent -> Unit
            is SshAuthentication.IdentityFile -> args += listOf(
                "-i", authentication.path.toAbsolutePath().normalize().toString(),
                "-o", "IdentitiesOnly=yes",
            )
        }
        args += "--"
        args += request.transport.user?.let { "$it@${request.transport.host}" } ?: request.transport.host
        args += remoteCommand
        return args
    }

    private fun quotePosixShellWord(value: String): String {
        require(SshCommandValidation.isSafeShellValue(value)) { "SSH remote command value contains a control character" }
        return "'${value.replace("'", "'\"'\"'")}'"
    }
}

private object SshCommandValidation {
    private val HOST = Regex("[A-Za-z0-9][A-Za-z0-9.-]*")
    private val USER = Regex("[A-Za-z0-9._-]+")

    fun isSafeHost(value: String): Boolean = value == value.trim() && HOST.matches(value) && !value.startsWith('-')
    fun isSafeUser(value: String): Boolean = USER.matches(value) && !value.startsWith('-')

    fun isSafeShellValue(value: String): Boolean = value.none(Char::isISOControl)

    fun isAbsolutePosixRoot(value: String): Boolean = runCatching {
        normalizePosix(value) == value && value.startsWith('/') && value != "/"
    }.getOrDefault(false)

    fun isAbsolutePosixPath(value: String): Boolean = runCatching {
        normalizePosix(value) == value && value.startsWith('/') && value != "/"
    }.getOrDefault(false)

    fun normalizePosix(value: String): String {
        require(value.isNotEmpty() && value.startsWith('/') && !value.startsWith("//") && '\\' !in value)
        val components = value.split('/').drop(1)
        require(components.none { it.isEmpty() || it == "." || it == ".." || it.any(Char::isISOControl) })
        return "/" + components.joinToString("/")
    }
}
