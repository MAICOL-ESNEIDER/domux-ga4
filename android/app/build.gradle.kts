plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.dracknoval.domux"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.dracknoval.domux"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        // URL base del backend. Cambia aquí o sobreescribe en distintos builds si lo necesitas.
        // Por defecto apunta al servicio desplegado en Render; para desarrollo local usa 10.0.2.2:5000.
        buildConfigField("String", "BASE_URL", "\"https://domux-backend.onrender.com/\"")

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    // Definir flavors para poder cambiar la BASE_URL sin editar código.
    flavorDimensions += "environment"
    productFlavors {
        create("dev") {
            dimension = "environment"
            // EMULADOR: "http://10.0.2.2:5000/"
            // DISPOSITIVO FÍSICO, la IP local del PC,: "http://192.168.1.5:5000/"
            buildConfigField("String", "BASE_URL", "\"10.0.2.2:5000/\"")
        }
        create("prod") {
            dimension = "environment"
            // URL por defecto apuntando al servicio desplegado en Render
            buildConfigField("String", "BASE_URL", "\"https://domux-backend.onrender.com/\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        // Habilitar generación de BuildConfig para poder usar buildConfigField por flavor
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3:1.3.0")
    implementation("com.google.android.material:material:1.12.0")
    // Navigation Compose: nos deja movernos entre pantallas con rutas ("login", "home", etc.)
    implementation("androidx.navigation:navigation-compose:2.8.1")
    // Retrofit + Gson: consumo de la API REST del backend Flask.
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.11.0")
    // Corrutinas: para las funciones "suspend" de las llamadas de red.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
