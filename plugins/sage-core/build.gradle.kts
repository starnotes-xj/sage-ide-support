import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.TestFrameworkType
import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.io.File
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

plugins {
    kotlin("jvm")
    id("org.jetbrains.intellij.platform")
}

version = rootProject.version

val onCi = System.getenv("CI") == "true"
val fullIndexPath = providers.gradleProperty("sage.bundle.fullIndex").orNull
val releaseFullIndexSha256 = providers.gradleProperty("sage.release.fullIndex.sha256").orNull
val releaseTag = providers.environmentVariable("GITHUB_REF_NAME").orNull

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    implementation(project(":core:model"))
    implementation(project(":core:runtime"))
    implementation(project(":core:sage-api"))
    testImplementation("junit:junit:4.13.2")
    testImplementation(kotlin("test"))

    intellijPlatform {
        if (onCi) {
            pycharm("2026.2.1")
        }
        else {
            local(providers.gradleProperty("sage.ide.localSdk").orElse("D:/JetBrains/PyCharm").get())
        }
        bundledPlugin("PythonCore")
        testFramework(TestFrameworkType.Platform)
    }
}

kotlin {
    jvmToolchain(25)
}

intellijPlatform {
    pluginConfiguration {
        // This ID is immutable once a plugin is public in the Marketplace.
        // Keeping the legacy Sage IDE Support ID makes SageMath Core 1.8.0 an
        // automatic update instead of a separately installed, conflicting
        // plugin.
        id = "com.starnotesxj.sageide"
        name = "SageMath Core"
        version = project.version.toString()
        description = "First-class SageMath language, runtime, type-intelligence, completion, and documentation support for PyCharm."
        ideaVersion {
            sinceBuild = "261"
            untilBuild = "263.*"
        }
        vendor {
            name = "starnotes-xj"
            email = "starnotes@qq.com"
            url = "https://github.com/starnotes-xj/sage-ide-support"
        }
    }
    buildSearchableOptions = false

    publishing {
        token = providers.environmentVariable("PUBLISH_TOKEN")
    }
}

private fun sha256(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().buffered().use { input ->
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            digest.update(buffer, 0, read)
        }
    }
    return digest.digest().joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
}

private val SAGE_DOCUMENTATION_RESOURCE_DIRECTORY = "sage-api-docs"
private val SAGE_DOCUMENTATION_FIELD_SEPARATOR = '\u001f'
private val SAGE_DOCUMENTATION_RECORD_SEPARATOR = '\t'
private val SAGE_DOCUMENTATION_BUCKET_MASK = 0x3f

private fun documentationRecord(documentation: Map<String, Any?>): String = JsonOutput.toJson(documentation)

@Suppress("UNCHECKED_CAST")
private fun splitSageIndexDocumentation(source: File, resourceRoot: File) {
    val parsed = JsonSlurper().parse(source) as? Map<String, Any?>
        ?: error("sage.bundle.fullIndex must contain a JSON object: $source")
    val entries = parsed["entries"] as? List<*>
        ?: error("sage.bundle.fullIndex must contain an entries array: $source")
    val records = linkedMapOf<String, StringBuilder>()
    val contractEntries = entries.map { value ->
        val entry = value as? Map<String, Any?>
            ?: error("sage.bundle.fullIndex entries must be JSON objects: $source")
        val documentation = entry["documentation"] as? Map<String, Any?>
        if (documentation != null) {
            val kind = entry["kind"] as? String ?: error("Sage index entry kind is missing")
            val qualifiedName = entry["qualifiedName"] as? String ?: error("Sage index entry qualifiedName is missing")
            val key = kind + SAGE_DOCUMENTATION_FIELD_SEPARATOR + qualifiedName
            val resourceName = "%s/%02x.ndjson".format(
                SAGE_DOCUMENTATION_RESOURCE_DIRECTORY,
                key.hashCode() and SAGE_DOCUMENTATION_BUCKET_MASK,
            )
            records.getOrPut(resourceName, ::StringBuilder)
                .append(key)
                .append(SAGE_DOCUMENTATION_RECORD_SEPARATOR)
                .append(documentationRecord(documentation))
                .append('\n')
        }
        entry - "documentation"
    }
    val contractIndex = parsed + ("entries" to contractEntries)
    resourceRoot.resolve("sage-api-index.json").writeText(JsonOutput.toJson(contractIndex), StandardCharsets.UTF_8)

    val documentationDirectory = resourceRoot.resolve(SAGE_DOCUMENTATION_RESOURCE_DIRECTORY)
    if (documentationDirectory.exists()) {
        check(documentationDirectory.toPath().startsWith(resourceRoot.toPath())) {
            "Refusing to remove documentation resources outside processResources output"
        }
        documentationDirectory.deleteRecursively()
    }
    records.forEach { (resourceName, lines) ->
        val target = resourceRoot.resolve(resourceName)
        target.parentFile.mkdirs()
        target.writeText(lines.toString(), StandardCharsets.UTF_8)
    }
    logger.lifecycle(
        "Bundled Sage contracts without documentation bodies: ${entries.size} entries, " +
            "${records.values.sumOf { it.count { character -> character == '\n' } }} documentation records in ${records.size} buckets",
    )
}

val verifyReleaseFullIndex = tasks.register("verifyReleaseFullIndex") {
    group = "verification"
    description = "Refuses Marketplace publication without a verified full Sage API index."
    inputs.property("sage.bundle.fullIndex", fullIndexPath ?: "")
    inputs.property("sage.release.fullIndex.sha256", releaseFullIndexSha256 ?: "")

    doLast {
        val configuredPath = requireNotNull(fullIndexPath) {
            "Marketplace publication requires -Psage.bundle.fullIndex=<sanitized full Sage API index>"
        }
        val expectedHash = requireNotNull(releaseFullIndexSha256) {
            "Marketplace publication requires -Psage.release.fullIndex.sha256=<expected SHA-256>"
        }.lowercase()
        require(expectedHash.matches(Regex("[0-9a-f]{64}"))) {
            "sage.release.fullIndex.sha256 must be a lowercase SHA-256 hex digest"
        }

        val source = file(configuredPath)
        require(source.isFile) { "sage.bundle.fullIndex must point to a regular file: $source" }
        require(source.length() >= 64L * 1024L * 1024L) {
            "Marketplace publication requires the full Sage API index, not the bundled fixture: $source"
        }
        val header = source.inputStream().buffered().use { input ->
            input.readNBytes(4096).toString(Charsets.UTF_8)
        }
        require("\"schemaVersion\"" in header && "\"sageVersion\"" in header) {
            "sage.bundle.fullIndex is not a Sage API index: $source"
        }
        val actualHash = sha256(source)
        require(actualHash == expectedHash) {
            "sage.bundle.fullIndex SHA-256 mismatch: expected $expectedHash, got $actualHash"
        }
        logger.lifecycle("Verified release Sage API index: $source ($actualHash)")
    }
}

val verifyReleaseVersion = tasks.register("verifyReleaseVersion") {
    group = "verification"
    description = "Ensures a Marketplace release tag exactly matches the plugin version."
    inputs.property("GITHUB_REF_NAME", releaseTag ?: "")

    doLast {
        val tag = requireNotNull(releaseTag) {
            "Marketplace publication requires GITHUB_REF_NAME=v${project.version}"
        }
        require(tag == "v${project.version}") {
            "Marketplace release tag $tag does not match plugin version ${project.version}"
        }
        logger.lifecycle("Verified Marketplace release tag: $tag")
    }
}

tasks.matching { it.name == "publishPlugin" }.configureEach {
    dependsOn(verifyReleaseFullIndex)
    dependsOn(verifyReleaseVersion)
}

tasks.named<ProcessResources>("processResources") {
    inputs.property("sage.bundle.fullIndex", fullIndexPath ?: "")
    doLast {
        val documentationDirectory = destinationDir.resolve(SAGE_DOCUMENTATION_RESOURCE_DIRECTORY)
        if (fullIndexPath == null && documentationDirectory.exists()) {
            check(documentationDirectory.toPath().startsWith(destinationDir.toPath())) {
                "Refusing to remove documentation resources outside processResources output"
            }
            documentationDirectory.deleteRecursively()
        }
    }
    if (fullIndexPath != null) {
        val source = file(fullIndexPath)
        inputs.file(source)
        doLast {
            require(source.isFile) { "sage.bundle.fullIndex must point to a regular file: $source" }
            splitSageIndexDocumentation(source, destinationDir)
        }
    }
}

tasks.test {
    enabled = providers.gradleProperty("runSageCoreTests").map(String::toBoolean).orElse(false).get()
    fullIndexPath?.let { path ->
        systemProperty("sage.bundle.fullIndex", path)
    }
    providers.gradleProperty("sage.external.fullIndex").orNull?.let { path ->
        systemProperty("sage.external.fullIndex", path)
    }
    providers.gradleProperty("sage.python.testSdk").orNull?.let { path ->
        systemProperty("sage.python.testSdk", path)
    }
}
