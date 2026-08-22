package com.starnotesxj.sagemath.sageapi

/**
 * Unified source-driven generator entry point for IDE and build tooling.
 *
 * Build tooling may provide richer runtime/stub/documentation inputs, while this
 * entry point keeps extraction and normalization behavior identical for fixtures
 * and in-process generation. No Sage symbol names are hard-coded here.
 */
class SageApiIndexGenerator(
    private val extractor: SageStubExtractor = SageStubExtractor(),
    private val normalizer: SageApiNormalizer = SageApiNormalizer(),
) {
    fun generate(version: SageApiVersion, sources: List<SageStubSource>): SageApiNormalizationResult =
        normalizer.normalize(version, sources.flatMap(extractor::extract))
}
