# Solución al Error de Conexión (Connection Refused / Timeout)

El error `failed to connect to /10.10.0.220 (port 5000)` indica que la aplicación Android no puede alcanzar el servidor backend en la dirección IP configurada. Esto suele suceder por configuraciones de red incorrectas entre el dispositivo (o emulador) y la computadora que corre el backend.

## User Review Required

> [!IMPORTANT]
> Necesito saber si estás usando un **emulador** o un **dispositivo físico** conectado por USB. Dependiendo de esto, la solución varía.

## Proposed Changes

### [Network Configuration]

Modificaremos la configuración de `RetrofitClient.kt` para usar la dirección correcta según tu entorno.

#### [MODIFY] [RetrofitClient.kt](file:///C:/Users/USUARIO/Documents/Proyecto_Final/domux-ga4/android/app/src/main/java/com/dracknoval/domux/data/RetrofitClient.kt)
- Cambiar `BASE_URL` a la opción adecuada.

### Opciones de Solución

1.  **Si usas el Emulador de Android Studio:**
    - La dirección IP debe ser `http://10.0.2.2:5000`. Android reserva `10.0.2.2` para referirse al "localhost" de tu computadora.
2.  **Si usas un Dispositivo Físico (vía USB):**
    - Lo más sencillo es usar `adb reverse`.
    - Ejecuta en tu terminal: `adb reverse tcp:5000 tcp:5000`
    - Configura la URL como `http://127.0.0.1:5000`.
3.  **Si usas un Dispositivo Físico (vía Wi-Fi):**
    - Ambos deben estar en la misma red.
    - Debes verificar que la IP de tu PC sea realmente `10.10.0.220`.
    - El backend (Flask) debe estar corriendo con `--host=0.0.0.0` para aceptar conexiones externas, no solo `127.0.0.1`.

## Verification Plan

### Manual Verification
1.  Corregir la URL en `RetrofitClient.kt`.
2.  Asegurarse de que el backend esté encendido y escuchando en el puerto 5000.
3.  Si es necesario, ejecutar el comando `adb reverse`.
4.  Re-lanzar la aplicación y verificar que no aparezca el error de conexión.
