---
titulo: Licencias de terceros
resumen: Las librerías de otras personas y empresas que usa DOMUX y las licencias bajo las que se usan.
estado: vigente
version: 0.1
vigente_desde: 2026-11-25
---
## Borrador de demostración

Este texto es un borrador de demostración. Es una lista de trabajo del equipo y no es asesoría legal. Todavía no lo ha revisado una persona con conocimiento legal.

## 1. Sobre DOMUX y sobre las librerías

DOMUX es software de sus autores, con todos los derechos reservados. Para construirlo se usan librerías de otras personas y empresas. Cada una conserva sus derechos de autor y su propia licencia, y se usa cumpliendo los avisos que esa licencia pide. La lista completa, con las versiones, está en el archivo THIRD_PARTY_NOTICES.md del repositorio del proyecto.

## 2. Qué piden las licencias, en palabras sencillas

- MIT, BSD y PSF: son permisivas. Se pueden usar, incluso en un producto cerrado, conservando el aviso de derechos de autor.
- Apache-2.0: igual de permisiva; además pide conservar los avisos de la librería y trae permiso de patentes.
- MPL-2.0: solo obliga si se modifican los archivos de esa librería. DOMUX no la modifica.
- LGPL-3.0: se usa sin modificarla, como librería aparte que puede reemplazarse.
- Términos de Google para Android (Android Software Development Kit License): rigen los componentes de Google Play services y de Firebase que usa la app.

El texto completo de cada licencia se consulta en la página de licencias SPDX (spdx.org/licenses), con el nombre de la licencia al final de la dirección.

## 3. Servidor y web de administración (Python)

- Flask, Flask-SQLAlchemy, Jinja2, Werkzeug, MarkupSafe y otras: licencia BSD-3-Clause.
- Flask-Migrate, flask-cors, SQLAlchemy, Alembic, gunicorn, openpyxl, PyJWT y otras: licencia MIT.
- firebase-admin, requests, cryptography y las librerías de Google para Python: licencia Apache-2.0 (cryptography también puede usarse con BSD-3-Clause).
- psycopg2-binary, que conecta con PostgreSQL: licencia LGPL-3.0 con excepción para OpenSSL.
- certifi: licencia MPL-2.0.
- typing_extensions y greenlet: licencia PSF-2.0 y MIT.

## 4. App Android

- Jetpack Compose, Material 3, AndroidX (Core, Lifecycle, Activity, Navigation) y Material Components: licencia Apache-2.0, de Google.
- Retrofit, OkHttp y Okio, de Square: licencia Apache-2.0.
- Gson, de Google: licencia Apache-2.0.
- kotlinx.coroutines y la biblioteca estándar de Kotlin, de JetBrains: licencia Apache-2.0.
- ZXing y ZXing Android Embedded, para leer y crear códigos QR: licencia Apache-2.0.
- Firebase Cloud Messaging y Google Play services, de Google: código abierto bajo Apache-2.0 y términos de Google para Android.

## 5. Garantía

Las librerías se usan tal como las entregan sus autores, sin garantía de ningún tipo. Los nombres y marcas mencionados pertenecen a sus dueños.

## 6. Cambios

Cuando se agregue o se cambie una librería, esta lista y el archivo THIRD_PARTY_NOTICES.md se actualizan.
