package com.starnotesxj.sageide

import com.intellij.DynamicBundle

private const val SAGE_BUNDLE = "messages.SageBundle"

/** User-visible plugin text resolved through the IDE's active language pack. */
object SageBundle {

    private val bundle = DynamicBundle(SageBundle::class.java, SAGE_BUNDLE)

    @JvmStatic
    fun message(key: String, vararg parameters: Any): String = bundle.getMessage(key, *parameters)
}
