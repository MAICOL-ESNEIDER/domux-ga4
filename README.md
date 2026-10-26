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
| **Residente**            | Ver anuncios · crear y ver sus PQRS · reservar/cancelar zonas comunes · consultar paquetes y visitas · autorizar ingresos · crear/revocar QR de visitas · ver notificaciones |
| **Guardia de seguridad** | Buscar residentes · registrar paquetes, visitantes y domiciliarios · registrar autorizaciones por llamada, entradas y salidas · escanear QR · marcar paquetes como entregados |

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
| Consultar/editar ficha de unidad | `GET, PUT /api/admin/units`         | Sí      | ADMIN                                    | 400, 401, 403, 404, 409 |
| Ver/editar perfil propio         | `GET, PUT /api/profile`             | Sí      | RESIDENT                                 | 400, 401, 403, 409 |
| Validar sesión actual            | `GET /api/auth/session`             | Sí      | cualquier usuario autenticado            | 401                |
| Registrar/desregistrar dispositivo push | `POST, DELETE /api/push-tokens` | Sí   | cualquier usuario autenticado            | 400, 401           |
| Ver hogar propio                 | `GET /api/profile/unit`             | Sí      | RESIDENT                                 | 401, 403, 404      |
| Listar residentes (para asignar) | `GET /api/residents`                | Sí      | ADMIN, GUARD                             | 401, 403           |
| Ver anuncios                     | `GET /api/announcements`            | Sí      | cualquiera                               | 401                |
| Publicar anuncio                 | `POST /api/announcements`           | Sí      | ADMIN                                    | 400, 401, 403      |
| Ver PQRS                         | `GET /api/pqrs`                     | Sí      | ADMIN (todas o por `residentId`), RESIDENT (propias) | 401, 403 |
| Crear PQRS                       | `POST /api/pqrs`                   | Sí      | RESIDENT; ADMIN con `residentId`         | 400, 401, 403      |
| Agregar mensaje a PQRS           | `POST /api/pqrs/{id}/messages`     | Sí      | RESIDENT (propia)                        | 400, 401, 403, 404 |
| Responder/actualizar PQRS        | `PUT /api/pqrs/{id}/respond`       | Sí      | ADMIN                                    | 400, 401, 403, 404 |
| Responder varias PQRS            | `POST /api/pqrs/batch/respond`     | Sí      | ADMIN                                    | 400, 401, 403, 404, 500 |
| Calificar una PQRS resuelta      | `PUT /api/pqrs/{id}/satisfaction`  | Sí      | RESIDENT (propia)                        | 400, 401, 403, 404 |
| Ver zonas comunes                | `GET /api/common-areas`             | Sí      | cualquiera                               | 401                |
| Ver reservas                     | `GET /api/reservations`             | Sí      | ADMIN (todas), RESIDENT (propias)        | 401, 403           |
| Crear reserva                    | `POST /api/reservations`            | Sí      | RESIDENT; ADMIN con `residentId`         | 400, 401, 403, 409 |
| Consultar fechas bloqueadas      | `GET /api/reservations/calendar`    | Sí      | autenticado                             | 400, 401, 404      |
| Conversar sobre reserva          | `POST /api/reservations/{id}/messages` | Sí   | RESIDENT (propia), ADMIN                | 400, 401, 403, 404 |
| Aprobar o rechazar reserva       | `PUT /api/reservations/{id}/status` | Sí      | ADMIN                                   | 400, 401, 403, 404, 409 |
| Cancelar reserva                 | `PUT /api/reservations/{id}/cancel` | Sí      | RESIDENT (propia), ADMIN                 | 400, 401, 403, 404 |
| Ver paquetes                     | `GET /api/packages`                 | Sí      | ADMIN, GUARD (todos), RESIDENT (propios) | 401                |
| Registrar paquete                | `POST /api/packages`                | Sí      | GUARD                                    | 400, 401, 403      |
| Marcar paquete entregado         | `PUT /api/packages/{id}/deliver`    | Sí      | GUARD (requiere `receivedBy`)            | 400, 401, 403, 404 |
| Ver visitas/historial            | `GET /api/visits`                   | Sí      | ADMIN, GUARD (todas), RESIDENT (propias) | 400, 401           |
| Buscar residentes para portería  | `GET /api/residents?search=`        | Sí      | ADMIN, GUARD (máximo 50 resultados)      | 401, 403           |
| Registrar visita/domiciliario    | `POST /api/visits`                  | Sí      | GUARD                                    | 400, 401, 403      |
| Autorizar/rechazar visita        | `PUT /api/visits/{id}/decision`     | Sí      | RESIDENT (propia)                        | 400, 401, 403, 404 |
| Autorizar ingreso por llamada    | `PUT /api/visits/{id}/authorize-call` | Sí   | GUARD                                    | 400, 401, 403, 404 |
| Registrar entrada                | `POST /api/visits/{id}/entry`       | Sí      | GUARD                                    | 400, 401, 403, 404 |
| Registrar salida                 | `POST /api/visits/{id}/exit`        | Sí      | GUARD                                    | 400, 401, 403, 404 |
| Crear/listar/revocar QR          | `POST, GET /api/visits/qr-passes`, `PUT .../{id}/revoke` | Sí | RESIDENT (propios) | 400, 401, 403, 404 |
| Consultar QR                     | `GET /api/visits/qr/{token}`        | Sí      | GUARD                                    | 400, 401, 403, 404 |
| Registrar acceso por QR          | `POST /api/visits/qr/{token}/entry`, `POST .../exit` | Sí | GUARD | 400, 401, 403, 404, 409 |

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

### Fase 2 — Gestión de usuarios y perfiles

- `GET /api/users` devuelve una página (25 registros por defecto; `pageSize`
  admite de 1 a 100), con total y cantidad de páginas. Permite combinar `search`,
  `role`, `occupancyType`, `apartmentFrom`, `apartmentTo`, `hasPets`,
  `hasVehicles`, `hasParking`, `hasStorage`, `minAge`, `maxAge` e `isActive`.
- Los tipos de tenencia aceptados son `propietario`, `arrendatario` y
  `residente`. El administrador registra el consentimiento expreso al crear
  residentes mediante `dataProcessingConsent: true`; la fecha queda guardada.
  No se presume consentimiento si el campo falta.
- La ficha de unidad (`ResidentialUnit`) agrupa integrantes del hogar con
  parentesco, documento y fecha de nacimiento, mascotas, vehículos, parqueadero,
  cuarto útil, seguro de mascotas y plan funerario. El administrador la consulta
  o reemplaza desde `/api/admin/units`; las listas se guardan de forma atómica.
  Las placas se normalizan a mayúsculas y se valida formato colombiano y
  unicidad entre apartamentos.
- El residente consulta los datos de su perfil y vivienda con `/api/profile` y
  `/api/profile/unit`. Solo puede editar teléfono, correo y redes sociales;
  el backend rechaza cualquier otro campo. Los cambios de apartamento,
  parentesco, documento, mascotas o vehículos se solicitan mediante PQRS o en
  administración.
- Se agregaron las tablas `residential_units`, `household_members`, `pets` y
  `vehicles`, además de campos de apartamento, redes sociales y consentimiento
  en `users`. Al iniciar, la migración idempotente crea fichas de unidad para
  residentes existentes y deriva el número del apartamento cuando es posible,
  conservando los datos previos.

### Fase 3 — Acciones administrativas en nombre del residente

- Desde la ficha de un apartamento, administración puede iniciar la creación de
  una PQRS o reserva preseleccionando al residente. PQRS abre además el historial
  de esa persona para continuar la conversación y responder sus solicitudes.
- No hay una operación administrativa para editar o borrar la solicitud original;
  administración puede responderla desde su conversación.
- Las solicitudes conservan al residente como dueño e incluyen una referencia
  opcional al administrador que las creó. Los registros anteriores mantienen
  `created_by_admin_id` vacío; no se atribuyen acciones pasadas sin evidencia.
- Las referencias de auditoría son columnas anulables agregadas de forma
  compatible con SQLite y PostgreSQL, y aparecen en el historial como
  **Creada por administración**.
- Crear una reserva a nombre de un residente genera una notificación. El guardia
  no puede usar estos flujos, y un residente no puede asignar solicitudes a otra
  persona enviando otro `residentId`.

### Fase 4 — Reservas de zonas comunes

- El calendario consulta `/api/reservations/calendar` por zona y mes. Los días
  pasados y los días donde ya están ocupadas todas las franjas de la zona no se
  pueden seleccionar. Si todavía hay horarios libres ese día, el residente puede
  escoger entre esas franjas.
- Una solicitud nueva queda en estado `pendiente`; no ocupa una franja hasta que
  administración la aprueba. La aprobación valida otra vez el cruce y devuelve
  `409` si otra reserva tomó el horario mientras la solicitud esperaba. Una
  reserva `aprobada` o `activa` sí ocupa la franja.
- Al solicitarla se puede enviar texto y/o un adjunto de imagen, video o audio.
  Los mensajes posteriores forman una conversación con autor, rol, texto,
  adjuntos y fecha. El residente puede escribir en sus reservas no finalizadas;
  administración puede responder. Cada nuevo mensaje notifica a la otra parte.
- Administración recibe aviso de solicitud nueva y de cancelación hecha por el
  residente. El residente recibe avisos cuando administración registra la reserva,
  la aprueba, la rechaza, la cancela o responde en la conversación.
- El residente puede cancelar sus reservas `pendiente`, `aprobada` o las
  `activa` heredadas, pero únicamente antes del día reservado. No se permite
  cancelar el mismo día ni después, ni cancelar solicitudes rechazadas o ya
  canceladas. Administración puede cancelar reservas pendientes o aprobadas.
- La API de disponibilidad y la aprobación aplican las mismas reglas de
  ocupación; los mensajes y adjuntos se conservan en la tabla nueva
  `reservation_messages`, sin modificar o eliminar los datos anteriores.

### Fase 5 — Portería, paquetes, visitas y domiciliarios

- La búsqueda de residentes permite consultar por nombre, documento o apartamento
  desde la portería; el backend devuelve como máximo 50 residentes activos.
- Al registrar una visita, el residente recibe una notificación para aprobar o
  rechazar el ingreso. El guardia también puede dejar registrada una autorización
  telefónica. Después de autorizar, registra cada entrada y salida por separado;
  los eventos guardan fecha, método y quién los registró.
- Foto o documento del visitante solo se acepta cuando el guardia confirma que
  existe consentimiento. La evidencia continúa usando el formato multimedia
  existente en Base64; no se guarda si no hay autorización.
- Los domiciliarios usan el mismo ciclo de autorización y entrada/salida, con un
  campo opcional para describir el pedido. El residente recibe aviso de llegada,
  entrada y salida.
- Para una estadía de varios días el residente puede crear un QR de 1 a 30 días,
  con un límite positivo de personas, o revocarlo. El QR contiene un token
  aleatorio sin datos personales; el backend valida vigencia, revocación y cupo.
  Una persona que ya usó cupo puede salir y volver a entrar sin consumir otro.
  También se puede vincular al QR un registro manual existente del mismo residente.
- Una visita autorizada que no sea por QR notifica al residente cada vez que
  entra o sale. Las entradas/salidas por QR no generan esos avisos repetidos.
- Al entregar un paquete, portería registra quién lo recibió y el residente recibe
  ese nombre en la notificación. Los registros históricos se conservan; las nuevas
  columnas se agregan sin borrar datos en SQLite y PostgreSQL.
- Android genera el QR y lo escanea con ZXing; el permiso de cámara se pide al
  momento de escanear por el componente de lectura.

### Fase 6 — Notificaciones push, sesión e infraestructura

- Android registra el token FCM del dispositivo al iniciar sesión y lo actualiza
  cuando Firebase rota el token. Al cerrar sesión, elimina la asociación del
  backend e invalida el token local de Firebase. Cada token queda asociado al
  usuario que inició sesión y a un identificador de instalación.
- El backend guarda los tokens en `device_push_tokens` y conserva la notificación
  normal en la base de datos. Tras confirmar la transacción, envía push por FCM;
  un fallo de FCM se registra en el log y no convierte en fallida la acción ya
  persistida. Las visitas pendientes usan prioridad alta; la consulta de
  notificaciones cada 30 segundos permanece como respaldo. Las notificaciones
  no se duplican entre FCM y la consulta local.
- Al tocar un push, DOMUX abre la sección correspondiente (PQRS, reservas,
  portería, anuncios o notificaciones). Android 13+ solicita `POST_NOTIFICATIONS`
  y usa canales separados para avisos normales y urgentes.
- La sesión se guarda cifrada con AES-GCM y una clave del Android Keystore.
  Al iniciar la app se valida con `GET /api/auth/session`; un token vencido vuelve
  al login. Si el servidor no responde, la sesión se conserva y se puede reintentar.
- Los cambios de autorización, entrada, salida y método de acceso de visitas se
  guardan como eventos con actor y fecha; también se conserva quién registró la
  entrega de cada paquete y la fecha de revocación del QR. Los tokens push están
  protegidos por autenticación y solo se pueden borrar para la cuenta actual.
- Las nuevas tablas se crean sin borrar registros y las columnas adicionales se
  migran de forma compatible con SQLite y PostgreSQL.

#### Configuración obligatoria de Firebase para activar push

1. En Firebase Console, crea o selecciona un proyecto y agrega una aplicación
   Android con el identificador exacto `com.dracknoval.domux`.
2. Descarga el archivo `google-services.json` y colócalo en
   `android/app/google-services.json`. El archivo está ignorado por Git y no se
   debe subir al repositorio. Gradle solo activa el plugin de Google Services
   cuando ese archivo existe.
3. En la configuración del proyecto Firebase, habilita Firebase Cloud Messaging.
   En Render, agrega la variable secreta `FIREBASE_SERVICE_ACCOUNT_JSON` con el
   contenido JSON completo de una clave de cuenta de servicio del Firebase Admin
   SDK. Se obtiene desde **Project settings → Service accounts → Generate new
   private key**. No pongas esa clave en el repositorio ni en Android.
4. Despliega nuevamente el backend y recompila/reinstala la app. El backend
   registra el token de cada dispositivo al iniciar sesión; no es necesario
   copiar tokens manualmente. Como alternativa al JSON en una variable de entorno,
   el backend admite `GOOGLE_APPLICATION_CREDENTIALS` apuntando a un archivo de
   credenciales disponible solo en el servidor.

## 6. Mapeo con la arquitectura de GA1-GA3

| Archivo/patrón enseñado en GA1-GA3             | Dónde está en este proyecto                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `data/Models.kt`                               | `android/.../data/Models.kt`                                                               |
| `data/ApiService.kt` (Retrofit, `Response<T>`) | `android/.../data/ApiService.kt`                                                           |
| `data/RetrofitClient.kt`                       | `android/.../data/RetrofitClient.kt`                                                       |
| `data/Session.kt` (sesión persistente)         | `android/.../data/Session.kt` (AES-GCM con Android Keystore y 3 roles)                      |
| `MainActivity.kt` con `NavHost` inline         | `android/.../MainActivity.kt`                                                              |
| `if (Session.isAdmin)` para ocultar opciones   | Igual, extendido a `isAdmin` / `isResident` / `isGuard` en `HomeScreen.kt` y cada pantalla |
| Backend Flask consumido por la app             | `backend/app.py` (en vez del backend de e-commerce del curso)                              |

## 7. Alcance y mejoras pendientes

Para cumplir la regla de la GA4 ("una app pequeña y terminada vale más que una
ambiciosa sin terminar"), quedan **fuera de esta entrega**:

- Push requiere completar la configuración de Firebase descrita arriba; sin las
  credenciales y `google-services.json`, las notificaciones en la base de datos y
  el respaldo de consulta siguen funcionando, pero FCM no envía alertas push.
- Almacenamiento separado de adjuntos queda pendiente: PQRS, reservas, paquetes y
  visitantes mantienen Base64 en JSON (máximo 5 MB por archivo en Android y 12 MB
  por petición en el backend); no se incorporó un servicio de archivos u objetos
  para evitar un cambio de infraestructura grande.
- La app de administración ya usa búsqueda, filtros combinables y paginación
  del servidor para usuarios; no hay todavía exportación de resultados.
- El perfil del residente es editable solo para los campos permitidos; no hay
  un flujo automatizado para que el residente registre cambios del hogar: debe
  solicitarlos mediante PQRS o a administración.
- Multi-unidad (multi-tenant): esta versión asume una sola unidad residencial.

## 8. Publicar cambios y abrir un Pull Request

Publica la rama de trabajo y abre un Pull Request hacia `develop`. No renombres
la rama de funcionalidad a `main` ni hagas merge directamente:

```bash
git push -u origin feature/pqrs-chat-usuarios-reservas-porteria
```

En GitHub, crea el Pull Request seleccionando `develop` como rama base y
`feature/pqrs-chat-usuarios-reservas-porteria` como rama de comparación. Si el
remoto `origin` todavía no está configurado, agrégalo antes con la URL del repo.
