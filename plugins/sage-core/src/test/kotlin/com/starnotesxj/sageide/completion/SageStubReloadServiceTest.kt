package com.starnotesxj.sageide.completion

import com.intellij.ide.util.PropertiesComponent
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.testFramework.runInEdtAndGet
import com.starnotesxj.sageide.SagePluginTestBase
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Epoch-driven stub auto-reload: the python generator drops
 * `install-epoch.json` beside the sidecar index; this service must detect a
 * newer epoch exactly once, refresh the recorded stub root in the VFS, and
 * remember the epoch.  The marker fixture is byte-compatible with
 * sage-pycharm-stubgen `sidecar.build_install_epoch`.
 */
class SageStubReloadServiceTest : SagePluginTestBase() {

    private fun stageSidecar(temp: Path, epochJson: String): Path {
        val index = temp.resolve("sage-api-index.json")
        Files.writeString(
            index,
            "{\"schemaVersion\":1,\"sageVersion\":\"10.9\",\"pythonVersion\":\"3.13\",\"generatorVersion\":\"test\",\"entries\":[]}",
        )
        Files.writeString(temp.resolve("install-epoch.json"), epochJson)
        SageApiIndexService.getInstance().reload(index)
        return index
    }

    fun testNewerEpochIsPendingExactlyOnce() {
        val temp = Files.createTempDirectory("sage-epoch")
        try {
            stageSidecar(temp, """{"epoch": 900, "stubgenVersion": "0.9.21"}""")
            val service = SageStubReloadService()

            val pending = service.pendingEpoch() ?: error("epoch marker not detected")
            assertEquals(900L, pending.epoch)
            assertEquals("0.9.21", pending.stubgenVersion)

            PropertiesComponent.getInstance()
                .setValue(SageStubReloadService.LAST_EPOCH_KEY, "900", "0")
            assertNull(service.pendingEpoch())
        } finally {
            temp.toFile().deleteRecursively()
        }
    }

    fun testApplyRefreshesTheRecordedStubRootUrl() {
        val temp = Files.createTempDirectory("sage-epoch-apply")
        val stubRoot = Files.createTempDirectory("sage-stubs")
        try {
            stageSidecar(temp, """{"epoch": 901, "stubRootUrl": "${stubRoot.toUri()}"}""")
            val service = SageStubReloadService()

            val touched = stubRoot.resolve("marker.txt")
            Files.writeString(touched, "fresh")

            val pending = service.pendingEpoch() ?: error("epoch marker not detected")
            runInEdtAndGet { service.apply(pending, project) }

            assertEquals(
                "901",
                PropertiesComponent.getInstance()
                    .getValue(SageStubReloadService.LAST_EPOCH_KEY, "0"),
            )
            // The recorded URL was resolvable: the marker file is visible
            // through the VFS after the refresh.
            val virtual = LocalFileSystem.getInstance()
                .refreshAndFindFileByNioFile(touched)
                ?: error("marker file not visible through the VFS after refresh")
            assertEquals("fresh", String(virtual.contentsToByteArray()))
            assertTrue(virtual.isValid)
        } finally {
            temp.toFile().deleteRecursively()
            stubRoot.toFile().deleteRecursively()
        }
    }

    fun testMissingMarkerYieldsNull() {
        val temp = Files.createTempDirectory("sage-epoch-empty")
        try {
            stageSidecar(temp, "{}")
            assertNull(SageStubReloadService().pendingEpoch())
        } finally {
            temp.toFile().deleteRecursively()
        }
    }
}
