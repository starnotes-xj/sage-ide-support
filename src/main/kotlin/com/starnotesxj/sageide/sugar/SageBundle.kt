package com.starnotesxj.sageide.sugar

import com.intellij.DynamicBundle
import org.jetbrains.annotations.NonNls
import org.jetbrains.annotations.PropertyKey

/**
 * Plugin-local message bundle (UTF-8 properties in `messages/`).
 *
 * The IDE locale selects the file: `SageBundle_zh_CN.properties` is picked up
 * automatically when the IDE runs with the zh-CN language pack, so UI text
 * such as the New-menu file-template entry reads "Sage 文件" on a Chinese
 * IDE and "Sage File" on an English one.
 */
object SageBundle {

    @NonNls
    private const val BUNDLE = "messages.SageBundle"

    private val instance = DynamicBundle(SageBundle::class.java, BUNDLE)

    @JvmStatic
    fun message(@PropertyKey(resourceBundle = BUNDLE) key: String, vararg params: Any): String =
        instance.getMessage(key, *params)
}
