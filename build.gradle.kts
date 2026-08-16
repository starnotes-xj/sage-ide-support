import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    kotlin("jvm") version "2.3.0"
    id("org.jetbrains.intellij.platform") version "2.11.0"
}

group = "com.starnotesxj"
version = "1.4.0"

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
    if (!onCi) {
        // The Python plugin jars of the local PyCharm installation (the plugin is
        // bundled with PyCharm at runtime, so nothing needs to be packaged —
        // compile-time only).  PyCharm 2026.1 splits the plugin across
        // plugins/python and plugins/python-ce
        // (psi/psi-impl/parser jars live in python-ce/lib/modules/).
        val pythonJars = files(
            fileTree("D:/JetBrains/PyCharm/plugins/python/lib") { include("**/*.jar") },
            fileTree("D:/JetBrains/PyCharm/plugins/python-ce/lib") { include("**/*.jar") },
        )
        compileOnly(pythonJars)
        testCompileOnly(pythonJars)
    }
    testImplementation("junit:junit:4.13.2")

    intellijPlatform {
        if (onCi) {
            // Downloaded on the runner; the bundled Python plugin jars are on
            // the compile classpath automatically.
            pycharmCommunity("2026.1.4")
        }
        else {
            // Local PyCharm 2026.1.4 installation as the plugin SDK.
            local("D:/JetBrains/PyCharm")
        }
        testFramework(TestFrameworkType.Platform)
    }
}

kotlin {
    jvmToolchain(21)
}

intellijPlatform {
    pluginConfiguration {
        version = "1.4.0"
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
}

tasks.test {
    // TODO: the IntelliJ platform test framework's PathClassLoader setup breaks
    // Gradle's test worker in local-SDK mode (GradleWorkerMain ClassNotFound).
    // Verification is done through `runIde` (interactive) until the runner
    // conflict is resolved; the test sources stay compiled by `compileTestKotlin`.
    enabled = false
}
