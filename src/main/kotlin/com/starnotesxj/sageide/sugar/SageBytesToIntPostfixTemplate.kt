package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate

/**
 * `.b2i` -> `int.from_bytes(expr, "big")` — CTF bytes-to-int conversion.
 * Own class so the `postfixTemplates/SageBytesToIntPostfixTemplate/`
 * description/example resources resolve from this plugin.
 */
class SageBytesToIntPostfixTemplate(provider: PostfixTemplateProvider) : SageFixedPostfixTemplate(
    name = "int.from_bytes(expr, 'big')",
    key = ".b2i",
    example = "int.from_bytes(expr, 'big')",
    templateText = "int.from_bytes(${StringBasedPostfixTemplate.EXPR}, \"big\")\$END\$",
    provider = provider,
)
