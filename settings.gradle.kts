pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "sage-math-ctf-ide"

include(":core:model")
include(":plugins:sage-core")

project(":core:model").projectDir = file("core/model")
project(":plugins:sage-core").projectDir = file("plugins/sage-core")
