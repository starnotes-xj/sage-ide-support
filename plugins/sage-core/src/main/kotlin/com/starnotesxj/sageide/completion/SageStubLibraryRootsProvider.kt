package com.starnotesxj.sageide.completion

import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.AdditionalLibraryRootsProvider
import com.intellij.openapi.roots.SyntheticLibrary
import com.intellij.openapi.util.io.FileUtilRt
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import java.nio.file.Files
import java.nio.file.Path

/**
 * Goal C's platform channel: the stub-tree mirror that
 * sage-pycharm-stubgen installs beside the API sidecar becomes a synthetic
 * library, so the IDE's own StubIndex serves the Sage ``.pyi`` corpus.
 *
 * The mirror lives on the local configuration filesystem — unlike the WSL
 * site-packages tree under IJent, change watching and indexing work there —
 * so native completion, resolve and QuickDoc over Sage stubs keep working
 * even when the sidecar is receipt-only (no JSON index, no doc buckets).
 */
class SageStubLibraryRootsProvider : AdditionalLibraryRootsProvider() {

    override fun getAdditionalProjectLibraries(project: Project): Collection<SyntheticLibrary> =
        mirrorRoots().map(::SageStubMirrorLibrary)

    override fun getRootsToWatch(project: Project): Collection<VirtualFile> = mirrorRoots()

    private fun mirrorRoots(): Collection<VirtualFile> {
        val fileSystem = LocalFileSystem.getInstance()
        return candidateDirectories()
            .mapNotNull { directory ->
                runCatching {
                    fileSystem.refreshAndFindFileByNioFile(directory)
                }.getOrNull()
            }
            .filter { it.isValid && it.children.isNotEmpty() }
            .toList()
    }

    /** ``<home|config>/sage-api/<sageVersion>/stub-tree`` for every installed version. */
    private fun candidateDirectories(): Sequence<Path> = sequence {
        val roots = listOfNotNull(
            runCatching { com.intellij.openapi.application.PathManager.getHomeDir() }.getOrNull(),
            runCatching { com.intellij.openapi.application.PathManager.getConfigDir() }.getOrNull(),
        )
        for (root in roots) {
            val apiRoot = runCatching { root.resolve("sage-api") }.getOrNull() ?: continue
            val versions = runCatching { Files.list(apiRoot).use { it.toList() } }.getOrNull() ?: continue
            for (version in versions) {
                val mirror = version.resolve(MIRROR_DIRECTORY_NAME)
                if (Files.isDirectory(mirror)) yield(mirror)
            }
        }
    }

    private class SageStubMirrorLibrary(private val root: VirtualFile) : SyntheticLibrary() {
        override fun getSourceRoots(): Collection<VirtualFile> = listOf(root)

        override fun equals(other: Any?): Boolean = other is SageStubMirrorLibrary && other.root == root

        override fun hashCode(): Int = root.hashCode()
    }

    private companion object {
        const val MIRROR_DIRECTORY_NAME = "stub-tree"
    }
}
