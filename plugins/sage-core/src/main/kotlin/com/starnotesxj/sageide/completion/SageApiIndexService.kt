package com.starnotesxj.sageide.completion

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.starnotesxj.sagemath.sageapi.SageApiIndexLoader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import java.nio.file.Path

/** Application-scoped holder for the validated Sage API index. */
@Service(Service.Level.APP)
class SageApiIndexService {
    @Volatile
    private var current: SageApiIndexQuery? = null

    private val loader = SageApiIndexLoader()

    init {
        val configuredPath = System.getProperty(INDEX_PATH_PROPERTY)?.takeIf { it.isNotBlank() }
        if (configuredPath == null || !reload(Path.of(configuredPath))) {
            reloadBundled()
        }
    }

    fun install(query: SageApiIndexQuery?) {
        current = query
    }

    fun query(): SageApiIndexQuery? = current

    private fun reloadBundled(): Boolean {
        val index = loader.fromResource(javaClass.classLoader, BUNDLED_INDEX_RESOURCE)
        if (index == null) {
            LOG.warn("Cannot load bundled Sage API index; indexed completion remains unavailable")
            return false
        }
        install(SageApiIndexQuery(index))
        return true
    }

    fun reload(path: Path): Boolean {
        val index = loader.fromPath(path)
        if (index == null) {
            LOG.warn("Cannot load Sage API index from $path; keeping the previous index")
            return false
        }
        install(SageApiIndexQuery(index))
        return true
    }

    companion object {
        const val INDEX_PATH_PROPERTY = "sage.api.index"
        private const val BUNDLED_INDEX_RESOURCE = "sage-api-index.json"
        private val LOG = Logger.getInstance(SageApiIndexService::class.java)

        fun getInstance(): SageApiIndexService =
            ApplicationManager.getApplication().getService(SageApiIndexService::class.java)
    }
}
