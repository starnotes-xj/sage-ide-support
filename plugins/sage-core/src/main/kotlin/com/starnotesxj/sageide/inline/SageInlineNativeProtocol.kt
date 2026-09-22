package com.starnotesxj.sageide.inline

/**
 * Framed stdin/stdout protocol for the dependency-free native Sage scorer.
 *
 * Every payload field is hexadecimal UTF-8. This prevents CTF source code,
 * strings, comments, or Unicode from changing the line framing, while keeping
 * the native process free of a JSON dependency. The protocol is deliberately
 * single-flight: the plugin sends another request only after the prior reply
 * was consumed or the process was discarded.
 */
internal object SageInlineNativeProtocol {
    private const val VERSION = "sage-inline-v1"
    private const val MAX_CONTEXT_CHARACTERS = 2 * 1024

    fun encodeRequest(request: SageInlineScoringRequest): String {
        val candidates = request.candidates.joinToString(separator = "\n", postfix = "\n") { candidate ->
            "${candidate.name}\t${if (candidate.callable) 1 else 0}"
        }
        return listOf(
            VERSION,
            request.prefix.hexEncode(),
            candidates.hexEncode(),
            request.memberContext.takeLast(MAX_CONTEXT_CHARACTERS).hexEncode(),
        ).joinToString("\t")
    }

    fun decodeResponse(line: String): String? {
        val fields = line.split('\t')
        if (fields.size != 2 || fields[0] != VERSION) return null
        return fields[1].hexDecode()?.decodeToString()
    }

    private fun String.hexEncode(): String = encodeToByteArray().joinToString("") { byte ->
        "%02x".format(byte.toInt() and 0xff)
    }

    private fun String.hexDecode(): ByteArray? {
        if (length % 2 != 0) return null
        val decoded = ByteArray(length / 2)
        for (index in decoded.indices) {
            val high = this[index * 2].digitToIntOrNull(16) ?: return null
            val low = this[index * 2 + 1].digitToIntOrNull(16) ?: return null
            decoded[index] = ((high shl 4) or low).toByte()
        }
        return decoded
    }
}
