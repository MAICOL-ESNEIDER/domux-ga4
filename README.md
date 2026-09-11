# Domux — App de gestión de unidad residencial (Proyecto GA4)

Proyecto final (GA4) del programa Análisis y Desarrollo de Software — adaptación
reducida del proyecto de grado **Domux** como app Android que consume un backend
REST propio (Flask + base de datos real), siguiendo la misma arquitectura
enseñada en las guías GA1-GA3 (Retrofit + `Models.kt`/`ApiService.kt`/
`RetrofitClient.kt`/`Session.kt` + Navigation Compose).

## Qué hace la app

Tres roles, un solo login:

| Rol | Puede hacer |
|---|---|
| **Administrador** | Crear cuentas de residente y de guardia · publicar anuncios · ver todas las PQRS y responderlas · ver todas las reservas · ver todos los registros de portería (paquetes y visitas) |
| **Residente** | Ver anuncios · crear y ver sus PQRS · reservar/cancelar zonas comunes · ver sus notificaciones (paquetes pendientes/entregados e historial de visitas) |
| **Guardia de seguridad** | Registrar paquetes a nombre de un residente · registrar ingreso de visitantes/domiciliarios a nombre de un residente · marcar paquetes como entregados |

Cada acción reservada está protegida en **dos capas**: la app oculta las
opciones según el rol (`Session.isAdmin` / `isResident` / `isGuard`), y el
backend vuelve a comprobar el rol en cada endpoint — si alguien llama a la API
directamente sin el permiso adecuado, recibe **403**.

## Estructura del repositorio

```
├── android/     → Proyecto de Android Studio (ábrelo apuntando a esta carpeta)
├── backend/     → API REST en Flask (desplegable en Render)
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

Debe quedar escuchando en `http://localhost:5000/`. La primera vez que arranca
crea la base de datos (`domux.db`, SQLite) y siembra estos **usuarios de
prueba**:

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | `admin@domux.com` | `admin123` |
| Guardia | `guardia@domux.com` | `guardia123` |
| Residente | `maria@domux.com` | `residente123` |
| Residente | `carlos@domux.com` | `residente123` |

## 2. Abrir y correr la app Android

1. Abre Android Studio → **Open** → selecciona la carpeta `android/` (no la
   raíz del repo).
2. Espera a que sincronice Gradle.
3. En `android/app/src/main/java/com/dracknoval/domux/data/RetrofitClient.kt`
   confirma cuál `BASE_URL` está activa (por defecto, `10.0.2.2:5000`, para
   emulador + backend local). Si no te conecta, sigue la Opción 2 que está
   comentada en ese mismo archivo (`adb reverse`).
4. Corre el backend (paso 1) y luego ejecuta la app (▶ Run) en el emulador.
5. Inicia sesión con cualquiera de los usuarios de prueba de la tabla anterior.

## 3. Desplegar el backend en Render

1. Sube este repo a GitHub (ver sección de Git más abajo).
2. En Render: **New +** → **Blueprint** → conecta el repo → Render detecta
   `render.yaml` solo y crea el servicio web `domux-backend` **y** la base de
   datos Postgres `domux-db`, ya conectados.
3. Cuando termine el deploy, Render te da una URL tipo
   `https://domux-backend.onrender.com`. Pégala en `RetrofitClient.kt`
   (Opción 3, ya comentada en el archivo) para consumir el backend real desde
   un celular físico o para la entrega final.
4. `render.yaml` ya arregla el detalle de que Render entrega la URL de
   Postgres como `postgres://` y la app la convierte a `postgresql://`
   automáticamente (si no, SQLAlchemy falla al conectar).

## 4. Contrato de la API (tabla de endpoints)

| Funcionalidad | Método y ruta | ¿Token? | ¿Rol? | Códigos de error |
|---|---|---|---|---|
| Login | `POST /api/auth/login` | No | — | 401 |
| Listar usuarios | `GET /api/users` | Sí | ADMIN | 401, 403 |
| Crear usuario | `POST /api/users` | Sí | ADMIN | 400, 401, 403, 409 |
| Listar residentes (para asignar) | `GET /api/residents` | Sí | ADMIN, GUARD | 401, 403 |
| Ver anuncios | `GET /api/announcements` | Sí | cualquiera | 401 |
| Publicar anuncio | `POST /api/announcements` | Sí | ADMIN | 400, 401, 403 |
| Ver PQRS | `GET /api/pqrs` | Sí | ADMIN (todas), RESIDENT (propias) | 401, 403 |
| Crear PQRS | `POST /api/pqrs` | Sí | RESIDENT | 400, 401, 403 |
| Responder PQRS | `PUT /api/pqrs/{id}/respond` | Sí | ADMIN | 400, 401, 403, 404 |
| Ver zonas comunes | `GET /api/common-areas` | Sí | cualquiera | 401 |
| Ver reservas | `GET /api/reservations` | Sí | ADMIN (todas), RESIDENT (propias) | 401, 403 |
| Crear reserva | `POST /api/reservations` | Sí | RESIDENT | 400, 401, 403 |
| Cancelar reserva | `PUT /api/reservations/{id}/cancel` | Sí | RESIDENT (propia), ADMIN | 401, 403, 404 |
| Ver paquetes | `GET /api/packages` | Sí | ADMIN, GUARD (todos), RESIDENT (propios) | 401 |
| Registrar paquete | `POST /api/packages` | Sí | GUARD | 400, 401, 403 |
| Marcar paquete entregado | `PUT /api/packages/{id}/deliver` | Sí | GUARD | 401, 403, 404 |
| Ver visitas | `GET /api/visits` | Sí | ADMIN, GUARD (todas), RESIDENT (propias) | 401 |
| Registrar visita | `POST /api/visits` | Sí | GUARD | 400, 401, 403 |

Todas las rutas protegidas exigen el encabezado `Authorization: Bearer <token>`.

## 5. Mapeo con la arquitectura de GA1-GA3

| Archivo/patrón enseñado en GA1-GA3 | Dónde está en este proyecto |
|---|---|
| `data/Models.kt` | `android/.../data/Models.kt` |
| `data/ApiService.kt` (Retrofit, `Response<T>`) | `android/.../data/ApiService.kt` |
| `data/RetrofitClient.kt` | `android/.../data/RetrofitClient.kt` |
| `data/Session.kt` (objeto en memoria) | `android/.../data/Session.kt` (con 3 roles en vez de 1 booleano `isAdmin`) |
| `MainActivity.kt` con `NavHost` inline | `android/.../MainActivity.kt` |
| `if (Session.isAdmin)` para ocultar opciones | Igual, extendido a `isAdmin` / `isResident` / `isGuard` en `HomeScreen.kt` y cada pantalla |
| Backend Flask consumido por la app | `backend/app.py` (en vez del backend de e-commerce del curso) |

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
