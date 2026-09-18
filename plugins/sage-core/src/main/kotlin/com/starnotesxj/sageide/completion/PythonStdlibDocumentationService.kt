package com.starnotesxj.sageide.completion

import java.nio.charset.StandardCharsets
import java.util.Base64
import java.util.LinkedHashMap

/**
 * Lazily reads the bundled CPython standard-library docstrings.
 *
 * PyCharm's typeshed stubs intentionally omit prose.  Its built-in provider
 * therefore offers a docs.python.org URL for a remote SDK, which is a poor
 * Ctrl+Q result and cannot be rendered without a local Python SDK.  These
 * records are generated from the matching CPython runtime at release time,
 * split into small hash buckets, and never execute a user interpreter in the
 * editor process.
 */
internal object PythonStdlibDocumentationService {
    private const val RESOURCE_DIRECTORY = "python-stdlib-docs"
    private const val BUCKET_MASK = 0x3f
    private const val MAX_CACHED_BUCKETS = 8

    private val bucketCache = object : LinkedHashMap<String, Map<String, String>>(MAX_CACHED_BUCKETS, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Map<String, String>>?): Boolean =
            size > MAX_CACHED_BUCKETS
    }

    fun documentationFor(qualifiedName: String): String? {
        if (!qualifiedName.matches(QUALIFIED_NAME)) return null
        return documentationForExact(qualifiedName)
            // PyCharm can omit the ``builtins.`` module prefix for both
            // functions (``len``) and methods (``list.append``).  The
            // generated source keeps the canonical runtime name; an exact
            // record is always preferred so a standard module never loses to
            // this fallback.
            ?: qualifiedName.takeUnless { it.startsWith("builtins.") }
                ?.let { documentationForExact("builtins.$it") }
    }

    private fun documentationForExact(qualifiedName: String): String? {
        val resourceName = "%s/%02x.ndjson".format(RESOURCE_DIRECTORY, qualifiedName.hashCode() and BUCKET_MASK)
        val bucket = synchronized(bucketCache) {
            bucketCache[resourceName] ?: readBucket(resourceName).also { bucketCache[resourceName] = it }
        }
        return bucket[qualifiedName]
    }

    private fun readBucket(resourceName: String): Map<String, String> {
        val stream = PythonStdlibDocumentationService::class.java.classLoader.getResourceAsStream(resourceName)
            ?: return emptyMap()
        return stream.bufferedReader(StandardCharsets.UTF_8).useLines { lines ->
            buildMap {
                lines.forEach { line ->
                    val separator = line.indexOf('\t')
                    if (separator <= 0 || separator == line.lastIndex) return@forEach
                    val qualifiedName = line.substring(0, separator)
                    val documentation = runCatching {
                        String(Base64.getDecoder().decode(line.substring(separator + 1)), StandardCharsets.UTF_8)
                    }.getOrNull()?.takeIf { it.isNotBlank() }
                    if (documentation != null) put(qualifiedName, documentation)
                }
            }
        }
    }

    private val QUALIFIED_NAME = Regex("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)*")
}
