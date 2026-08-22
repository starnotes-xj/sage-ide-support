package com.starnotesxj.sagemath.sageapi

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/** Loads only schema-validated Sage API index artifacts. */
class SageApiIndexLoader {
    fun fromJson(json: String): SageApiIndex = SageApiIndexJsonReader.read(json)

    fun fromPath(path: Path): SageApiIndex? = runCatching {
        fromJson(Files.readString(path, StandardCharsets.UTF_8))
    }.getOrNull()

    fun fromResource(classLoader: ClassLoader, resource: String): SageApiIndex? = runCatching {
        classLoader.getResourceAsStream(resource)?.use { input ->
            fromJson(input.bufferedReader(StandardCharsets.UTF_8).use { it.readText() })
        }
    }.getOrNull()

    fun externalOrBundled(path: Path?, classLoader: ClassLoader, resource: String): SageApiIndex? {
        val external = path?.let(::fromPath)
        return external ?: fromResource(classLoader, resource)
    }
}
