pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "sage-math-ctf-ide"

include(":core:model")
include(":core:runtime")
include(":core:sage-api")
include(":plugins:sage-core")

project(":core:model").projectDir = file("core/model")
project(":core:runtime").projectDir = file("core/runtime")
project(":core:sage-api").projectDir = file("core/sage-api")
project(":plugins:sage-core").projectDir = file("plugins/sage-core")
