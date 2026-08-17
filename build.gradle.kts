import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    kotlin("jvm") version "2.3.0"
    id("org.jetbrains.intellij.platform") version "2.11.0"
}

group = "com.starnotesxj"
version = "1.7.2"

// GitHub Actions sets CI=true; there is no local PyCharm on the runner, so the
// SDK is downloaded there.  Locally the existing PyCharm installation is used.
val onCi = System.getenv("CI") == "true"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")

    intellijPlatform {
        if (onCi) {
            // Downloaded on the runner.  (PyCharm Community is no longer
            // published since 2025.3, hence the unified accessor.)
            pycharm("2026.2.1")
        }
        else {
            // Local PyCharm 2026.2.1 installation as the plugin SDK.
            local("D:/JetBrains/PyCharm")
        }
        // The Python PSI/parser classes: with the 2026.1 split layout they
        // live in the bundled python-ce plugin (lib + lib/modules), which is
        // not on the default product classpath.
        bundledPlugin("PythonCore")
        testFramework(TestFrameworkType.Platform)
    }
}

kotlin {
    jvmToolchain(21)
}

intellijPlatform {
    pluginConfiguration {
        version = "1.7.2"
        ideaVersion {
            // The whole PyCharm 2026 release year: 2026.1 (261) .. 2026.3 (263).
            // The plugin only uses stable, long-standing extension points, so a
            // single build covers the full year.
            sinceBuild = "261"
            untilBuild = "263.*"
        }
    }
    // The settings search index needs an IDE lock that conflicts with the
    // interactive runIde instance; the plugin has no searchable settings.
    buildSearchableOptions = false

    // JetBrains Marketplace publishing (https://plugins.jetbrains.com):
    // `gradle publishPlugin` uploads with the token from the PUBLISH_TOKEN
    // environment variable (created on the JetBrains Marketplace site).
    publishing {
        token = providers.environmentVariable("PUBLISH_TOKEN")
    }

    // Compatibility verification (local equivalent of the Marketplace
    // "Verification" page): checks the plugin against every IDE build we
    // declare support for (since-build 261 .. until-build 263).  The plugin
    // was only ever built/run against 2026.2.1 before, so 2026.1.4 and
    // 2026.3 are unverified until this runs.
    pluginVerification {
        ides {
            // PyCharm Community is no longer published separately since
            // 2025.3 — use the unified PyCharm product (same as the SDK
            // accessor `pycharm(...)`).  2026.3 has no published build yet,
            // so only the two released versions are verified for now.
            create(IntelliJPlatformType.PyCharm, "2026.1.4")
            create(IntelliJPlatformType.PyCharm, "2026.2.1")
        }
    }
}

tasks.test {
    // TODO: the IntelliJ platform test framework's PathClassLoader setup breaks
    // Gradle's test worker in local-SDK mode (GradleWorkerMain ClassNotFound).
    // Verification is done through `runIde` (interactive) until the runner
    // conflict is resolved; the test sources stay compiled by `compileTestKotlin`.
    enabled = false
}
