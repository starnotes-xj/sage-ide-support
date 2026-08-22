package com.starnotesxj.sageide.completion

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/** Application-scoped holder for the validated Sage API index. */
@Service(Service.Level.APP)
class SageApiIndexService {
    @Volatile
    private var current: SageApiIndexQuery? = null

    init {
        System.getProperty(INDEX_PATH_PROPERTY)?.takeIf { it.isNotBlank() }?.let { reload(Path.of(it)) }
            ?: reloadBundled()
    }

    fun install(query: SageApiIndexQuery?) {
        current = query
    }

    fun query(): SageApiIndexQuery? = current

    private fun reloadBundled(): Boolean = runCatching {
        val stream = javaClass.classLoader.getResourceAsStream(BUNDLED_INDEX_RESOURCE) ?: return false
        val json = stream.bufferedReader(StandardCharsets.UTF_8).use { it.readText() }
        install(SageApiIndexQuery(SageApiIndexJsonReader.read(json)))
        true
    }.getOrElse {
        LOG.warn("Cannot load bundled Sage API index; indexed completion remains unavailable", it)
        false
    }

    fun reload(path: Path): Boolean = runCatching {
        install(SageApiIndexQuery(SageApiIndexJsonReader.read(Files.readString(path))))
        true
    }.getOrElse {
        LOG.warn("Cannot load Sage API index from $path; keeping the previous index", it)
        false
    }

    companion object {
        const val INDEX_PATH_PROPERTY = "sage.api.index"
        private const val BUNDLED_INDEX_RESOURCE = "sage-api-index.json"
        private val LOG = Logger.getInstance(SageApiIndexService::class.java)

        fun getInstance(): SageApiIndexService =
            ApplicationManager.getApplication().getService(SageApiIndexService::class.java)
    }
}
