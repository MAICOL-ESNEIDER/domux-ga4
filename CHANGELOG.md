# Registro de cambios (CHANGELOG)

Aquí se anota todo lo importante que cambia en DOMUX. El formato sigue la idea de «Keep a Changelog»
(cada versión con sus secciones *Añadido*, *Cambiado*, *Corregido* y *Seguridad*) y las versiones
siguen el «Versionado Semántico» (MAYOR.MENOR.PARCHE; «rc» es la versión candidata, del inglés
*release candidate*, la que se prueba antes de entregar).

Los códigos entre paréntesis son los del proyecto: **HU** (historia de usuario), **TT** (tarea
técnica), **DEF** (defecto encontrado en la auditoría), **SEC** (requisito de seguridad), **RN**
(regla de negocio) y **DEC** o **ADR** (decisión registrada). Las historias y las tareas están en Jira
y las decisiones en `Documentacion_Proyecto_ADSO`.

## [Sin publicar] — hacia la versión candidata v1.0.0-rc.1 (Reducida 1.0)

La versión reducida es la que se entrega el 1 de diciembre de 2026. Son tres piezas que trabajan
juntas: la app Android (residentes, portería y administración), el servidor (API) y la web de
administración.

### Añadido

**Cuentas y estructura de la unidad**
- Torres, apartamentos, parqueaderos y cuartos útiles, y un selector de apartamento para vincular a
  cada residente (HU-013 a HU-018 y HU-023).
- Ficha del hogar con integrantes, mascotas (con vacunación y desparasitación, HU-021) y vehículos.
- Datos de la unidad: nombre, NIT, dirección, teléfono de portería y logo (HU-077).
- Censo de residentes por Excel y reporte legal en Excel con las PQRS, sus conversaciones, las
  reservas y el registro de auditoría.
- La persona de portería toma el turno en la tablet con su PIN de 4 dígitos (HU-010, RN-029, CU-008).

**Portería**
- Visitas con historial y filtros, estadía prevista y nombres de los visitantes en el QR
  (HU-030 a HU-033), con el documento del visitante.
- Vehículos de visitantes (con parqueadero) y de residentes, y aviso cuando un vehículo pasa el
  tiempo máximo (HU-035 a HU-041).
- Paquetes con transportadora y guía, código de entrega para el residente y alertas a las 48 y 72
  horas (HU-047 a HU-049).
- El residente crea el QR de su visita (HU-027) y el QR con PIN de 6 dígitos para que otra persona
  recoja su paquete (HU-048, RN-016), y los comparte por WhatsApp, correo u otra app.

**Comunidad**
- Reservas con reglas por zona común, de varias franjas seguidas o del día completo
  (HU-050 a HU-055).
- Comunicados por categoría y por torre, con vencimiento, lectura y «Archivados»
  (HU-058 a HU-062).
- PQRS con radicado, semáforo de plazos, conversación y respuestas por lotes (HU-072 y HU-073).
- Notificaciones dentro de la app (HU-064 y HU-065).
- Adjuntos como en WhatsApp: foto, video, audio y PDF, con revisión real de cada archivo en el
  servidor. Se ven dentro de la app y no se guarda nada en el celular (HU-042, HU-054, HU-057,
  HU-067 y HU-068).
- **Permiso de descarga:** quien sube un archivo decide si los demás pueden descargarlo; si no lo
  permite, solo se ve.

**Web de administración** (HU-074 a HU-081, HU-087 y HU-088)
- Inicio de sesión solo para la administración, sesión segura y la misma identidad visual de la app.
- Panel de pendientes, usuarios, estructura de la unidad, datos de la unidad, PQRS, reservas,
  comunicados y zonas con sus reglas, y paquetería y visitas en modo consulta.
- Botón «Filtros» en las listas.
- Zona **Descargas**: se marca qué datos se quieren (PQRS, reservas, visitas, paquetes…), las fechas
  y, si se quiere, un apartamento. Sale un Excel con una hoja por tipo que junta lo que está en la
  base con lo que ya está en el archivo histórico. También se puede bajar una sola PQRS o una sola
  reserva con su conversación, y queda un historial de lo descargado (quién, qué y cuándo).

**Datos históricos y copias**
- Archivo histórico mensual: nada se borra; cada mes y tipo de dato se guarda comprimido, con su
  huella SHA-256, y solo después de comprobar que se guardó bien se retira de las listas del día a
  día (ADR-013, DEC-090 y DEC-103). Se puede consultar, restaurar y descargar.
- Copia de respaldo descargable, sin contraseñas ni claves.
- Copia de seguridad diaria de la base de datos: deja las últimas 7 copias, cada una con su huella
  SHA-256, y un programa las restaura en otra base para comprobarlas (TT-009).

**Documentos legales**
- Espacio para los ocho documentos que pide la ley de protección de datos personales: política de
  tratamiento, aviso de privacidad, autorización, términos y condiciones, consultas y reclamos,
  cookies, responsable y encargado, y licencias de terceros. Cada uno es un archivo de
  `backend/legal/`; se lee sin iniciar sesión en la web (`/web/legal`), en la API (`/api/legal`) y
  en la app («Legal y privacidad» en «Más» o «Mi hogar», y un enlace en el inicio de sesión). Los
  formularios que piden la autorización de datos enlazan a su texto.
- Hoy los ocho están «en preparación». Un programa revisa que cada texto esté bien armado y, para la
  versión final, exige que todos estén vigentes (`python -m scripts.verificar_legal`).

**App Android**
- Menú y pantalla de inicio por rol, íconos, colores con nombre y avisos explícitos de éxito y error
  (HU-086, HU-002).
- Buscador con botón «Filtros» en las listas.
- Ícono de la app con el logo de DOMUX (adaptable, para Android 7 y con versión monocromática).

**Calidad e infraestructura**
- Migraciones de la base con Flask-Migrate (TT-008).
- Pipeline en GitHub Actions: pruebas en SQLite y en PostgreSQL, cobertura mínima de 70 %, revisión
  de errores con Ruff, búsqueda de librerías con fallas conocidas y compilación del APK
  (TT-021, TT-023).
- Pruebas automáticas que vigilan los permisos de todas las rutas (nadie queda sin sesión ni sin
  rol) y que ninguna lista haga una consulta más por cada fila.
- Contrato de la API en OpenAPI 3.0 (`docs/api/openapi.yaml`), con una prueba que lo compara con el
  servidor real en cada cambio (TT-022).
- Documentación para entregar: README con las secciones de la guía (TT-016), guía para colaborar y
  plantilla de pull request (TT-015), y licencia de todos los derechos reservados con los avisos de
  las librerías de terceros (TT-019).
- El pipeline también corre al subir una etiqueta de versión; con la versión final exige los
  documentos legales vigentes.

### Cambiado
- El Excel se maneja solo en la web de administración; la app no guarda archivos en el celular.
- Las horas se muestran y se comparan en hora de Colombia (TT-031, DEF-002).
- Errores del servidor en español y un solo registro de auditoría para todo el servidor (TT-013).
- Las listas del administrador (PQRS, reservas, resumen y reporte legal) cargan sus datos
  relacionados de una vez y no fila por fila; se agregaron índices a las columnas de las listas del
  residente (migración 0020).
- El servidor quedó más ordenado: la ficha del hogar, los filtros de usuarios y la importación del
  censo viven en funciones pequeñas y con nombre.

### Corregido
- Los paquetes nunca se borran; la papelera solo se restaura (TT-026, DEF-004).
- Retirar un comunicado ya no lo borra de la base (TT-029, DEF-005).
- Guardar la ficha del hogar ya no borra integrantes, mascotas ni vehículos (TT-032, DEF-007).
- Al desactivar a un usuario se anulan sus QR y se borran sus tokens (TT-027, DEF-003 y DEF-011).
- Se quitó de la app y del README la lista de cuentas de prueba (TT-016, DEF-009).
- Se quitó el plan funerario de las mascotas (DEF-013).

### Seguridad
- La cuenta se bloquea 15 minutos tras 5 intentos fallidos (HU-006, SEC-001 y SEC-011).
- Contraseña temporal: cuando la administración crea una cuenta o restablece una contraseña, la
  persona debe cambiarla en su primer ingreso, y al cambiarla se cierran las sesiones que habían
  quedado abiertas con la anterior.
- La web pide de nuevo la contraseña antes de descargar copias, archivos históricos o descargas a la
  medida.
- Cada ruta del servidor dice qué roles la usan (ADR-015, SEC-002 y SEC-015); una prueba lo revisa.
- Secretos fuera del código: el servidor no arranca en producción sin su clave y las cuentas de
  prueba nacen solo si se configuran por variables de entorno (TT-010).
- Servidor cerrado por defecto (CORS) y el token del QR oculto en los registros (SEC-012).
- Librerías sin fallas conocidas y con versiones fijas (TT-023).

### Pendiente antes de entregar la versión reducida
- Escribir y revisar los ocho textos legales (hoy están «en preparación»): una persona debe
  revisarlos antes de marcarlos como vigentes.

### Pendiente para la versión completa
- Cifrar con una clave los archivos que se exportan.
- Recuperar la cuenta por correo (hoy la restablece la administración).
- Guardar los archivos adjuntos aparte de la base de datos y pedirlos solo cuando se abren.
- Notificaciones push (Firebase está suspendido en esta versión).
