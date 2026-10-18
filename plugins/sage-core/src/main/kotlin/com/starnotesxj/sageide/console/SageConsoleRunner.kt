package com.starnotesxj.sageide.console

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.console.LanguageConsoleBuilder
import com.intellij.execution.console.LanguageConsoleImpl
import com.intellij.execution.console.LanguageConsoleView
import com.intellij.execution.console.ProcessBackedConsoleExecuteActionHandler
import com.intellij.execution.executors.DefaultRunExecutor
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.ui.RunContentDescriptor
import com.intellij.execution.ui.RunContentManager
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.starnotesxj.sageide.sugar.SageLanguage
import com.starnotesxj.sageide.run.SageRunSettings
import com.starnotesxj.sageide.run.configuredWslSageExecutable
import com.starnotesxj.sageide.run.wslDirectRunArguments

/**
 * An interactive Sage REPL bound to the configured runtime (v1: native and
 * WSL targets; Docker/SSH consoles need PTY channels and are refused with a
 * clear message).  The console reuses the run pipeline's executable
 * resolution so the console and "Run Sage Script" always target the same
 * SageMath installation.
 */
object SageConsoleRunner {
    private val LOG = Logger.getInstance(SageConsoleRunner::class.java)
    private const val CONSOLE_TITLE = "Sage Console"

    fun open(project: Project) {
        ProgressManager.getInstance().runProcessWithProgressSynchronously<String, Exception>(
            {
                try {
                    openInternal(project)
                } catch (e: Exception) {
                    LOG.warn("Sage console failed to start", e)
                    Messages.showErrorDialog(project, e.message ?: e.toString(), CONSOLE_TITLE)
                }
                null
            },
            "Starting Sage Console",
            true,
            project,
        )
    }

    private fun openInternal(project: Project) {
        val settings = SageRunSettings.getInstance().getState()
        val commandLine = when (settings.executionMode) {
            "WSL" -> {
                val distribution = settings.wslDistribution.ifBlank { "Ubuntu" }
                val executable = configuredWslSageExecutable(settings) ?: "sage"
                GeneralCommandLine("wsl.exe")
                    .withParameters(wslDirectRunArguments(distribution, executable, emptyList()))
            }
            "NATIVE" -> {
                val executable = settings.nativeSageExecutable.trim()
                if (executable.isBlank()) {
                    throw IllegalStateException(
                        "NATIVE runtime selected but no Sage executable is configured in Run Settings",
                    )
                }
                GeneralCommandLine(executable)
            }
            "DOCKER", "SSH" -> throw IllegalStateException(
                "The interactive Sage console currently supports NATIVE and WSL runtimes only; " +
                    "switch the execution mode in Run Settings to open a console.",
            )
            else -> throw IllegalStateException("Unknown execution mode: ${settings.executionMode}")
        }
        commandLine.withCharset(Charsets.UTF_8)

        val handler = OSProcessHandler(commandLine)
        // The builder wires the process handler to the console, including the
        // enter-to-execute action; the REPL prints its own prompts.
        val console: LanguageConsoleView =
            LanguageConsoleImpl(project, CONSOLE_TITLE, SageLanguage.INSTANCE)
        LanguageConsoleBuilder(console)
            .processHandler(handler)
            .initActions(ProcessBackedConsoleExecuteActionHandler(handler, true), "Console.Execute")
            .build(project, SageLanguage.INSTANCE)

        val descriptor = RunContentDescriptor(console, handler, console.component, CONSOLE_TITLE, null)
        descriptor.isAutoFocusContent = true
        RunContentManager.getInstance(project)
            .showRunContent(DefaultRunExecutor.getRunExecutorInstance(), descriptor)
    }
}
