package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider

/**
 * `.i2b` -> `int(expr).to_bytes(<len>, "big")` — CTF int-to-bytes conversion.
 * Own class so the `postfixTemplates/SageIntToBytesPostfixTemplate/`
 * description/example resources resolve from this plugin.
 */
class SageIntToBytesPostfixTemplate(provider: PostfixTemplateProvider) : SageFixedPostfixTemplate(
    name = "int(expr).to_bytes(len, 'big')",
    key = ".i2b",
    example = "int(expr).to_bytes(len, 'big')",
    // $expr$ references the target expression — see
    // SageBytesToIntPostfixTemplate.
    templateText = "int(\$expr\$).to_bytes(\$END\$, \"big\")",
    provider = provider,
)
