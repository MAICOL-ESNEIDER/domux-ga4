# DOMUX — Residential Security OS (Proyecto Final GA4 - SENA ADSO)

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-REST_API-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Kotlin](https://img.shields.io/badge/Kotlin-1.9.24-7F52FF?style=for-the-badge&logo=kotlin&logoColor=white)
![Jetpack Compose](https://img.shields.io/badge/Jetpack_Compose-Material_3-4285F4?style=for-the-badge&logo=jetpackcompose&logoColor=white)
![SQLite & PostgreSQL](https://img.shields.io/badge/DB-SQLite_%7C_PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)

Sistema integral de operación, seguridad y administración para unidades residenciales (**Residential Security OS**), desarrollado como proyecto final (**GA4**) del programa **Análisis y Desarrollo de Software (ADSO) — SENA CTMA (Ficha 3223873)**.

El ecosistema está construido bajo una **Arquitectura Cliente-Servidor** que conecta una aplicación nativa Android en **Kotlin + Jetpack Compose** (estética *Dark SaaS / Bento Grid*) con un backend RESTful propio en **Python / Flask + SQLAlchemy**, evolucionando las bases de las guías GA1–GA3 hacia un entorno de nivel productivo con control de acceso basado en roles (**RBAC**), migraciones automáticas, notificaciones híbridas (FCM + Polling local), pases QR de acceso y ciclo de vida automatizado de paquetería.

## 1. Qué hace la aplicación (Roles y Capacidades)

Tres roles operativos bajo un único flujo de autenticación con sesión cifrada en **Android KeyStore (`AES/GCM/NoPadding`)**:

| Rol | Capacidades Principales en el Sistema |
| :--- | :--- |
| **Administrador (`ADMIN`)** | Superpermisos sobre todos los módulos · Crear, editar e inhabilitar usuarios · Filtros demográficos avanzados · Restablecer contraseñas con doble confirmación · Gestionar la ficha integral del hogar (habitantes, mascotas, vehículos, parqueadero y cuarto útil) · Publicar y eliminar anuncios con adjuntos multimedia · Responder PQRS individualmente o por lotes · Aprobar, rechazar o cancelar reservas · Control completo de portería (paquetes, papelera y visitas). |
| **Residente (`RESIDENT`)** | Consultar anuncios de la unidad · Crear PQRS, conversar en el hilo de seguimiento y calificar la satisfacción (1 a 5) · Consultar disponibilidad en tiempo real, reservar y cancelar zonas comunes · Ver sus paquetes (por llegar, en portería, entregados) · Autorizar o rechazar visitantes desde la app · Generar y revocar códigos QR temporales para visitas · Actualizar datos de contacto y consultar la ficha de su vivienda. |
| **Guardia (`GUARD`)** | Registrar paquetes (en portería o por llegar) con evidencia multimedia y llamada directa al residente · Marcar entregas registrando quién recibe · Gestionar la papelera de paquetes (restauración y borrado) · Registrar ingresos y salidas de visitantes, domiciliarios y contratistas · Autorizar visitas por verificación telefónica · Escanear e inspeccionar códigos QR de acceso con cámara. |

### Seguridad en Doble Capa (RBAC)

Cada operación está protegida en **dos niveles**:

1. **Capa de Presentación (Android):** El `DomuxScreenScaffold`, el menú lateral (`ModalNavigationDrawer`) y las pestañas (`DomuxSectionTabs`) adaptan dinámicamente las vistas según `Session.isAdmin`, `Session.isResident` y `Session.isGuard`.
2. **Capa de Servidor (Flask):** Todos los endpoints validan el token JWT (`@token_required`) y los permisos del rol (`@role_required`). Cualquier intento de invocación directa sin privilegios retorna `403 Forbidden`.

## 2. Arquitectura del Proyecto y Estructura del Repositorio

### Arquitectura Técnica

* **Backend (`Python / Flask` — Arquitectura en Capas):**
  * **Fábrica de Aplicación y Migraciones (`app.py`):** Inicialización modular, validación global contra campos vacíos (`@app.before_request`) y motor de migraciones automáticas en caliente compatible con **SQLite** y **PostgreSQL**.
  * **Capa de Enrutamiento (`routes/`):** Blueprints desacoplados por dominio (`auth.py`, `admin.py`, `community.py`, `security.py`).
  * **Capa de Servicios (`services/`):** Lógica de negocio aislada para disponibilidad/conflictos de reservas (`reservation_service.py`) y despacho transaccional de notificaciones (`notification_service.py`).
  * **Capa de Dominio y Persistencia (`models.py`, `validators.py`, `auth.py`, `errors.py`):** Modelos relacionales SQLAlchemy, serializadores JSON camelCase para Android, expresiones regulares de validación (contraseñas fuertes, placas colombianas, fechas ISO) y manejo centralizado de errores HTTP.
* **Frontend (`Android / Kotlin` — MVVM + UI Declarativa):**
  * **Interfaz de Usuario (`Jetpack Compose + Material 3`):** Sistema de diseño propio (*Dark SaaS / Bento Grid*) centralizado en `DomuxComponents.kt` (`DomuxScreenScaffold` con `TopAppBar` y botón de retorno, `ModalNavigationDrawer` o menú hamburguesa, `DomuxSectionTabs`, `DomuxFeedbackBanner` semántico en verde/rojo y buscador autocompletable `DomuxResidentSearchField`).
  * **Capa de Datos y Red (`data/`):** Cliente HTTP singleton con Retrofit (`RetrofitClient.kt`, `ApiService.kt`, `Models.kt`), persistencia cifrada de sesión (`Session.kt`) y registro de dispositivos push (`PushRegistration.kt`).

### Árbol de Directorios

```text
├── Documentacion_Proyecto_ADSO/     → Gobierno y artefactos documentales SENA ADSO
│   ├── 00_Gobierno_Documental/      → Arquitectura documental e Índice Maestro
│   ├── 01_Inicio_y_Planeacion/      → Formulación, constitución y gestión del proyecto
│   ├── 02_Requisitos/               → Alcance, Backlog de HU, Casos de Uso y Trazabilidad
│   ├── 03_Diseno/                   → Diseño UX/UI, Arquitectura de Datos y Diseño Técnico
│   ├── 04_Calidad/                  → Plan de Calidad, Pruebas y Aceptación
│   ├── 05_Manuales/                 → Manual Técnico/Operación y Manual de Usuario
│   ├── 06_Cierre/                   → Informe de Cierre y Entrega
│   ├── 07_Evaluacion/               → Rúbrica Integral, Lista de Chequeo y Sustentación
│   └── 08_Repositorio/              → Guía de Estructura y Evidencias
├── android/                         → Proyecto nativo de Android Studio (Kotlin / Compose)
│   └── app/src/main/java/com/dracknoval/domux/
│       ├── data/                    → ApiService.kt, Models.kt, RetrofitClient.kt, Session.kt
│       ├── ui/theme/                → Paleta Dark SaaS, tipografía y tema Material 3
│       ├── DomuxComponents.kt       → Scaffold global, Drawer, Tabs, Banners y Buscador
│       └── *Screen.kt               → Pantallas modulares por dominio de negocio
├── backend/                         → API REST en Python / Flask
│   ├── routes/                      → Blueprints: auth.py, admin.py, community.py, security.py
│   ├── services/                    → notification_service.py y reservation_service.py
│   ├── tests/                       → Suite automatizada de pruebas de integración (unittest)
│   ├── app.py                       → Punto de entrada, configuración y migraciones SQL
│   ├── models.py                    → Modelos SQLAlchemy y serializadores JSON
│   ├── validators.py                → Reglas de validación de negocio y formatos
│   ├── auth.py                      → Generación/verificación JWT y decoradores RBAC
│   ├── errors.py                    → Manejadores globales de excepciones HTTP
│   ├── logging_config.py            → Auditoría de peticiones en consola del servidor
│   └── seed.py                      → Datos iniciales de prueba (usuarios, zonas, paquetes)
└── render.yaml                      → Blueprint IaC para despliegue en la nube (Render)
```

## 3. Levantar el Backend en Local

```powershell
cd backend
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

El servidor quedará escuchando en `http://localhost:5000/` (accesible desde el emulador Android mediante `http://10.0.2.2:5000/`). En su primer arranque crea automáticamente la base de datos `domux.db`, ejecuta las migraciones de esquema y siembra los siguientes usuarios de prueba:

| Rol | Correo | Contraseña | Unidad Asignada |
| :--- | :--- | :--- | :--- |
| Administrador | `admin@domux.com` | `Admin123*` | Administración |
| Guardia | `guardia@domux.com` | `Guardia123*` | Portería Principal |
| Residente | `maria@domux.com` | `Residente123*` | Torre 1 Apto 101 |
| Residente | `carlos@domux.com` | `Residente123*` | Torre 2 Apto 202 |

### Ejecutar la Suite de Pruebas del Backend

```powershell
cd backend
python -m unittest discover -s tests
```

## 4. Abrir y Compilar la App Android

1. Abre Android Studio → **Open** → selecciona la carpeta `android/`.
2. Espera la sincronización de Gradle.
3. Selecciona la variante en **Build Variants**:
   * `devDebug`: Conecta al backend local en `http://10.0.2.2:5000/`.
   * `prodDebug`: Conecta al backend en la nube desplegado en Render.
4. Para compilar o instalar por terminal:

```powershell
cd android
.\gradlew.bat :app:assembleDevDebug
```

## 5. Despliegue en la Nube (Render)

Conecta el repositorio en Render (**New +** → **Blueprint**). Render detecta automáticamente `render.yaml` y aprovisiona el servicio web `domux-backend` junto con la base de datos PostgreSQL `domux-db`. `app.py` normaliza automáticamente las cadenas `postgres://` a `postgresql://` para compatibilidad con SQLAlchemy y ejecuta las migraciones de columnas al iniciar.

## 6. Contrato de la API REST (Endpoints Principales)

Todas las rutas protegidas requieren el encabezado `Authorization: Bearer <token>`.

| Módulo | Método y Ruta | Roles Permitidos | Descripción |
| :--- | :--- | :--- | :--- |
| Auth | `POST /api/auth/login` | Público | Autenticación y emisión de token JWT. |
| Auth | `GET /api/auth/session` | Autenticado | Valida la sesión activa y retorna el perfil. |
| Usuarios | `GET /api/users` | ADMIN | Directorio paginado con filtros demográficos. |
| Usuarios | `POST /api/users` | ADMIN | Creación de usuarios con validación de datos. |
| Usuarios | `PUT /api/users/<id>` | ADMIN | Edición de usuario, rol, unidad y estado activo. |
| Usuarios | `PUT /api/users/<id>/password` | ADMIN | Restablecimiento seguro de contraseña. |
| Residentes | `GET /api/residents` | ADMIN, GUARD | Búsqueda rápida por nombre completo o apto. |
| Unidades | `GET / PUT /api/admin/units` | ADMIN | Consulta y guardado de la ficha del hogar. |
| Perfil | `GET / PUT /api/profile` | RESIDENT | Consulta y actualización de datos de contacto. |
| Anuncios | `GET / POST / DELETE /api/announcements` | Todos (GET), ADMIN (POST/DELETE) | Tablón de comunicados con soporte multimedia. |
| PQRS | `GET / POST /api/pqrs` | ADMIN, RESIDENT | Listado filtrado y radicación de solicitudes. |
| PQRS | `PUT /api/pqrs/<id>/respond` | ADMIN | Respuesta administrativa y cambio de estado. |
| PQRS | `POST /api/pqrs/batch/respond` | ADMIN | Respuesta masiva por lotes de igual categoría. |
| PQRS | `POST /api/pqrs/<id>/messages` | RESIDENT | Seguimiento conversacional y reapertura. |
| PQRS | `PUT /api/pqrs/<id>/satisfaction` | RESIDENT | Calificación de satisfacción (1 a 5 estrellas). |
| Reservas | `GET / POST /api/reservations` | ADMIN, RESIDENT | Historial y creación de reservas de zonas. |
| Reservas | `GET /api/reservations/availability` | Autenticado | Consulta de franjas horarias libres/ocupadas. |
| Reservas | `GET /api/reservations/calendar` | Autenticado | Fechas bloqueadas por ocupación total del mes. |
| Reservas | `PUT /api/reservations/<id>/status` | ADMIN | Aprobación o rechazo de reservas pendientes. |
| Reservas | `PUT /api/reservations/<id>/cancel` | ADMIN, RESIDENT | Cancelación de reservas activas o aprobadas. |
| Paquetes | `GET / POST /api/packages` | ADMIN, GUARD, RESIDENT (GET) | Consulta con filtros y registro (pendiente/por_llegar). |
| Paquetes | `PUT /api/packages/<id>/status` | ADMIN, GUARD | Recepción en portería de paquetes por llegar. |
| Paquetes | `PUT /api/packages/<id>/deliver` | ADMIN, GUARD | Registro de entrega con nombre de receptor. |
| Paquetes | `DELETE /api/packages/<id>` | ADMIN, GUARD | Envío a papelera o eliminación definitiva (`?force=true`). |
| Paquetes | `PUT /api/packages/<id>/restore` | ADMIN, GUARD | Restauración de paquetes desde la papelera. |
| Visitas | `GET / POST /api/visits` | ADMIN, GUARD, RESIDENT (GET) | Historial y registro en portería con foto/documento. |
| Visitas | `PUT /api/visits/<id>/decision` | RESIDENT | Autorización o rechazo de ingreso desde la app. |
| Visitas | `PUT /api/visits/<id>/authorize-call` | GUARD | Autorización de ingreso respaldada por llamada. |
| Visitas | `POST /api/visits/<id>/entry` y `/exit` | GUARD | Control de entrada, salida temporal o definitiva. |
| Pases QR | `GET / POST / PUT /api/visits/qr-passes` | RESIDENT | Creación, consulta y revocación de pases QR. |
| Pases QR | `GET / POST /api/visits/qr/<token>/*` | GUARD | Inspección de QR, vinculación, entrada y salida. |
| Alertas | `GET / PUT /api/notifications` | Autenticado | Bandeja de notificaciones y marcado de lectura. |

## 7. Mapeo con la Arquitectura GA1–GA3 y Evolución en GA4

| Componente Base (GA1–GA3) | Implementación y Evolución en DOMUX (GA4) |
| :--- | :--- |
| `data/Models.kt` | `android/.../data/Models.kt` con modelos completos de dominio, papelera, QR y unidades. |
| `data/ApiService.kt` | `android/.../data/ApiService.kt` con soporte completo para los flujos RESTful del proyecto. |
| `data/RetrofitClient.kt` | `android/.../data/RetrofitClient.kt` configurado dinámicamente por variante (`BuildConfig.BASE_URL`). |
| `data/Session.kt` | `android/.../data/Session.kt` con 3 roles (ADMIN, RESIDENT, GUARD) y cifrado AES/GCM en Android KeyStore. |
| `MainActivity.kt` (NavHost) | `android/.../MainActivity.kt` integrado con `DomuxScreenScaffold`, `ModalNavigationDrawer` y deep-linking de notificaciones. |
| Backend Flask académico | `backend/app.py` estructurado en capas (`routes/`, `services/`, `models.py`, `validators.py`) y cubierto por 45 tests automatizados. |

## 8. Gobierno Documental SENA ADSO

Toda la documentación formal del proyecto exigida por la metodología del programa ADSO se encuentra organizada en la carpeta raíz `Documentacion_Proyecto_ADSO/`, distribuida en 9 fases: `00_Gobierno_Documental` · `01_Inicio_y_Planeacion` · `02_Requisitos` · `03_Diseno` · `04_Calidad` · `05_Manuales` · `06_Cierre` · `07_Evaluacion` · `08_Repositorio`.

---

### Paso Final: Subir la Estructura Documental y el Nuevo README (GitFlow)

Una vez que tu agente de VS Code actualice el archivo `README.md`, puedes pedirle al mismo agente (o ejecutar tú mismo en la terminal) este bloque para registrar ambos cambios de forma limpia sin tocar `android/gradle.properties`:

```powershell
# 1. Revisar qué archivos van a entrar (solo Documentacion_Proyecto_ADSO/ y README.md)
git add Documentacion_Proyecto_ADSO/ README.md
git status --short

# 2. Crear el commit convencional de documentación
git commit -m "docs(adso): add SENA ADSO documentation tree and update executive README"

# 3. Subir a tu rama actual en GitHub
git push origin HEAD
```
