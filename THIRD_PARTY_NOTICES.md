# Avisos de librerías de terceros

DOMUX está hecho con software de otras personas y empresas. Cada librería conserva su propia licencia
y sus derechos de autor; este archivo las lista para cumplir con los avisos que esas licencias piden. La
licencia de DOMUX en sí está en el archivo [`LICENSE`](LICENSE) (todos los derechos reservados).

**Última revisión:** 16 de noviembre de 2026. **Cómo se revisó:**

- *Servidor (Python):* se leyó la licencia de cada paquete instalado (sus metadatos y, cuando el campo era
  ambiguo, su archivo de licencia).
- *Aplicación Android:* se comprobó cada licencia en la página oficial de cada proyecto. No se pudo consultar
  los repositorios de Maven desde el entorno de desarrollo, así que las versiones que llegan "indirectas"
  se indican de forma aproximada.
- Esto es una lista de trabajo del equipo, **no es asesoría legal**; la revisión legal final la hace una persona.

## Qué piden las licencias, en palabras sencillas

| Licencia | Qué pide |
|---|---|
| MIT, MIT-0, BSD-2-Clause, BSD-3-Clause, PSF-2.0 | Permisivas: se puede usar, incluso en un producto cerrado; si se reparte el software hay que conservar el aviso de derechos de autor y el texto de la licencia. |
| Apache-2.0 | Permisiva: igual que las anteriores, conservando también los avisos (`NOTICE`), y trae permiso de patentes. |
| MPL-2.0 (certifi) | Copyleft débil, por archivo: solo obliga si se modifican los archivos de esa librería. DOMUX no la modifica. |
| LGPL-3.0 (psycopg2) | Se usa sin modificarla, como librería aparte que se instala con `pip`, y por eso puede reemplazarse. Es la forma de uso que la LGPL permite en software propio. Su licencia trae una excepción para enlazar con OpenSSL. |
| Android Software Development Kit License (Google Play services y partes de Firebase) | Son los términos de Google para usar esos SDK dentro de una app: [developer.android.com/studio/terms.html](https://developer.android.com/studio/terms.html). |

El texto completo de cada licencia se consulta en `https://spdx.org/licenses/<identificador>.html`, por ejemplo
[Apache-2.0](https://spdx.org/licenses/Apache-2.0.html), [MIT](https://spdx.org/licenses/MIT.html) y
[BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html). La app y la página web mostrarán estos textos en el
documento legal «Licencias de terceros».

## Servidor (Python)

Las versiones de las librerías **directas** están fijadas en `backend/requirements.txt`. Las **indirectas** son las
que traen las directas y las que estaban instaladas al revisar; pueden cambiar si se actualizan. La página de cada
paquete está en `https://pypi.org/project/<nombre>/`.

El paquete `psycopg2-binary` trae dentro otras librerías (libpq de PostgreSQL, OpenSSL, Kerberos y OpenLDAP) con
sus propias licencias; están en la carpeta del paquete instalado (`licenses` y `sboms`).

| Librería | Versión | Licencia | Cómo llega |
|---|---|---|---|
| alembic | 1.20.1 | MIT | indirecta |
| anyio | 4.16.0 | MIT | indirecta |
| blinker | 1.9.0 | MIT | indirecta |
| CacheControl | 0.14.4 | Apache-2.0 | indirecta |
| certifi | 2026.10.23 | MPL-2.0 | indirecta |
| cffi | 2.1.1 | MIT-0 | indirecta |
| charset-normalizer | 3.5.2 | MIT | indirecta |
| click | 8.5.1 | BSD-3-Clause | indirecta |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | indirecta |
| et_xmlfile | 2.0.0 | MIT | indirecta |
| firebase_admin | 7.7.0 | Apache-2.0 | directa |
| Flask | 3.1.3 | BSD-3-Clause | directa |
| flask-cors | 6.0.5 | MIT | directa |
| Flask-Migrate | 4.1.0 | MIT | directa |
| Flask-SQLAlchemy | 3.1.1 | BSD-3-Clause | directa |
| google-api-core | 2.44.0 | Apache-2.0 | indirecta |
| google-auth | 2.62.1 | Apache-2.0 | indirecta |
| google-cloud-core | 2.8.0 | Apache-2.0 | indirecta |
| google-cloud-firestore | 2.34.1 | Apache-2.0 | indirecta |
| google-cloud-storage | 3.17.1 | Apache-2.0 | indirecta |
| google-crc32c | 1.9.0 | Apache-2.0 | indirecta |
| google-resumable-media | 2.11.0 | Apache-2.0 | indirecta |
| googleapis-common-protos | 1.76.0 | Apache-2.0 | indirecta |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | indirecta |
| grpcio | 1.85.1 | Apache-2.0 | indirecta |
| gunicorn | 23.0.0 | MIT | directa |
| h11 | 0.16.0 | MIT | indirecta |
| httpcore | 1.0.9 | BSD-3-Clause | indirecta |
| httpx | 0.28.1 | BSD-3-Clause | indirecta |
| idna | 3.20 | BSD-3-Clause | indirecta |
| itsdangerous | 2.2.0 | BSD-3-Clause | indirecta |
| Jinja2 | 3.1.6 | BSD-3-Clause | indirecta |
| Mako | 1.4.3 | MIT | indirecta |
| MarkupSafe | 3.0.4 | BSD-3-Clause | indirecta |
| msgpack | 1.2.4 | Apache-2.0 | indirecta |
| openpyxl | 3.1.5 | MIT | directa |
| opentelemetry-api | 1.45.2 | Apache-2.0 | indirecta |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | indirecta |
| proto-plus | 1.29.0 | Apache-2.0 | indirecta |
| protobuf | 7.36.2 | BSD-3-Clause | indirecta |
| psycopg2-binary | 2.9.13 | LGPL-3.0-or-later con excepción para OpenSSL | directa |
| pyasn1 | 0.6.5 | BSD-2-Clause | indirecta |
| pyasn1_modules | 0.4.2 | BSD-2-Clause | indirecta |
| pycparser | 3.12 | BSD-3-Clause | indirecta |
| PyJWT | 2.15.1 | MIT | directa |
| python-dotenv | 1.2.4 | BSD-3-Clause | directa |
| requests | 2.34.2 | Apache-2.0 | indirecta |
| SQLAlchemy | 2.0.57 | MIT | directa |
| typing_extensions | 4.16.0 | PSF-2.0 | indirecta |
| tzdata | 2026.6 | Apache-2.0 | directa |
| urllib3 | 2.8.0 | MIT | indirecta |
| Werkzeug | 3.1.9 | BSD-3-Clause | indirecta |

## Aplicación Android

Son las librerías declaradas en `android/app/build.gradle.kts` (más las que ellas traen). La versión de pruebas
que arma el pipeline (`prodDebug`) incluye además las herramientas de depuración.

| Librería | Versión | Licencia | Responsable |
|---|---|---|---|
| Jetpack Compose (`ui`, `ui-graphics`, `ui-tooling-preview`) y Material 3 (`material3`) | BOM 2024.09.00; `material3` 1.3.0 | Apache-2.0 | Android Open Source Project (Google) |
| AndroidX Core KTX | 1.13.1 | Apache-2.0 | Android Open Source Project (Google) |
| AndroidX Lifecycle (`lifecycle-runtime-ktx`, `lifecycle-viewmodel-compose`) | 2.8.6 | Apache-2.0 | Android Open Source Project (Google) |
| AndroidX Activity Compose | 1.9.2 | Apache-2.0 | Android Open Source Project (Google) |
| AndroidX Navigation Compose | 2.8.1 | Apache-2.0 | Android Open Source Project (Google) |
| Material Components para Android (`com.google.android.material:material`) | 1.12.0 | Apache-2.0 | Google |
| Firebase Cloud Messaging (`firebase-messaging`) | Firebase BoM 33.4.0 | Apache-2.0 (código abierto del SDK de Firebase); los paquetes publicados pueden declarar la Android Software Development Kit License | Google |
| Google Play services (`play-services-basement`, `play-services-base`, `play-services-tasks`...; llegan con Firebase Messaging) | según Firebase BoM 33.4.0 | Android Software Development Kit License | Google |
| kotlinx.coroutines (`-android`, `-play-services`) | 1.8.1 | Apache-2.0 | JetBrains |
| Biblioteca estándar de Kotlin | la del plugin de Kotlin 1.9.24 | Apache-2.0 | JetBrains |
| Retrofit y `converter-gson` | 2.9.0 | Apache-2.0 (Copyright 2013 Square, Inc.) | Square |
| OkHttp y Okio (llegan con Retrofit) | 3.14.x y 1.17.x (aprox.) | Apache-2.0 | Square |
| Gson (llega con `converter-gson`) | 2.8.x (aprox.) | Apache-2.0 (Copyright 2008 Google Inc.) | Google |
| ZXing Android Embedded (`zxing-android-embedded`) | 4.3.0 | Apache-2.0 (Copyright 2012-2022 ZXing authors, Journey Mobile) | Journey Mobile y autores de ZXing |
| ZXing core (`com.google.zxing:core`) | 3.5.3 | Apache-2.0 | Autores de ZXing |
| Otras librerías de AndroidX y Compose que las anteriores traen consigo | varias | Apache-2.0 | Android Open Source Project (Google) |
| Solo en la versión de depuración: `androidx.compose.ui:ui-tooling` y `ui-test-manifest` | BOM 2024.09.00 | Apache-2.0 | Android Open Source Project (Google) |

Herramientas para compilar la app (no van dentro del APK): Android Gradle Plugin 8.5.2, plugin de Kotlin 1.9.24 y
plugin de Google Services 4.4.2.

## Página web de administración

No incluye librerías de JavaScript ni de CSS de terceros, ni fuentes descargadas ni enlaces a servidores externos
(CDN). Usa las fuentes del sistema del dispositivo (la lista empieza por Roboto si el dispositivo la tiene) y todo
lo demás (estilos, scripts, logo) es propio. El servidor genera las páginas con Jinja2 (ver la tabla del servidor).

## Imágenes, iconos y logo

El logo de DOMUX y los iconos de la app (carpeta `android/app/src/main/res/drawable`) son dibujos propios del
equipo, según el comentario de cada archivo («dibujado para DOMUX» o «de la guía visual de DOMUX»), y quedan bajo
la licencia de DOMUX. Si algún dibujo se tomó de otra
fuente, hay que agregarlo en este archivo.

## Herramientas de desarrollo y pruebas (no forman parte del producto)

`coverage` (Apache-2.0), `ruff` (MIT), `pip-audit` (Apache-2.0) y `PyYAML` (MIT), declaradas en `backend/requirements-dev.txt`.
`PyYAML` solo lo usa la prueba que lee el contrato de la API (`docs/api/openapi.yaml`).

## Servicios externos (no son librerías)

- **Firebase Cloud Messaging** (Google): envía los avisos al celular. Se rige por los términos de Firebase y Google.
- **Render**: aloja el servidor de la demostración. Se rige por los términos de Render.

## Cómo mantener este archivo

Cuando se agregue o se actualice una librería, se agrega o se corrige su fila aquí. Antes de entregar una versión,
se vuelven a revisar las licencias de las librerías indirectas.
