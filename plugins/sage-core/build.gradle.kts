import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    kotlin("jvm")
    id("org.jetbrains.intellij.platform")
}

version = rootProject.version

val onCi = System.getenv("CI") == "true"

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
        id = "com.starnotesxj.sagemath.ctf.sage-core"
        name = "SageMath Core"
        version = project.version.toString()
        description = "SageMath language, runtime and scientific-computing support for SageMath CTF IDE."
        ideaVersion {
            sinceBuild = "261"
            untilBuild = "263.*"
        }
        vendor {
            name = "starnotes-xj"
            email = "starnotes@qq.com"
            url = "https://github.com/starnotes-xj/sage-math-ctf-ide"
        }
    }
    buildSearchableOptions = false
}

tasks.test {
    enabled = providers.gradleProperty("runSageCoreTests").map(String::toBoolean).orElse(false).get()
}
