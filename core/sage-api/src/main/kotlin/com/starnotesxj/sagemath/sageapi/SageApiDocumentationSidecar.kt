package com.starnotesxj.sagemath.sageapi

import java.io.InputStream
import java.nio.charset.StandardCharsets

/**
 * Compact, line-oriented documentation storage for a Sage API index.
 *
 * Type contracts are queried during every editor analysis pass, whereas a
 * documentation body is needed only for Quick Documentation.  Keeping the
 * latter in a sidecar lets the main index stay focused on completion and type
 * inference.  A lookup scans a compressed resource one line at a time, so it
 * never builds a second full documentation map in the IDE heap.
 */
object SageApiDocumentationSidecar {
    const val RESOURCE_DIRECTORY: String = "sage-api-docs"

    // 64 buckets keep a Ctrl+Q scan below roughly one megabyte on the Sage
    // 10.9 full index while preserving ZIP compression across related docs.
    private const val BUCKET_COUNT = 64
    private const val FIELD_SEPARATOR = '\u001f'
    private const val RECORD_SEPARATOR = '\t'

    /** Creates the contract-only counterpart of an index without changing its API surface. */
    fun withoutDocumentation(index: SageApiIndex): SageApiIndex = index.copy(
        entries = index.entries.map { entry -> entry.copy(documentation = null) },
    )

    /** Serializes documentation as one independently decodable entry per line. */
    fun write(index: SageApiIndex): String = buildString {
        index.entries
            .asSequence()
            .filter { it.documentation != null }
            .sortedWith(compareBy<SageApiEntry> { it.qualifiedName }.thenBy { it.kind.name })
            .forEach { entry -> appendLine(entry) }
    }

    /**
     * Partitions documents into small classpath resources.  A Ctrl+Q lookup
     * opens only one bucket rather than streaming the complete Sage manual.
     */
    fun writeBuckets(index: SageApiIndex): Map<String, String> {
        val buckets = linkedMapOf<String, StringBuilder>()
        index.entries
            .asSequence()
            .filter { it.documentation != null }
            .sortedWith(compareBy<SageApiEntry> { it.qualifiedName }.thenBy { it.kind.name })
            .forEach { entry ->
                buckets.getOrPut(resourceName(entry), ::StringBuilder).appendLine(entry)
            }
        return buckets.mapValues { (_, lines) -> lines.toString() }
    }

    /** Finds one document while retaining only its matching line in memory. */
    fun find(input: InputStream, entry: SageApiEntry): SageApiDocumentation? = find(input, key(entry))

    /** Finds one document while retaining only its matching line in memory. */
    fun find(input: InputStream, expectedKey: String): SageApiDocumentation? = runCatching {
        input.bufferedReader(StandardCharsets.UTF_8).use { reader ->
            var result: SageApiDocumentation? = null
            while (result == null) {
                val line = reader.readLine() ?: break
                val separator = line.indexOf(RECORD_SEPARATOR)
                if (separator <= 0 || line.substring(0, separator) != expectedKey) continue
                result = SageApiIndexJsonReader.readDocumentation(line.substring(separator + 1))
            }
            result
        }
    }.getOrNull()

    fun key(entry: SageApiEntry): String = entry.kind.name + FIELD_SEPARATOR + entry.qualifiedName

    fun resourceName(entry: SageApiEntry): String = resourceName(key(entry))

    fun resourceName(key: String): String = "%s/%02x.ndjson".format(
        RESOURCE_DIRECTORY,
        key.hashCode() and (BUCKET_COUNT - 1),
    )

    private fun StringBuilder.appendLine(entry: SageApiEntry) {
        append(key(entry))
        append(RECORD_SEPARATOR)
        append(SageApiIndexJsonWriter.writeDocumentation(requireNotNull(entry.documentation)))
        append('\n')
    }
}
