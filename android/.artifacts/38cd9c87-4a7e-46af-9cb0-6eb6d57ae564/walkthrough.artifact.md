# Solución de Conexión para Dispositivo Físico

Como estás usando un celular conectado por cable, la mejor forma de conectarlo al backend de tu PC es mediante **ADB Reverse**. Esto permite que el celular vea el "localhost" de tu PC a través del cable USB.

## Cambios Realizados

### [RetrofitClient.kt](file:///C:/Users/USUARIO/Documents/Proyecto_Final/domux-ga4/android/app/src/main/java/com/dracknoval/domux/data/RetrofitClient.kt)
He cambiado la `BASE_URL` para que apunte a `127.0.0.1`.

```kotlin
private const val BASE_URL = "http://127.0.0.1:5000/"
```

## Pasos Cruciales para ti

> [!TIP]
> **¡Buenas noticias!** He logrado ejecutar el comando `adb reverse` por ti directamente desde aquí, usando la ruta completa de las herramientas de Android en tu PC.
>
> Ya no necesitas ejecutarlo tú. El túnel entre tu celular y tu PC ya está activo.

### Verificación Final
1.  Asegúrate de que tu backend en VSCode siga diciendo `Running on http://127.0.0.1:5000`.
2.  **Vuelve a correr la app en Android Studio.**
3.  Ahora debería conectar sin problemas.

Si al ejecutar el comando te sale un error de que no se encuentra `adb`, asegúrate de tener activada la **Depuración USB** en tu celular.
