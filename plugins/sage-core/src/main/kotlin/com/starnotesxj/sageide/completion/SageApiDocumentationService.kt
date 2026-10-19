package com.starnotesxj.sageide.completion

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiDocumentationSidecar
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import java.nio.file.Files
import java.nio.file.Path
import java.util.LinkedHashMap

/**
 * Lazily reads indexed Sage documentation without retaining the full manual.
 *
 * Static type contracts are stored on [SageApiEntry] and are always available
 * to completion.  Documentation bodies live in small hash buckets and are
 * opened only for Quick Documentation, from either side of the sidecar
 * pipeline: the external directory installed by sage-pycharm-stubgen next to
 * the loaded index (`sage-api/<version>/sage-api-docs/`), or the classpath
 * resources shipped with a bundled product index.  The bounded cache makes
 * repeated Ctrl+Q lookups instant without allowing a long CTF session to grow
 * with every document inspected.
 */
@Service(Service.Level.APP)
class SageApiDocumentationService(
    private val externalDocsRoot: () -> Path?,
) {
    constructor() : this(::defaultExternalDocsRoot)

    private val cache = object : LinkedHashMap<String, SageApiDocumentation>(MAX_CACHED_DOCUMENTS, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, SageApiDocumentation>?): Boolean =
            size > MAX_CACHED_DOCUMENTS
    }

    fun documentation(entry: SageApiEntry): SageApiDocumentation? {
        entry.documentation?.let { return it }
        val key = SageApiDocumentationSidecar.key(entry)
        synchronized(cache) { cache[key]?.let { return it } }

        val loaded = fromExternalBucket(key) ?: fromClasspathBucket(entry)
        if (loaded == null) return null

        return synchronized(cache) {
            cache[key] ?: loaded.also { cache[key] = it }
        }
    }

    /** The stubgen-installed bucket beside the externally loaded index. */
    private fun fromExternalBucket(key: String): SageApiDocumentation? {
        val root = runCatching { externalDocsRoot() }.getOrNull() ?: return null
        val bucket = root.resolve(SageApiDocumentationSidecar.resourceName(key).substringAfterLast('/'))
        if (!Files.isRegularFile(bucket)) return null
        return runCatching {
            Files.newInputStream(bucket).use { input ->
                SageApiDocumentationSidecar.find(input, key)
            }
        }.onFailure { error ->
            LOG.warn("Cannot read indexed Sage documentation bucket ${bucket.fileName}", error)
        }.getOrNull()
    }

    /** The bucket resources shipped inside a bundled product index. */
    private fun fromClasspathBucket(entry: SageApiEntry): SageApiDocumentation? =
        runCatching {
            val resource = SageApiDocumentationSidecar.resourceName(entry)
            javaClass.classLoader.getResourceAsStream(resource)?.use { input ->
                SageApiDocumentationSidecar.find(input, entry)
            }
        }.onFailure { error ->
            LOG.warn("Cannot read indexed Sage documentation for ${entry.qualifiedName}", error)
        }.getOrNull()

    companion object {
        private const val MAX_CACHED_DOCUMENTS = 128
        private val LOG = Logger.getInstance(SageApiDocumentationService::class.java)

        fun getInstance(): SageApiDocumentationService =
            ApplicationManager.getApplication().getService(SageApiDocumentationService::class.java)
    }
}

/** The `sage-api-docs` directory next to whichever index the service loaded. */
private fun defaultExternalDocsRoot(): Path? = runCatching {
    SageApiIndexService.getInstance().loadState().path
        ?.parent
        ?.resolve(SageApiDocumentationSidecar.RESOURCE_DIRECTORY)
}.getOrNull()?.takeIf { Files.isDirectory(it) }
