package com.starnotesxj.sageide.completion

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.ui.Messages
import com.intellij.ide.util.PropertiesComponent
import com.intellij.openapi.vfs.VirtualFileManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/** One stub-installation marker as written by sage-pycharm-stubgen. */
data class SageStubInstallEpoch(
    val epoch: Long,
    val stubRoot: String? = null,
    val stubRootUrl: String? = null,
    val stubgenVersion: String? = null,
)

/**
 * Closes the "stubs were reinstalled but the IDE never notices" loop.
 *
 * PyCharm 2026.2 reaches WSL files through IJent, whose change watching
 * does not report out-of-band writes — from inside WSL or through the
 * `\\wsl.localhost` share alike — so mass stub reinstalls are invisible to
 * the running IDE, and its stub index keeps serving the previous generation
 * (the recurring "frac lost completion" reports).  sage-pycharm-stubgen
 * therefore drops an `install-epoch.json` next to the sidecar index on
 * every install; this service compares it with the last epoch it processed
 * and, when it moved, refreshes the recorded stub root in the VFS and
 * reloads the sidecar — no Invalidate Caches, no user action.
 */
@Service(Service.Level.APP)
class SageStubReloadService {

    /** Reads the marker; `null` when absent, malformed, or already applied. */
    fun pendingEpoch(): SageStubInstallEpoch? {
        val state = SageApiIndexService.getInstance().loadState()
        // PRODUCT is the normal flow; EXTERNAL covers explicitly configured
        // indexes (same sidecar layout, same marker).
        if (state.origin != SageApiIndexOrigin.PRODUCT && state.origin != SageApiIndexOrigin.EXTERNAL) {
            return null
        }
        val directory = state.path?.parent ?: return null
        return runCatching {
            val text = java.nio.file.Files.readString(directory.resolve(EPOCH_FILE))
            val epoch = REGEX_EPOCH.find(text)?.groupValues?.get(1)?.toLongOrNull()
                ?: return null
            SageStubInstallEpoch(
                epoch = epoch,
                stubRoot = jsonStringMember(text, "stubRoot"),
                stubRootUrl = jsonStringMember(text, "stubRootUrl"),
                stubgenVersion = jsonStringMember(text, "stubgenVersion"),
            )
        }.getOrNull()?.takeIf {
            it.epoch > PropertiesComponent.getInstance().getLong(LAST_EPOCH_KEY, 0L)
        }
    }

    /**
     * Refreshes the stub tree recorded by [epoch] in the VFS (the WSL
     * backend re-reads the current content), reloads the sidecar, and
     * records the epoch as processed.
     */
    fun apply(epoch: SageStubInstallEpoch, project: Project?) {
        val url = epoch.stubRootUrl
        if (url != null) {
            runCatching {
                val root = VirtualFileManager.getInstance().refreshAndFindFileByUrl(url)
                root?.refresh(false, true)
            }.onFailure { error ->
                LOG.warn("Cannot refresh Sage stub root $url", error)
            }
        }
        SageApiIndexService.getInstance().reloadConfigured()
        PropertiesComponent.getInstance().setValue(LAST_EPOCH_KEY, epoch.epoch.toString(), "0")
        if (project != null) {
            NotificationGroupManager.getInstance()
                .getNotificationGroup(NOTIFICATION_GROUP)
                .createNotification(
                    "Sage 桩已更新并自动刷新索引" +
                        (epoch.stubgenVersion?.let { " (stubgen $it)" } ?: ""),
                    NotificationType.INFORMATION,
                )
                .notify(project)
        }
    }

    /** Checks once; the VFS refresh itself runs off the caller's thread. */
    fun refreshIfNeeded(project: Project?) {
        val epoch = pendingEpoch() ?: return
        ApplicationManager.getApplication().executeOnPooledThread { apply(epoch, project) }
    }

    companion object {
        const val EPOCH_FILE = "install-epoch.json"
        const val LAST_EPOCH_KEY = "sage.stub.lastInstallEpoch"
        const val NOTIFICATION_GROUP = "Sage"
        private val REGEX_EPOCH = Regex("\"epoch\"\\s*:\\s*(\\d+)")
        private val LOG = Logger.getInstance(SageStubReloadService::class.java)

        fun getInstance(): SageStubReloadService =
            ApplicationManager.getApplication().getService(SageStubReloadService::class.java)

        private fun jsonStringMember(json: String, key: String): String? =
            Regex("\"$key\"\\s*:\\s*\"([^\"]*)\"").find(json)?.groupValues?.get(1)
    }
}

/**
 * Waits for the sidecar index to finish loading, then applies a newer
 * install epoch once per project open.
 */
class SageStubReloadStartupActivity : ProjectActivity {
    override suspend fun execute(project: Project) {
        withContext(Dispatchers.Default) {
            repeat(MAX_INDEX_LOAD_POLLS) {
                val state = SageApiIndexService.getInstance().loadState()
                if (state.origin != SageApiIndexOrigin.LOADING) {
                    SageStubReloadService.getInstance().refreshIfNeeded(project)
                    return@withContext
                }
                delay(INDEX_LOAD_POLL_MILLIS)
            }
        }
    }

    private companion object {
        const val MAX_INDEX_LOAD_POLLS = 60
        const val INDEX_LOAD_POLL_MILLIS = 500L
    }
}

/** Manual trigger: Tools | Reload Sage Stubs. */
class ReloadSageStubsAction : AnAction(
    "Reload Sage Stubs",
    "Re-read the installed Sage stub tree and API index without Invalidate Caches",
    null,
) {
    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project
        val epoch = SageStubReloadService.getInstance().pendingEpoch()
        if (epoch == null) {
            if (project != null) {
                Messages.showInfoMessage(
                    project,
                    "没有待应用的 Sage 桩更新（install-epoch.json 未变化）。\n" +
                        "若刚重装过桩，请先运行 sage-pycharm-stubgen --install 生成新的 epoch 标记。",
                    "Reload Sage Stubs",
                )
            }
            return
        }
        SageStubReloadService.getInstance().apply(epoch, project)
    }

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = event.project != null
    }

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT
}
