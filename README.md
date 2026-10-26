# Domux — App de gestión de unidad residencial (Proyecto GA4)

Proyecto final (GA4) del programa Análisis y Desarrollo de Software — adaptación
reducida del proyecto de grado **Domux** como app Android que consume un backend
REST propio (Flask + base de datos real), siguiendo la misma arquitectura
enseñada en las guías GA1-GA3 (Retrofit + `Models.kt`/`ApiService.kt`/
`RetrofitClient.kt`/`Session.kt` + Navigation Compose).

## Qué hace la app

Tres roles, un solo login:

| Rol                      | Puede hacer                                                                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Administrador**        | Crear y editar usuarios · restablecer contraseñas · publicar/eliminar anuncios · gestionar PQRS y reservas · registrar paquetes y visitas · bandeja de notificaciones |
| **Residente**            | Ver anuncios · crear y ver sus PQRS · reservar/cancelar zonas comunes · consultar paquetes, visitas y notificaciones |
| **Guardia de seguridad** | Registrar paquetes y visitas a nombre de un residente · marcar paquetes como entregados |

Cada acción reservada está protegida en **dos capas**: la app oculta las
opciones según el rol (`Session.isAdmin` / `isResident` / `isGuard`), y el
backend vuelve a comprobar el rol en cada endpoint — si alguien llama a la API
directamente sin el permiso adecuado, recibe **403**.

## Estructura del repositorio

```
├── android/     → Proyecto de Android Studio (ábrelo apuntando a esta carpeta)
├── backend/     → API REST en Flask (desplegable en Render)
│   ├── routes/  → Blueprints separados por responsabilidad
│   ├── errors.py → Respuestas JSON y manejo global de errores
│   └── logging_config.py → Auditoría de solicitudes y errores
└── render.yaml  → Blueprint para desplegar el backend en Render de un clic
```

---

## 1. Levantar el backend en local

```bash
cd backend
python -m venv venv
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Debe quedar escuchando en `http://localhost:5000/`. La variante Android `dev`
lo alcanza desde el emulador mediante `http://10.0.2.2:5000/`. La primera vez que arranca
crea la base de datos (`domux.db`, SQLite) y siembra estos **usuarios de
prueba**:

| Rol           | Correo              | Contraseña     |
| ------------- | ------------------- | -------------- |
| Administrador | `admin@domux.com`   | `Admin123*`     |
| Guardia       | `guardia@domux.com` | `Guardia123*`   |
| Residente     | `maria@domux.com`   | `Residente123*` |
| Residente     | `carlos@domux.com`  | `Residente123*` |

El backend registra el inicio y resultado de cada solicitud, además de las
excepciones no controladas, únicamente en la salida de consola del servidor.
`LOG_LEVEL=WARNING` permite cambiar el nivel de detalle. Los errores HTTP
devuelven un JSON uniforme con las claves `error` y `status`.
Configura `JWT_SECRET` en el entorno desplegado para mantener la clave fuera
del código; si no está definida, el MVP usa una clave estable de respaldo.

## 2. Abrir y correr la app Android

1. Abre Android Studio → **Open** → selecciona la carpeta `android/` (no la
   raíz del repo).
2. Espera a que sincronice Gradle.
3. Elige la variante de compilación según el backend:
   - `devDebug`: backend local en `http://10.0.2.2:5000/`.
   - `prodDebug`: backend desplegado en Render.
   En Android Studio se selecciona desde **Build Variants**. También puedes usar
   `./gradlew.bat :app:assembleDevDebug` o `./gradlew.bat :app:assembleProdDebug`.
4. Para `devDebug`, corre el backend local (paso 1) antes de ejecutar la app.
   Para `prodDebug`, no necesitas levantar Flask localmente: la app consume Render.
5. Inicia sesión con cualquiera de los usuarios de prueba de la tabla anterior.

## 3. Desplegar el backend en Render

1. Sube este repo a GitHub (ver sección de Git más abajo).
2. En Render: **New +** → **Blueprint** → conecta el repo → Render detecta
   `render.yaml` solo y crea el servicio web `domux-backend` **y** la base de
   datos Postgres `domux-db`, ya conectados.
4. Cuando termine el deploy, Render te da una URL tipo
   `https://domux-backend.onrender.com`. La variante `prod` ya está configurada
   para consumir esa URL; si Render asigna otra, actualiza `BASE_URL` en
   `android/app/build.gradle.kts` y recompila `prodDebug`.
5. `render.yaml` ya arregla el detalle de que Render entrega la URL de
   Postgres como `postgres://` y la app la convierte a `postgresql://`
   automáticamente (si no, SQLAlchemy falla al conectar).

## 4. Contrato de la API (tabla de endpoints)

| Funcionalidad                    | Método y ruta                       | ¿Token? | ¿Rol?                                    | Códigos de error   |
| -------------------------------- | ----------------------------------- | ------- | ---------------------------------------- | ------------------ |
| Login                            | `POST /api/auth/login`              | No      | —                                        | 401                |
| Listar usuarios                  | `GET /api/users`                    | Sí      | ADMIN                                    | 401, 403           |
| Crear usuario                    | `POST /api/users`                   | Sí      | ADMIN                                    | 400, 401, 403, 409 |
| Listar residentes (para asignar) | `GET /api/residents`                | Sí      | ADMIN, GUARD                             | 401, 403           |
| Ver anuncios                     | `GET /api/announcements`            | Sí      | cualquiera                               | 401                |
| Publicar anuncio                 | `POST /api/announcements`           | Sí      | ADMIN                                    | 400, 401, 403      |
| Ver PQRS                         | `GET /api/pqrs`                     | Sí      | ADMIN (todas), RESIDENT (propias)        | 401, 403           |
| Crear PQRS                       | `POST /api/pqrs`                   | Sí      | RESIDENT; ADMIN con `residentId`         | 400, 401, 403      |
| Agregar mensaje a PQRS           | `POST /api/pqrs/{id}/messages`     | Sí      | RESIDENT (propia)                        | 400, 401, 403, 404 |
| Responder/actualizar PQRS        | `PUT /api/pqrs/{id}/respond`       | Sí      | ADMIN                                    | 400, 401, 403, 404 |
| Responder varias PQRS            | `POST /api/pqrs/batch/respond`     | Sí      | ADMIN                                    | 400, 401, 403, 404, 500 |
| Calificar una PQRS resuelta      | `PUT /api/pqrs/{id}/satisfaction`  | Sí      | RESIDENT (propia)                        | 400, 401, 403, 404 |
| Ver zonas comunes                | `GET /api/common-areas`             | Sí      | cualquiera                               | 401                |
| Ver reservas                     | `GET /api/reservations`             | Sí      | ADMIN (todas), RESIDENT (propias)        | 401, 403           |
| Crear reserva                    | `POST /api/reservations`            | Sí      | RESIDENT                                 | 400, 401, 403      |
| Cancelar reserva                 | `PUT /api/reservations/{id}/cancel` | Sí      | RESIDENT (propia), ADMIN                 | 401, 403, 404      |
| Ver paquetes                     | `GET /api/packages`                 | Sí      | ADMIN, GUARD (todos), RESIDENT (propios) | 401                |
| Registrar paquete                | `POST /api/packages`                | Sí      | GUARD                                    | 400, 401, 403      |
| Marcar paquete entregado         | `PUT /api/packages/{id}/deliver`    | Sí      | GUARD                                    | 401, 403, 404      |
| Ver visitas                      | `GET /api/visits`                   | Sí      | ADMIN, GUARD (todas), RESIDENT (propias) | 401                |
| Registrar visita                 | `POST /api/visits`                  | Sí      | GUARD                                    | 400, 401, 403      |

Todas las rutas protegidas exigen el encabezado `Authorization: Bearer <token>`.

### Flujo actualizado de PQRS

- El residente crea la solicitud con asunto, descripción, categoría y, si aplica,
  fecha/hora del incidente y un adjunto. Se guarda inicialmente como `abierta`.
- La descripción inicial y las respuestas posteriores se conservan como mensajes
  dentro de una conversación. Las PQRS existentes se migran al iniciar el backend:
  la descripción original queda como primer mensaje del residente y la respuesta
  anterior del administrador como mensaje administrativo. La migración es idempotente.
- El administrador puede registrar una PQRS a nombre de un residente enviando su
  `residentId`; el backend rechaza esta acción para guardias y otros roles.
- El residente puede escribir después de una respuesta. Si la solicitud ya estaba
  resuelta, su nuevo mensaje la reabre automáticamente como `abierta` y avisa a los
  administradores.
- El administrador debe escribir una respuesta no vacía (no basta con adjuntar un
  archivo) antes de actualizar el estado o resolver una PQRS. Puede adjuntar imagen,
  video o audio además del texto.
- La respuesta por lotes acepta `pqrsIds`, `status`, `message` y adjunto opcional.
  Solo admite solicitudes de una misma categoría y estado `en_proceso` o `resuelta`.
  Todas se guardan en una sola transacción; si falta una PQRS o falla el guardado,
  no se modifica ninguna y la respuesta identifica los IDs fallidos. Se crea una
  notificación por residente afectado.
- Al estar resuelta, el residente puede calificar de 1 a 5 estrellas y agregar un
  comentario opcional. Las calificaciones se guardan como historial: al reabrirse
  la PQRS, las anteriores se conservan y, tras resolverse otra vez, se registra una
  nueva calificación. Si vuelve a calificar durante la misma resolución, se actualiza
  la calificación de ese ciclo.
- La pantalla agrupa las solicitudes por categoría, muestra pendientes por categoría
  y permite buscar/filtrar por estado y categoría. La selección por lotes se limita a
  una categoría a la vez.

Los adjuntos continúan viajando como Base64 en JSON; la app limita el archivo original
a 5 MB y el backend admite solicitudes de hasta 12 MB. No se implementó almacenamiento
de objetos ni carga multipart en esta fase.

## 5. Mapeo con la arquitectura de GA1-GA3

| Archivo/patrón enseñado en GA1-GA3             | Dónde está en este proyecto                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `data/Models.kt`                               | `android/.../data/Models.kt`                                                               |
| `data/ApiService.kt` (Retrofit, `Response<T>`) | `android/.../data/ApiService.kt`                                                           |
| `data/RetrofitClient.kt`                       | `android/.../data/RetrofitClient.kt`                                                       |
| `data/Session.kt` (objeto en memoria)          | `android/.../data/Session.kt` (con 3 roles en vez de 1 booleano `isAdmin`)                 |
| `MainActivity.kt` con `NavHost` inline         | `android/.../MainActivity.kt`                                                              |
| `if (Session.isAdmin)` para ocultar opciones   | Igual, extendido a `isAdmin` / `isResident` / `isGuard` en `HomeScreen.kt` y cada pantalla |
| Backend Flask consumido por la app             | `backend/app.py` (en vez del backend de e-commerce del curso)                              |

## 6. Alcance y "versión 2" (lo que queda fuera a propósito)

Para cumplir la regla de la GA4 ("una app pequeña y terminada vale más que una
ambiciosa sin terminar"), quedan **fuera de esta entrega**:

- Notificaciones push reales (Firebase). Las "notificaciones" son la pestaña
  de Registros/Notificaciones, que se actualiza al entrar o refrescar (polling
  por GET), no una alerta del sistema operativo.
- Subida de fotos (paquetes, visitantes).
- Recuperación de contraseña / edición de perfil.
- Búsqueda y filtros avanzados en las listas.
- Multi-unidad (multi-tenant): esta versión asume una sola unidad residencial.

## 7. Poner el repo en GitHub

El repositorio ya viene inicializado con Git y con los commits hechos. Solo
falta crear el repo vacío en GitHub y apuntarlo:

```bash
git remote add origin https://github.com/MAICOL-ESNEIDER/domux-ga4.git
git branch -M main
git push -u origin main
```

(Cambia la URL si le pones otro nombre al repositorio en GitHub.)
