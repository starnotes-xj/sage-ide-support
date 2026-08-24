package com.starnotesxj.sagemath.runtime

import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class SshCommandBuilderTest {
    @Test
    fun `builds strict noninteractive agent command with one quoted remote command`() {
        val temp = Files.createTempDirectory("ssh-builder")
        val knownHosts = Files.createFile(temp.resolve("known_hosts"))
        try {
            val mapping = RuntimePathMapping(temp.resolve("workspace"), "/srv/workspace")
            val spec = SshOpenSshSpec(
                host = "sage.example",
                user = "ctf",
                port = 2201,
                knownHostsFile = knownHosts,
                authentication = SshAuthentication.Agent,
                runtimeRoot = "/opt/sage-runtime",
                pathMapping = mapping,
            )
            val argv = SshOpenSshCommandBuilder.build(
                SshSageRunRequest(
                    transport = spec,
                    remoteSageExecutable = "/opt/sage-runtime/bin/sage",
                    remoteScriptPath = "/srv/workspace/solve.sage",
                    sageArguments = listOf("--quiet"),
                    scriptArguments = listOf("value with spaces", "$(id)", "x'; echo bad; '")
                ),
            )
            assertEquals("ssh", argv.first())
            assertTrue(argv.containsAll(listOf("-F", "none", "-T", "-o", "BatchMode=yes", "StrictHostKeyChecking=yes")))
            assertTrue(argv.contains("-o"))
            assertTrue(argv.any { it == "UserKnownHostsFile=${knownHosts.toAbsolutePath().normalize()}" })
            assertTrue(argv.contains("GlobalKnownHostsFile=none"))
            assertTrue(argv.contains("PreferredAuthentications=publickey"))
            assertTrue(argv.contains("PasswordAuthentication=no"))
            assertTrue(argv.contains("KbdInteractiveAuthentication=no"))
            assertTrue(argv.contains("ProxyCommand=none"))
            assertTrue(argv.contains("ProxyJump=none"))
            assertTrue(argv.contains("RemoteCommand=none"))
            assertTrue(argv.contains("--"))
            assertEquals("ctf@sage.example", argv[argv.indexOf("--") + 1])
            val remote = argv.last()
            assertEquals(1, argv.drop(argv.indexOf("--") + 2).size)
            assertTrue(remote.startsWith("cd -- '/srv/workspace' && exec '/opt/sage-runtime/bin/sage'"))
            assertTrue(remote.contains("'value with spaces'"))
            assertTrue(remote.contains("'\$(id)'"))
            assertTrue(remote.contains("'x'\"'\"'; echo bad; '\"'\"''"))
            assertTrue(argv.none { it == "--mount" || it == "-v" || it == "--volume" })
        } finally {
            Files.walk(temp).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `identity mode is explicit and rejects invalid authentication files`() {
        val temp = Files.createTempDirectory("ssh-identity")
        val knownHosts = Files.createFile(temp.resolve("known_hosts"))
        val identity = Files.createFile(temp.resolve("id_ed25519"))
        try {
            val spec = SshOpenSshSpec(
                host = "127.0.0.1",
                user = null,
                port = 22,
                knownHostsFile = knownHosts,
                authentication = SshAuthentication.IdentityFile(identity),
                runtimeRoot = "/opt/sage",
                pathMapping = RuntimePathMapping(temp, "/srv/workspace"),
            )
            val argv = SshOpenSshCommandBuilder.build(
                SshSageRunRequest(spec, "/opt/sage/bin/sage", "/srv/workspace/a.sage"),
            )
            assertTrue(argv.containsAll(listOf("-i", identity.toAbsolutePath().normalize().toString(), "IdentitiesOnly=yes")))
        } finally {
            Files.walk(temp).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
        assertFailsWith<IllegalArgumentException> {
            SshOpenSshSpec(
                host = "sage.example",
                user = "ctf",
                port = 22,
                knownHostsFile = Path.of("relative-known-hosts"),
                authentication = SshAuthentication.Agent,
                runtimeRoot = "/opt/sage",
                pathMapping = RuntimePathMapping(Path.of("/tmp"), "/srv/workspace"),
            )
        }
    }

    @Test
    fun `rejects symlinked trust files`() {
        val temp = Files.createTempDirectory("ssh-symlink")
        val target = Files.createFile(temp.resolve("actual-known-hosts"))
        val link = temp.resolve("known_hosts")
        try {
            runCatching { Files.createSymbolicLink(link, target) }.onSuccess {
                assertFailsWith<IllegalArgumentException> {
                    SshOpenSshSpec("host", null, 22, link, SshAuthentication.Agent, "/opt/sage", RuntimePathMapping(temp, "/srv/workspace"))
                }
            }
        } finally {
            Files.walk(temp).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `rejects unsafe hosts roots and paths`() {
        val temp = Files.createTempDirectory("ssh-invalid")
        val knownHosts = Files.createFile(temp.resolve("known_hosts"))
        try {
            assertFailsWith<IllegalArgumentException> {
                SshOpenSshSpec("bad host", null, 22, knownHosts, SshAuthentication.Agent, "/opt/sage", RuntimePathMapping(temp, "/srv/workspace"))
            }
            val spec = SshOpenSshSpec("host", null, 22, knownHosts, SshAuthentication.Agent, "/opt/sage", RuntimePathMapping(temp, "/srv/workspace"))
            assertFailsWith<IllegalArgumentException> {
                SshSageRunRequest(spec, "/opt/sage/../bin/sage", "/srv/workspace/a.sage")
            }
            assertFailsWith<IllegalArgumentException> {
                SshSageRunRequest(spec, "/opt/sage/bin/sage", "/tmp/a.sage")
            }
        } finally {
            Files.walk(temp).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }
}
