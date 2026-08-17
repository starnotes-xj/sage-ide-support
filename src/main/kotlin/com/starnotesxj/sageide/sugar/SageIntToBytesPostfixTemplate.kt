package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate

/**
 * `.i2b` -> `int(expr).to_bytes(<len>, "big")` — CTF int-to-bytes conversion.
 * Own class so the `postfixTemplates/SageIntToBytesPostfixTemplate/`
 * description/example resources resolve from this plugin.
 */
class SageIntToBytesPostfixTemplate(provider: PostfixTemplateProvider) : SageFixedPostfixTemplate(
    name = "int(expr).to_bytes(len, 'big')",
    key = ".i2b",
    example = "int(expr).to_bytes(len, 'big')",
    templateText = "int(${StringBasedPostfixTemplate.EXPR}).to_bytes(\$END\$, \"big\")",
    provider = provider,
)
