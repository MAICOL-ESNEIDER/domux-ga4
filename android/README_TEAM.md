Instrucciones rápidas para el equipo — Domux Android

Propósito
- El proyecto tiene dos flavors: dev y prod.
  - dev -> usa el backend local: http://10.0.2.2:5000/
  - prod -> usa el backend desplegado en Render: https://domux-backend.onrender.com/

Comandos (PowerShell)
1) Compilar e instalar la versión de desarrollo (con backend local):
   cd android
   $env:JAVA_HOME = "C:\\Program Files\\Microsoft\\jdk-17.0.20.101-hotspot"
   $env:PATH = "$env:JAVA_HOME\\bin;$env:PATH"
   .\gradlew.bat installDevDebug
   & "$env:ANDROID_SDK_ROOT\\platform-tools\\adb.exe" shell am start -n com.dracknoval.domux/com.dracknoval.domux.MainActivity

2) Compilar la versión prod (apunta a Render):
   cd android
   .\gradlew.bat assembleProdDebug

Notas
- Para que dev funcione, el backend local debe estar levantado en tu máquina en el puerto 5000 (python app.py).
- Desde el emulador Android, la IP `10.0.2.2` representa tu PC local.
- Si necesitas cambiar la URL de prod, edita `android/app/build.gradle.kts` en el bloque `productFlavors` -> `prod` -> `buildConfigField`.
- No compartas credenciales de la base de datos. Si alguien quiere usar la DB en Render desde su servidor local, que pida las credenciales por un canal seguro.

Contacto
- Si hay problemas con la build (OOM en R8), aumentar org.gradle.jvmargs en android/gradle.properties.

Usuarios de prueba
- admin@domux.com / admin123

Fin.