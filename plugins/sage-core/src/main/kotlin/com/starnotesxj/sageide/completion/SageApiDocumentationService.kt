package com.starnotesxj.sageide.completion

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiDocumentationSidecar
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import java.util.LinkedHashMap

/**
 * Lazily reads indexed Sage documentation without retaining the full manual.
 *
 * Static type contracts are stored on [SageApiEntry] and are always available
 * to completion.  Full release bundles move their large documentation bodies
 * into small hash buckets, opened only for Quick Documentation.  The bounded
 * cache makes repeated Ctrl+Q lookups instant without allowing a long CTF
 * session to grow with every document inspected.
 */
@Service(Service.Level.APP)
class SageApiDocumentationService {
    private val cache = object : LinkedHashMap<String, SageApiDocumentation>(MAX_CACHED_DOCUMENTS, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, SageApiDocumentation>?): Boolean =
            size > MAX_CACHED_DOCUMENTS
    }

    fun documentation(entry: SageApiEntry): SageApiDocumentation? {
        entry.documentation?.let { return it }
        val key = SageApiDocumentationSidecar.key(entry)
        synchronized(cache) { cache[key]?.let { return it } }

        val loaded = runCatching {
            val resource = SageApiDocumentationSidecar.resourceName(entry)
            javaClass.classLoader.getResourceAsStream(resource)?.use { input ->
                SageApiDocumentationSidecar.find(input, entry)
            }
        }.onFailure { error ->
            LOG.warn("Cannot read indexed Sage documentation for ${entry.qualifiedName}", error)
        }.getOrNull() ?: return null

        return synchronized(cache) {
            cache[key] ?: loaded.also { cache[key] = it }
        }
    }

    companion object {
        private const val MAX_CACHED_DOCUMENTS = 128
        private val LOG = Logger.getInstance(SageApiDocumentationService::class.java)

        fun getInstance(): SageApiDocumentationService =
            ApplicationManager.getApplication().getService(SageApiDocumentationService::class.java)
    }
}
