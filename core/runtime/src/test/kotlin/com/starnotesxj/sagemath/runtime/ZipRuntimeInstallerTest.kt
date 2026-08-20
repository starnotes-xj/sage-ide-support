package com.starnotesxj.sagemath.runtime

import java.net.URI
import java.nio.file.Files
import java.nio.file.LinkOption
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.Test
import kotlin.test.assertTrue

class ZipRuntimeInstallerTest {
    @Test
    fun `installer publishes a verified executable from a safe zip`() {
        val root = Files.createTempDirectory("sage-runtime-install")
        try {
            val archive = root.resolve("runtime.zip")
            ZipOutputStream(Files.newOutputStream(archive)).use { output ->
                output.putNextEntry(ZipEntry("bin/sage"))
                output.write("#!/bin/sh\necho sage\n".toByteArray())
                output.closeEntry()
            }
            val digest = Sha256ChecksumVerifier().sha256(archive)
            val platform = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)
            val id = SageRuntimeId("10.6", platform)
            val artifact = RuntimeArtifact(
                id,
                URI("https://example.invalid/runtime.zip"),
                ArchiveFormat.ZIP,
                sha256 = digest,
                entrypoint = "bin/sage",
            )
            val executableBytes = "#!/bin/sh\necho sage\n".toByteArray()
            val manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = id,
                executable = "bin/sage",
                files = listOf(RuntimeFileRecord("bin/sage", executableBytes.size.toLong(), digestOf(executableBytes))),
                artifactSha256 = digest,
            )
            val downloader = object : RuntimeDownloader {
                override fun download(
                    artifact: RuntimeArtifact,
                    destination: java.nio.file.Path,
                    progress: DownloadProgressListener,
                    cancellation: InstallationCancellation,
                ): DownloadedArtifact {
                    Files.copy(archive, destination)
                    return DownloadedArtifact(destination, Files.size(destination), digest)
                }
            }

            val result = ZipRuntimeInstaller(downloader).install(
                RuntimeInstallRequest(artifact, root.resolve("installed"), manifest = manifest)
            )

            assertTrue(result is InstallResult.Installed)
            val installed = (result as InstallResult.Installed).runtime
            assertTrue(Files.isRegularFile(installed.executable, LinkOption.NOFOLLOW_LINKS))
            assertTrue(Files.isRegularFile(root.resolve("installed/current"), LinkOption.NOFOLLOW_LINKS))
            assertTrue(Files.isDirectory(root.resolve("installed/versions"), LinkOption.NOFOLLOW_LINKS))
            val metadataFiles = Files.list(root.resolve("installed/versions")).use { paths -> paths.filter { it.fileName.toString().endsWith(".meta") }.toList() }
            assertTrue(metadataFiles.any { Files.isRegularFile(it, LinkOption.NOFOLLOW_LINKS) })
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `existing valid runtime is reused without replacement`() {
        val root = Files.createTempDirectory("sage-runtime-existing")
        try {
            val archive = root.resolve("runtime.zip")
            ZipOutputStream(Files.newOutputStream(archive)).use { output ->
                output.putNextEntry(ZipEntry("sage.exe"))
                output.write("sage".toByteArray())
                output.closeEntry()
            }
            val digest = Sha256ChecksumVerifier().sha256(archive)
            val platform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)
            val id = SageRuntimeId("10.6", platform)
            val artifact = RuntimeArtifact(
                id,
                URI("https://example.invalid/runtime.zip"),
                ArchiveFormat.ZIP,
                sha256 = digest,
                entrypoint = "sage.exe",
            )
            val manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = id,
                executable = "sage.exe",
                files = listOf(RuntimeFileRecord("sage.exe", 4, digestOf("sage".toByteArray()))),
                artifactSha256 = digest,
            )
            val downloader = object : RuntimeDownloader {
                override fun download(
                    artifact: RuntimeArtifact,
                    destination: java.nio.file.Path,
                    progress: DownloadProgressListener,
                    cancellation: InstallationCancellation,
                ): DownloadedArtifact {
                    Files.copy(archive, destination)
                    return DownloadedArtifact(destination, Files.size(destination), digest)
                }
            }
            val installer = ZipRuntimeInstaller(downloader)
            val installRoot = root.resolve("installed")
            val first = installer.install(RuntimeInstallRequest(artifact, installRoot, manifest = manifest))
            val second = installer.install(RuntimeInstallRequest(artifact, installRoot, manifest = manifest))

            assertTrue(first is InstallResult.Installed)
            assertTrue(second is InstallResult.AlreadyInstalled)
            assertTrue(Files.isRegularFile(installRoot.resolve("current"), LinkOption.NOFOLLOW_LINKS))
            assertTrue(FileRuntimeLocator().locate(installRoot, id) != null)
            Files.writeString(installRoot.resolve("versions").resolve(Files.readString(installRoot.resolve("current")).trim()).resolve("unexpected"), "tampered")
            assertTrue(FileRuntimeLocator().locate(installRoot, id) == null)
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `streaming downloader cleans destination after digest failure`() {
        val root = Files.createTempDirectory("sage-runtime-download")
        try {
            val payload = "payload".toByteArray()
            val artifact = RuntimeArtifact(
                SageRuntimeId("10.6", PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)),
                URI("https://example.invalid/runtime.zip"),
                ArchiveFormat.ZIP,
                sizeBytes = payload.size.toLong(),
                sha256 = "0".repeat(64),
            )
            val destination = root.resolve("artifact.zip")

            kotlin.test.assertFailsWith<RuntimeInstallException> {
                HttpRuntimeDownloader({ payload.inputStream() }).download(artifact, destination)
            }

            assertTrue(!Files.exists(destination, LinkOption.NOFOLLOW_LINKS))
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `installer rejects unsupported archive format`() {
        val root = Files.createTempDirectory("sage-runtime-format")
        try {
            val platform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)
            val artifact = RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("https://example.invalid/runtime.tar"),
                ArchiveFormat.entries.first { it != ArchiveFormat.ZIP },
                sha256 = "0".repeat(64),
            )
            val result = ZipRuntimeInstaller(object : RuntimeDownloader {
                override fun download(
                    artifact: RuntimeArtifact,
                    destination: java.nio.file.Path,
                    progress: DownloadProgressListener,
                    cancellation: InstallationCancellation,
                ): DownloadedArtifact = error("downloader must not be called")
            }).install(RuntimeInstallRequest(artifact, root.resolve("installed"), manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = artifact.id,
                executable = artifact.entrypoint,
                files = listOf(RuntimeFileRecord("sage.exe", 0, "0".repeat(64))),
                artifactSha256 = artifact.sha256,
            )))

            assertTrue(result is InstallResult.Failed)
            assertTrue((result as InstallResult.Failed).stage == "ARCHIVE_FORMAT_UNSUPPORTED")
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `installer cancellation cleans staging and leaves no current pointer`() {
        val root = Files.createTempDirectory("sage-runtime-cancel")
        try {
            val archive = root.resolve("runtime.zip")
            ZipOutputStream(Files.newOutputStream(archive)).use { output ->
                output.putNextEntry(ZipEntry("sage.exe"))
                output.write("sage".toByteArray())
                output.closeEntry()
            }
            val artifact = RuntimeArtifact(
                SageRuntimeId("10.6", PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)),
                URI("https://example.invalid/runtime.zip"),
                ArchiveFormat.ZIP,
                sha256 = Sha256ChecksumVerifier().sha256(archive),
                entrypoint = "sage.exe",
            )
            val manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = artifact.id,
                executable = artifact.entrypoint,
                files = listOf(RuntimeFileRecord("sage.exe", 4, digestOf("sage".toByteArray()))),
                artifactSha256 = artifact.sha256,
            )
            val result = ZipRuntimeInstaller(object : RuntimeDownloader {
                override fun download(
                    artifact: RuntimeArtifact,
                    destination: java.nio.file.Path,
                    progress: DownloadProgressListener,
                    cancellation: InstallationCancellation,
                ): DownloadedArtifact {
                    throw RuntimeInstallException("DOWNLOAD_CANCELLED", "cancelled")
                }
            }).install(
                RuntimeInstallRequest(
                    artifact,
                    root.resolve("installed"),
                    manifest = manifest,
                    cancellation = InstallationCancellation { true },
                )
            )

            assertTrue(result is InstallResult.Failed)
            assertTrue((result as InstallResult.Failed).stage == "DOWNLOAD_CANCELLED")
            assertTrue(!Files.exists(root.resolve("installed/current")))
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `installer rejects zip slip entries`() {
        val root = Files.createTempDirectory("sage-runtime-zipslip")
        try {
            val archiveBytes = java.io.ByteArrayOutputStream()
            ZipOutputStream(archiveBytes).use { output ->
                output.putNextEntry(ZipEntry("../escape"))
                output.write(byteArrayOf(1))
                output.closeEntry()
            }
            val platform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)
            val artifact = RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("https://example.invalid/runtime.zip"),
                ArchiveFormat.ZIP,
                sha256 = digestOf(archiveBytes.toByteArray()),
                entrypoint = "sage.exe",
            )
            val downloader = object : RuntimeDownloader {
                override fun download(
                    artifact: RuntimeArtifact,
                    destination: java.nio.file.Path,
                    progress: DownloadProgressListener,
                    cancellation: InstallationCancellation,
                ): DownloadedArtifact {
                    Files.write(destination, archiveBytes.toByteArray())
                    return DownloadedArtifact(destination, Files.size(destination), artifact.sha256)
                }
            }

            val result = ZipRuntimeInstaller(downloader).install(
                RuntimeInstallRequest(artifact, root.resolve("installed"), manifest = RuntimeManifest(
                    schemaVersion = 1,
                    runtimeId = artifact.id,
                    executable = artifact.entrypoint,
                    files = listOf(RuntimeFileRecord("sage.exe", 1, "0".repeat(64))),
                    artifactSha256 = artifact.sha256,
                ))
            )

            assertTrue(result is InstallResult.Failed)
            assertTrue((result as InstallResult.Failed).stage == "ARCHIVE_UNSAFE")
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    private fun digestOf(bytes: ByteArray): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        return digest.digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
