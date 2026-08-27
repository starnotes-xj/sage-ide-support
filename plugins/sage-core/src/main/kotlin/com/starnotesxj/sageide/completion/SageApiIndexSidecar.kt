package com.starnotesxj.sageide.completion

import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest

internal data class ProductSidecarMetadata(
    val sha256: String,
    val artifactId: String,
    val entryCount: Int,
)

internal fun sha256(path: Path): String {
    val digest = MessageDigest.getInstance("SHA-256")
    Files.newInputStream(path).use { input ->
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE * 16)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            digest.update(buffer, 0, count)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}
