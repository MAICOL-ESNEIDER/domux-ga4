# DOMUX — Residential Security OS (Proyecto Final GA4 - SENA ADSO)

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-REST_API-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Kotlin](https://img.shields.io/badge/Kotlin-1.9.24-7F52FF?style=for-the-badge&logo=kotlin&logoColor=white)
![Jetpack Compose](https://img.shields.io/badge/Jetpack_Compose-Material_3-4285F4?style=for-the-badge&logo=jetpackcompose&logoColor=white)
![SQLite & PostgreSQL](https://img.shields.io/badge/DB-SQLite_%7C_PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)

**DOMUX** es un sistema para que la administración, la portería y los residentes de una unidad residencial lleven en un solo lugar las visitas, los vehículos, los paquetes, los comunicados, las PQRS (peticiones, quejas, reclamos y sugerencias) y las reservas de zonas comunes.

Es el proyecto final (**GA4**) del programa **Tecnología en Análisis y Desarrollo de Software (ADSO)** del SENA, Centro de Tecnología de la Manufactura Avanzada (CTMA), Medellín, ficha 3223873.

Tiene tres piezas que trabajan juntas:

| Pieza | Qué es | Carpeta |
| :--- | :--- | :--- |
| **App Android** | La usan la administración, la portería y los residentes. Está hecha en Kotlin con Jetpack Compose. | `android/` |
| **Servidor (API)** | Guarda los datos y aplica las reglas. Está hecho en Python con Flask. Una **API REST** es la «puerta» por la que la app y la web piden y envían datos. | `backend/` |
| **Web de administración** | Páginas para la administración, servidas por el mismo servidor (Flask y plantillas HTML con Jinja2). | `backend/web/` |

**Contenido:**
[1. Estado](#1-estado-del-proyecto) ·
[2. Problema y solución](#2-problema-y-solución) ·
[3. Características](#3-características) ·
[4. Tecnologías](#4-tecnologías) ·
[5. Requisitos previos](#5-requisitos-previos) ·
[6. Instalación](#6-instalación) ·
[7. Configuración](#7-configuración) ·
[8. Migraciones y semillas](#8-migraciones-y-semillas) ·
[9. Ejecución](#9-ejecución) ·
[10. Pruebas](#10-pruebas) ·
[11. Despliegue](#11-despliegue) ·
[12. Estructura](#12-estructura-del-repositorio) ·
[13. Autores](#13-autores-y-contribuciones) ·
[14. Licencia](#14-licencia) ·
[Más información](#más-información)

## 1. Estado del proyecto

| Dato | Valor |
| :--- | :--- |
| Versión | `1.0.0-rc.1`: la versión **candidata** (*release candidate*, la que se prueba antes de entregar) de la **versión reducida 1.0**. Todavía no tiene etiqueta de Git. |
| Entrega | 1 de diciembre de 2026, **en local**: el servidor y la base de datos corren en el computador de la demostración. |
| Rama de trabajo | `release/v1.0-reducida` |
| Calidad automática | Un pipeline en GitHub Actions prueba el servidor en SQLite y en PostgreSQL (cobertura mínima de 70 %), revisa las librerías y arma el APK. Ver [10. Pruebas](#10-pruebas). |
| Fuera de esta versión | Pagos y cartera, clasificados, chat entre vecinos, recuperación de contraseña por correo, modo sin internet para la portería y varias unidades a la vez. Quedan para la **versión completa**. |

El historial de cambios está en [`CHANGELOG.md`](CHANGELOG.md).

## 2. Problema y solución

**Problema.** La unidad no tiene una herramienta digital única para la portería, los comunicados, las PQRS, las reservas y la paquetería: cada proceso se lleva por separado, en papel, cuadernos o chats. Por eso los registros de portería se pierden y no muestran quién sigue dentro, los avisos oficiales se mezclan con otros mensajes y no se sabe quién los leyó, las PQRS no tienen seguimiento, las reservas se cruzan y no hay un registro confiable de los paquetes ni de los parqueaderos de visitantes. Una encuesta de diagnóstico a 30 personas (residentes, arrendatarios, guardias y administradores), hecha entre mayo y junio de 2026, midió la satisfacción con la gestión actual en 2,30 sobre 5.

**Solución.** DOMUX reúne esos procesos en un servidor propio, una app Android y una web de administración. No pide hardware nuevo: usa los celulares de los residentes y la tablet o el celular de la portería.

## 3. Características

### App Android, por rol

Las tres cuentas entran por el mismo inicio de sesión y cada una ve solo lo suyo.

| Rol | Qué puede hacer |
| :--- | :--- |
| **Administración** (`ADMIN`) | Crear, editar y desactivar cuentas, y restablecer contraseñas (la persona debe cambiarla al entrar) · Armar la estructura de la unidad (torres, apartamentos, parqueaderos y cuartos útiles) y la ficha de cada hogar (integrantes, mascotas y vehículos) · Publicar comunicados con adjuntos · Responder las PQRS, una por una o por lotes · Aprobar o rechazar reservas y fijar las reglas de cada zona común · Registrar y consultar paquetes, y consultar las visitas y los vehículos de la portería. |
| **Residente** (`RESIDENT`) | Leer los comunicados · Radicar PQRS, conversar en su seguimiento y calificar la respuesta · Ver la disponibilidad de las zonas comunes, reservar (por franjas o el día completo, según la regla de cada zona) y cancelar · Ver sus paquetes y generar el código para que otra persona los recoja · Autorizar o rechazar a un visitante desde la app · Crear y anular códigos QR de acceso para sus visitas · Editar sus datos de contacto y ver la ficha de su hogar. |
| **Portería** (`GUARD`) | Tomar el turno con su PIN de 4 dígitos · Registrar paquetes (con foto, video o audio de evidencia), entregarlos y archivarlos · Registrar visitantes, autorizarlos con una llamada al residente, y anotar su entrada y salida · Escanear los códigos QR con la cámara · Registrar la entrada y la salida de los vehículos de visitantes y de residentes, con el tablero de parqueaderos · Buscar residentes (cada consulta de un teléfono queda en la auditoría). |

Todas las cuentas reciben notificaciones dentro de la app y, si el servidor tiene Firebase configurado, avisos al celular.

### Web de administración

Funciona en el navegador del computador y es solo para la administración. Tiene el resumen de lo pendiente del día y las mismas funciones de la app, más las que pesan demasiado para el celular: importar el censo de residentes desde Excel, sacar información en Excel (PQRS, reservas, visitas, paquetes, vehículos, comunicados y usuarios, por fechas y por apartamento), el archivo histórico y las copias de respaldo.

Páginas: usuarios, estructura de la unidad, datos de la unidad, zonas comunes, comunicados, PQRS, reservas, paquetería, visitas, vehículos, notificaciones, descargas, archivo histórico y respaldo.

En el inicio de sesión, la casilla «Recordar mi correo en este equipo» (apagada al comienzo) hace que ese navegador guarde el correo y el nombre, nunca la contraseña. La próxima vez basta con tocar la cuenta y escribir la contraseña; cada cuenta se quita del equipo con su X.

### Seguridad

- **Sesión con token.** Quien inicia sesión recibe un token JWT (una «llave» firmada) que dura 7 días. En el celular se guarda cifrado con el Android Keystore (`AES/GCM`).
- **Permisos en dos capas (RBAC).** La app muestra a cada rol solo sus opciones, y el servidor vuelve a revisar el rol en cada ruta (`@token_required` y `@role_required`): una llamada directa sin permiso responde `403`.
- **Bloqueos.** Al quinto intento fallido seguido, el inicio de sesión (o el PIN de un guardia) queda bloqueado 15 minutos.
- **Nada se borra.** Los paquetes y los comunicados se archivan o se retiran; el historial viejo pasa a archivos comprimidos con huella SHA-256 que se pueden descargar y volver a cargar.
- **Secretos fuera del repositorio.** Las claves y las contraseñas viven en variables de entorno; `.env`, `google-services.json` y las copias de la base están en `.gitignore`.

### Contrato de la API

El servidor tiene 111 operaciones en 18 módulos (salud, sesión, usuarios, residentes, administración, hogares, unidad, estructura, comunicados, PQRS, zonas comunes, reservas, notificaciones, paquetes, visitas, códigos QR, vehículos y documentos legales). Todas están descritas en [`docs/api/openapi.yaml`](docs/api/openapi.yaml), el contrato en formato OpenAPI 3.0 (cómo se ve y cómo se mantiene: [`docs/api/README.md`](docs/api/README.md)). Una prueba automática lo compara con el servidor real en cada cambio, así que no puede quedar desactualizado.

## 4. Tecnologías

Las versiones salen de los archivos de dependencias: [`backend/requirements.txt`](backend/requirements.txt), [`backend/requirements-dev.txt`](backend/requirements-dev.txt) y [`android/app/build.gradle.kts`](android/app/build.gradle.kts).

| Parte | Tecnología y versión |
| :--- | :--- |
| Servidor | Python 3.11 · Flask 3.1.3 · Flask-SQLAlchemy 3.1.1 con SQLAlchemy 2.0.57 · Flask-Migrate 4.1.0 (Alembic) · Flask-Cors 6.0.5 · PyJWT 2.15.1 · python-dotenv 1.2.4 · gunicorn 23.0.0 |
| Web de administración | Plantillas Jinja2 (vienen con Flask) · hojas de estilo propias · openpyxl 3.1.5 para los archivos de Excel |
| Base de datos | SQLite (la que se usa si no se configura otra) y PostgreSQL 18 con psycopg2-binary 2.9.13 |
| Avisos al celular | Firebase Cloud Messaging (firebase-admin 7.7.0 en el servidor; Firebase BoM 33.4.0 en la app) |
| App Android | Kotlin 1.9.24 · Jetpack Compose (BoM 2024.09.00) con Material 3 1.3.0 · Navigation Compose 2.8.1 · ViewModel 2.8.6 · Retrofit 2.9.0 con Gson · ZXing 4.3.0 para los QR · corrutinas 1.8.1 |
| Compilación de la app | Android Gradle Plugin 8.5.2 · Gradle 8.7 · JDK 17 · `minSdk` 24 (Android 7.0) · `targetSdk` y `compileSdk` 34 |
| Calidad | `unittest` · coverage 7.10.7 · Ruff 0.14.5 · pip-audit 2.9.0 · PyYAML 6.0.3 (lee el contrato de la API en las pruebas) · GitHub Actions |

**Cómo está armada la app (MVVM).** Cada módulo tiene su `ViewModel`: guarda el estado de la pantalla y hace las llamadas al servidor. Las pantallas (`*Screen.kt`) solo dibujan lo que el ViewModel les entrega. Cuatro piezas todavía llaman al servidor sin ViewModel: la revisión de la sesión al abrir la app, el selector de apartamento, el buscador de residentes y el diálogo del turno de portería.

**Cómo está armado el servidor.** Rutas (`routes/`) → reglas de negocio (`services/`) → modelos (`models.py`). Los errores salen siempre con la misma forma, `{"error": "texto", "status": 400}`.

## 5. Requisitos previos

**Para el servidor:**

- Python 3.11 o superior con `pip`.
- Nada más para una prueba rápida: sin configurar nada usa SQLite.
- PostgreSQL (el proyecto se prueba con la versión 18) si quieres usar la base real y las copias de seguridad.
- El puerto 5000 libre (y el 5432 si usas PostgreSQL).

**Para la app:**

- Android Studio con soporte para el plugin de Android 8.5.2 (Koala, 2024.1.1, o más nuevo) y JDK 17.
- Un emulador o un celular con Android 7.0 (API 24) o superior.
- Opcional, para los avisos al celular: una cuenta de Firebase y su archivo `google-services.json`.

## 6. Instalación

Todo el servidor está en la carpeta `backend/`. En PowerShell (Windows):

```powershell
git clone https://github.com/MAICOL-ESNEIDER/domux-ga4.git
cd domux-ga4/backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

En Linux o macOS, el cuarto comando cambia por `source venv/bin/activate`.

Si PowerShell no deja activar el entorno, ejecuta antes `Set-ExecutionPolicy -Scope Process Bypass`.

Para correr las pruebas y revisar el código, instala además las herramientas de desarrollo:

```powershell
pip install -r requirements-dev.txt
```

Para la app: abre la carpeta `android/` con Android Studio (**Open**) y espera a que Gradle termine de sincronizar.

## 7. Configuración

El servidor lee su configuración de variables de entorno. Copia el archivo de ejemplo y escribe tus propios valores:

```powershell
Copy-Item .env.example .env       # Linux o macOS: cp .env.example .env
```

El archivo [`backend/.env.example`](backend/.env.example) lista todas las variables, con su explicación. `.env` nunca se sube a GitHub. Las principales:

| Variable | Para qué sirve |
| :--- | :--- |
| `JWT_SECRET` | La clave que firma los tokens de sesión. Larga y al azar (64 caracteres). **Obligatoria en producción**; en desarrollo, si falta, se usa una temporal. |
| `DATABASE_URL` | Dirección de la base. Si no se define, se usa SQLite. Ejemplo: `postgresql://usuario:clave@localhost:5432/domux` |
| `SEED_ADMIN_PASSWORD`, `SEED_GUARD_PASSWORD`, `SEED_RESIDENT_PASSWORD` | Las contraseñas de las cuentas de prueba, una por rol: administración, los 4 guardias y los 12 residentes (mínimo 8 caracteres, con mayúscula, minúscula, número y símbolo). Si faltan, el servidor las crea al azar y las guarda en `backend/instance/demo_credentials.txt`, un archivo que nunca se sube. |
| `DOMUX_DEMO_DATA` | Con `0`, el servidor no agrega los datos de prueba de `backend/demo_data.py` (las pruebas automáticas lo apagan). Por defecto se agregan. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | La cuenta de servicio de Firebase, para los avisos al celular. Sin ella el servidor funciona, sin avisos. |
| `CORS_ORIGINS` | Páginas de otro dominio que pueden llamar a la API. Déjala vacía: la app y la web no la necesitan. |
| `APP_ENV`, `FLASK_DEBUG`, `LOG_LEVEL` | Producción fuera de Render (`production`), depuración local (`1`) y nivel de los registros. |
| `PORT`, `VISITOR_PARKING_MAX_DAYS` | Opcionales: el puerto (5000) y los días que un vehículo visitante puede quedarse (3). |
| `BACKUP_DIR`, `BACKUP_KEEP`, `PG_BIN_DIR` | Para las copias de seguridad (ver [`backend/scripts/LEEME.md`](backend/scripts/LEEME.md)). |

**App Android.** La variante `dev` se conecta a `http://10.0.2.2:5000/` (la dirección que el emulador usa para llegar al computador). Con un celular físico, escribe en `android/local.properties` la dirección del computador en la red: `domux.dev.baseUrl=http://<IP-del-computador>:5000/`. Los avisos al celular solo funcionan si pones tu `google-services.json` en `android/app/` (está en `.gitignore`).

## 8. Migraciones y semillas

- **Migraciones.** La estructura de la base está en `backend/migrations/versions/` (20 migraciones de Alembic, en orden). El servidor las aplica solo al arrancar, igual en SQLite y en PostgreSQL; una base creada antes de las migraciones se completa sin perder datos. Las pruebas también las aplican desde cero cada vez que arman la aplicación. Para crear una migración nueva, sigue [`backend/migrations/README`](backend/migrations/README).
- **Semillas.** La primera vez que arranca con la base vacía, el servidor (`backend/seed.py`) crea las cuentas de prueba (administración, portería y dos residentes) y una unidad de ejemplo con su estructura. Si en `.env` no pusiste las contraseñas `SEED_*`, el servidor las crea al azar y las guarda, junto con los correos, en `backend/instance/demo_credentials.txt` (ese archivo no se sube a GitHub). Si pones o cambias una `SEED_*`, el servidor aplica la contraseña nueva al reiniciar a todas las cuentas de prueba de ese rol.
- **Datos de prueba.** Después, el servidor agrega lo que falta para probar cada opción (`backend/demo_data.py`), sin borrar ni cambiar nada de lo que ya hay: quedan 17 usuarios (1 de administración, 4 guardias y 12 residentes en cuatro hogares, con propietarios, arrendatarios, propietarios que no viven ahí, adultos mayores y menores de edad), parqueaderos, cuartos útiles, vehículos, mascotas, comunicados, PQRS, reservas, paquetes, visitas, códigos QR y notificaciones. Se agregan una sola vez (queda una marca en el registro de auditoría) y solo en una base que tenga las cuentas de la semilla. Las cuentas nuevas usan la contraseña de su rol; los guardias nuevos empiezan sin PIN y se lo asigna la administración.
- **Empezar de cero.** Con SQLite, detén el servidor y borra el archivo `domux.db` de `backend/instance/`; al arrancar de nuevo se crea la base y las semillas. Con PostgreSQL, usa una base nueva y vacía.

## 9. Ejecución

**Servidor en desarrollo:**

```powershell
cd backend
python app.py
```

Queda escuchando en `http://localhost:5000/`. Comprueba que está vivo con `http://localhost:5000/api/health`. La dirección principal lleva a la web de administración. Para depurar, define `FLASK_DEBUG=1` (solo en tu computador).

**Servidor en producción** (Linux, como en Render):

```bash
gunicorn app:app
```

Escucha en el puerto de la variable `PORT` (Render la define sola) o, si no existe, en el 8000.

**App Android.** En Android Studio elige la variante en **Build Variants** y pulsa **Run**:

- `devDebug`: se conecta al servidor de tu computador (ver [7. Configuración](#7-configuración)).
- `prodDebug`: se conecta al servidor de pruebas en la nube (ver [11. Despliegue](#11-despliegue)).

También se puede armar desde la terminal:

```powershell
cd android
.\gradlew.bat :app:assembleDevDebug      # Linux o macOS: ./gradlew :app:assembleDevDebug
```

El APK queda en `android/app/build/outputs/apk/`.

## 10. Pruebas

**Servidor.** Desde `backend/`:

```powershell
python -m unittest discover -s tests
```

Son más de 1.200 pruebas automáticas: cada ruta con sus roles, las reglas de negocio, la web de administración, las copias de seguridad, los documentos legales y el contrato de la API. Por defecto usan una base SQLite en memoria, así que no tocan tu base.

**En PostgreSQL.** Crea una base **vacía, solo para pruebas**, y dile a las pruebas cuál es:

```powershell
$env:TEST_DATABASE_URL = "postgresql://usuario@localhost:5432/domux_pruebas"   # Linux o macOS: export TEST_DATABASE_URL=...
python -m unittest discover -s tests
```

Las pruebas **borran y vuelven a crear las tablas** de esa base: nunca la apuntes a una con datos.

**Cobertura y revisión del código** (lo mismo que hace el pipeline):

```powershell
coverage run -m unittest discover -s tests
coverage report                                      # falla si la cobertura baja de 70 %
ruff check . --select F,E9 --exclude migrations
```

**Pipeline.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre con cada subida a las ramas principales y en cada pull request: Ruff, las pruebas con cobertura en SQLite y en PostgreSQL, `pip-audit` (librerías con fallas conocidas) y el armado del APK. También corre al subir una etiqueta de versión (`v1.0.0-rc.1`, `v1.0.0`); con la versión final (`v1.0.0`, sin guion) además exige que los ocho documentos legales estén vigentes (ver [`backend/legal/LEEME.md`](backend/legal/LEEME.md)).

**App Android.** Todavía no tiene pruebas automáticas propias: el pipeline comprueba que compila y arma el APK, y las funciones se prueban a mano.

## 11. Despliegue

Hay dos formas de correr DOMUX:

1. **En local: es la entrega.** El servidor corre con `python app.py` en el computador de la demostración, con SQLite o con PostgreSQL local, y la app se instala con la variante `dev` apuntando a ese computador.
2. **Servidor de pruebas en Render.** [`render.yaml`](render.yaml) describe el servicio web `domux-ga4` (rama `release/v1.0-reducida`, Python 3.11.9, `gunicorn app:app`, revisión de salud en `/api/health`) y una base PostgreSQL 18. En el panel de Render se crea con **New + › Blueprint**. Sus secretos (`JWT_SECRET`, las contraseñas de las cuentas de prueba y `FIREBASE_SERVICE_ACCOUNT_JSON`) se escriben en el panel, nunca en el repositorio. Con cada subida, el pipeline arma el APK `prodDebug` que apunta a ese servidor; se baja desde la pestaña **Actions** de GitHub y dura 14 días.

Las copias de seguridad de la base (diarias y automáticas, con su restauración) están explicadas en [`backend/scripts/LEEME.md`](backend/scripts/LEEME.md).

Los documentos legales (política de datos, términos, cookies y los demás) se leen sin iniciar sesión: en la web en `/web/legal`, en la app desde el inicio de sesión y desde «Más» o «Mi hogar», y en la API en `/api/legal`. Hoy los ocho están «en preparación»; cómo se escribe y se publica cada uno está en [`backend/legal/LEEME.md`](backend/legal/LEEME.md).

## 12. Estructura del repositorio

```text
.
├── .github/
│   ├── workflows/ci.yml            → Pipeline: pruebas, cobertura, revisión de librerías y APK
│   └── pull_request_template.md    → Lista que se llena en cada pull request
├── android/                        → App Android (Kotlin y Jetpack Compose)
│   └── app/src/main/java/.../domux/
│       ├── data/                   → Cliente del servidor (Retrofit), sesión cifrada y modelos
│       ├── ui/theme/               → Colores, tipografía y tema Material 3
│       ├── *Screen.kt              → Las pantallas
│       ├── *ViewModel.kt           → El estado de cada módulo y sus llamadas al servidor
│       └── DomuxComponents.kt      → Piezas que se repiten (menú, pestañas, avisos, buscador)
├── backend/                        → Servidor (API) y web de administración
│   ├── routes/                     → Las rutas de la API, por tema
│   ├── services/                   → Las reglas de negocio
│   ├── web/                        → Web de administración: vistas, plantillas HTML y estilos
│   ├── migrations/                 → Los cambios de la base de datos, en orden (Alembic)
│   ├── legal/                      → Los textos de los documentos legales (uno por archivo)
│   ├── scripts/                    → Copia de seguridad y restauración de la base, y revisión de los documentos legales
│   ├── tests/                      → Pruebas automáticas
│   ├── app.py                      → Arranque del servidor y migraciones
│   ├── models.py                   → Las tablas de la base de datos
│   ├── seed.py                     → Cuentas y datos de prueba de la primera vez
│   ├── requirements.txt            → Librerías del servidor, con versiones fijas
│   ├── requirements-dev.txt        → Herramientas para probar y revisar el código
│   └── .env.example                → Variables de entorno de ejemplo
├── docs/api/                       → Contrato de la API (OpenAPI)
├── Documentacion_Proyecto_ADSO/    → Documentación formal del proyecto (SENA ADSO)
├── CHANGELOG.md                    → Historial de cambios
├── CONTRIBUTING.md                 → Cómo trabajamos en equipo: ramas, commits y pull requests
├── LICENSE                         → Licencia: todos los derechos reservados
├── THIRD_PARTY_NOTICES.md          → Licencias de las librerías que se usan
└── render.yaml                     → Descripción del servidor de pruebas en Render
```

## 13. Autores y contribuciones

| Integrante | Rol en el proyecto |
| :--- | :--- |
| Maicol Esneider Posada Callejas | Líder del proyecto, Scrum Master y líder técnico |
| Sebastián Lein Castro Grajales | Product Owner, analista y responsable de UX/UI |
| Nicolás Muñoz Hernández | Responsable de calidad y apoyo en UX/UI |

Para trabajar en el repositorio, lee [`CONTRIBUTING.md`](CONTRIBUTING.md): ramas por tarea (`feature/SCRUM-<n>-<nombre>`), commits en español con la clave de Jira (`tipo(SCRUM-n): descripción`) y pull requests con el pipeline en verde.

## 14. Licencia

**Todos los derechos reservados** © 2026 Maicol Esneider Posada Callejas, Sebastián Lein Castro Grajales y Nicolás Muñoz Hernández. Que el código se pueda ver en GitHub no autoriza a usarlo, copiarlo ni distribuirlo sin permiso de los tres autores. El texto completo está en [`LICENSE`](LICENSE).

Las librerías de terceros conservan sus propias licencias; están listadas en [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Más información

- **Documentación formal del proyecto** (formulación, requisitos, diseño, calidad, manuales y cierre): carpeta [`Documentacion_Proyecto_ADSO/`](Documentacion_Proyecto_ADSO/).
- **Contrato de la API:** [`docs/api/`](docs/api/).
- **Registro de decisiones del proyecto:** [`docs/adr/registro-decisiones.md`](docs/adr/registro-decisiones.md).
- **Reporte del ciclo de pruebas CIC-01:** [`docs/testing/cic-01.md`](docs/testing/cic-01.md).
- **Cambios de cada versión:** [`CHANGELOG.md`](CHANGELOG.md).
- **Relación con las guías GA1–GA3.** DOMUX parte de la estructura de esas guías y la lleva más lejos: `data/Models.kt`, `data/ApiService.kt`, `data/RetrofitClient.kt` y `data/Session.kt` ahora cubren todos los módulos, los tres roles y la sesión cifrada; `MainActivity.kt` usa `DomuxScreenScaffold` y el menú lateral; y el backend de Flask pasó a capas (`routes/`, `services/`, `models.py`, `validators.py`).
