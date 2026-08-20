package com.starnotesxj.sageide.run

import com.intellij.execution.actions.ConfigurationContext
import com.intellij.execution.actions.LazyRunConfigurationProducer
import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.openapi.util.Ref
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement

/**
 * Offers a Sage run configuration for .sage files (context menu, gutter).
 */
class SageRunConfigurationProducer : LazyRunConfigurationProducer<SageRunConfiguration>() {

    override fun getConfigurationFactory(): ConfigurationFactory =
        SageRunConfigurationType.getInstance().configurationFactories.single()

    override fun setupConfigurationFromContext(
        configuration: SageRunConfiguration,
        context: ConfigurationContext,
        sourceElement: Ref<PsiElement>,
    ): Boolean {
        val file = context.location?.virtualFile ?: return false
        if (file.extension != "sage") return false
        configuration.scriptPath = file.path
        configuration.name = file.nameWithoutExtension
        return true
    }

    override fun isConfigurationFromContext(
        configuration: SageRunConfiguration,
        context: ConfigurationContext,
    ): Boolean {
        val file = context.location?.virtualFile ?: return false
        return file.extension == "sage" && configuration.scriptPath == file.path
    }
}

private fun VirtualFile?.extensionOrNull(): String? = this?.extension
