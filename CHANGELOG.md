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

**Descarga directa de la app: /descargar**
- Nueva dirección `https://domux-ga4.onrender.com/descargar`: el propio servidor entrega la última APK como app Android y con su tamaño. Así el celular la instala sin el error «el paquete no es válido» que salía al descargar desde GitHub con el navegador del lector de QR.
- El QR del póster y el botón de la página de presentación usan esta dirección.

**Web en oscuro, como la app**
- La página de presentación de DOMUX se ve siempre en oscuro.
- El inicio de sesión y toda la administración web vienen en «Oscuro»; quien prefiera «Mixto» o «Automático» lo cambia en Preferencias.
- El inicio de sesión tiene el enlace «Volver a la página de DOMUX».

**Avisos al celular activados**
- Firebase quedó configurado: la APK ya se arma con los avisos al celular y el servidor puede mandarlos.
- La APK publicada también se actualiza cuando se lanza la revisión a mano desde GitHub («Run workflow»).

**Zonas completas en la app, verificar contacto y vehículo en el QR**
- App de administración: en «Datos de la unidad y zonas» ya se crean y retiran zonas y se cambian todas sus reglas (nombre, horario, duración de la franja, aforo, anticipación, plazo para cancelar, reservas por semana, franjas seguidas, día de mantenimiento y día completo).
- App de administración: en Usuarios aparece «pendiente de verificar» y el botón «Ya lo verifiqué» cuando un residente cambió su correo o teléfono.
- QR de visitas: el residente puede marcar «¿Vienen en vehículo?» y anotar tipo (carro o moto), placa, marca y color. El guardia lo ve al leer el QR y, después de la entrada de la persona, registra la del vehículo con un toque.

**La app y la web de administración se parecen más**
- App de administración: nueva pantalla «Datos de la unidad y zonas» (nombre, NIT, dirección y teléfono de portería; horario, aforo y anticipación de cada zona; cerrar y reabrir una zona), igual que «Datos de la unidad» y «Zonas comunes y reglas» de la web.
- La administración solo consulta los paquetes de los residentes: entregar, cambiar de estado, archivar y sacar de archivados quedan para la portería; ella solo lo hace con los paquetes de la unidad.
- Web: al editar un residente que cambió su correo o teléfono desde la app, aparece el aviso «pendiente de verificar» y la casilla para darlo por verificado.

**Portería: registro más simple, guía por llamada y «Entradas y entregas»**
- Registrar una visita muestra solo lo obligatorio; la estadía, los detalles y la foto quedan en «Más datos (opcional)».
- Cuando el residente no responde en la app, la tarjeta de la visita guía al guardia: llamar al apartamento, preguntar y marcar «Sí autorizó» o «No autorizó» (nuevo: queda registrado el rechazo por llamada).
- Nueva pantalla «Entradas y entregas de hoy»: visitas que entraron o salieron, paquetes recibidos y entregados y vehículos de visitantes del día.
- La administración ve en su inicio cuántos vehículos de visitantes están adentro y cuántos pasaron el tiempo máximo.

**App del residente: lo que faltaba de la versión reducida**
- «Mis paquetes» y «Mis visitas y mi QR» son pantallas separadas, y el inicio trae atajos y el botón «Más».
- El QR de visitas lleva el nombre y el documento de cada persona (hasta 5), revisados; la portería ve qué documento debe pedir.
- Preferencia «Formato de la hora»: 12 horas (2:30 p. m.) o 24 horas (14:30), en toda la app.
- Reservas: las franjas que no se pueden elegir dicen si están «Ocupadas» o «Cerradas».
- Comunicados de tipo «Otra» con un nombre que escribe la administración (app y web).
- Mi perfil: ya no pide redes sociales; cambiar el correo o el teléfono pide la contraseña actual y queda «pendiente de verificar» hasta que la administración lo revise.
- Textos legales por rol: la portería y la administración tienen su propio compromiso con los datos.
- Sin internet o con el servidor despertando, la app vuelve a intentar sola dos veces antes de mostrar el error.

**Reglas de la unidad conectadas: QR automático y motos por cupo**
- QR automático: cuando el guardia registra la entrada de una visita que se queda los días de la regla o más (2 por defecto), DOMUX le crea al residente un QR para ese visitante, válido los días de la estadía, y le avisa para que lo comparta.
- Motos por cupo de carro: un parqueadero de visitantes se puede marcar «para motos» (app y web). Ahí caben las motos de la regla (6 por defecto); con el cupo lleno queda ocupado y se libera cuando sale una. El guardia elige «Carro» o «Moto» al registrar la entrada.

**La administración anuncia técnicos y paquetes de la unidad**
- La administración ya no registra visitas ni paquetes de los residentes (eso es de la portería). Ahora anuncia con anticipación a los técnicos y contratistas que vienen a trabajar en las zonas comunes (ascensores, piscina, jardín…) y los paquetes de la unidad (repuestos, materiales, plantas, herramientas).
- El guardia los ve como «Esperados por la administración» en el inicio y en Visitas; el técnico ya llega autorizado y solo se registra su entrada. Los paquetes de la unidad aparecen «Por llegar».
- En la app de administración: pestañas «Paquete para la unidad» y «Técnicos esperados». En la web: nueva sección «Esperados por la administración» en Paquetería y visitas.

**Portería: Paquetes y Visitas por separado y un solo escáner**
- En la app del guardia, «Paquetes» y «Visitas» del menú abren cada una solo sus pestañas (antes se veían las cinco juntas).
- Un solo botón «Escanear código» (en el inicio y arriba de Paquetes y Visitas) lee tanto el QR de una visita como el código de entrega de un paquete y abre lo que corresponde.

- App de administración: nueva pantalla «Reglas de la unidad» (en «Más») para cambiar desde el celular los mismos plazos y límites que ya se cambiaban en la web.

**Limpieza de la base para la exposición**
- Una limpieza que se hace una sola vez (se pide con `DOMUX_EXPO_ACCION=limpiar`): borra las pruebas sueltas (2 comunicados, 2 PQRS con fotos sin relación, 3 paquetes «de prueba», 1 visita pendiente y los intentos de inicio de sesión fallidos), deja un solo ejemplo vencido de cada cosa y crea copias nuevas que siguen vigentes el 1 de diciembre. Antes de borrar, cada fila queda escrita en el registro del servidor para poder reponerla.

**Nuevo ícono de DOMUX**
- El logo nuevo (edificios azules con una D) es el ícono de la app en el celular (adaptable, con fondo azul noche, resplandor celeste y versión monocromática para Android 13), la marca dentro de la app y el logo y el favicon de la web de administración.

**Más reglas de la unidad que la administración puede cambiar**
- En «Reglas de la unidad» (web y API) se pueden ajustar seis reglas que estaban fijas en el código: la estadía máxima de una visita (30 días por defecto, antes 7), las personas por QR (5, antes sin tope), la vigencia de un QR (30 días), desde cuántos días de estadía el QR se crea solo (2), los días para archivar un paquete entregado (7) y las motos que caben en un parqueadero de carro de visitantes (6). Cada una tiene mínimo y máximo, valor de DOMUX y queda en la auditoría.

**Página de bienvenida**
- La dirección principal del servidor (`/`) ahora muestra una página pública que explica DOMUX para residentes, portería y administración, con el botón para descargar la app (Android), la entrada a la administración, la documentación de la API y el código. No muestra datos de nadie ni cuentas de prueba.

**Documentación de la API**
- Página `/docs` (Swagger UI) en el propio servidor: se abre sin sesión, muestra todas las rutas del contrato y permite probarlas con «Try it out» contra el mismo servidor.

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
- **Zonas comunes completas** (DEC-032): la administración agrega las zonas que tiene su unidad, les
  cambia el nombre, las **cierra con un motivo** cuando fallan (los residentes ven «Cerrada» y el
  motivo, y no pueden pedir reservas nuevas), las vuelve a abrir y retira las que ya no existen.
  Al cerrar una zona, las reservas que ya tenía se mantienen y la administración recibe un aviso con
  cuántas son; no se puede aprobar una solicitud pendiente de una zona cerrada ni retirar una zona con
  reservas próximas. Nada se borra: una zona retirada conserva sus reservas viejas con su nombre.
- **Reglas de la unidad** (DEC-032): lo que la asamblea cambia cada año ahora lo ajusta la
  administración en la web, sin pedirle nada al equipo técnico: los **días hábiles para responder una
  PQRS** (general y propio de cada tipo: petición, queja, reclamo, sugerencia o daño), cuántos días
  antes del vencimiento el semáforo pasa a amarillo, las **horas sin reclamar** para el aviso naranja
  y rojo de un paquete y los **días máximos de un vehículo visitante** en el parqueadero. Cada valor
  se revisa (con su mínimo y su máximo) y el sistema avisa si las reglas no tienen sentido juntas. Un
  cambio rige desde que se guarda, también para lo que ya existe, y los textos de la app, de la web y
  de las alertas dicen el plazo real de la unidad. Donde no se cambia nada rige el valor de DOMUX
  (15 días hábiles, 5 de aviso, 48 y 72 horas, 3 días) y cada regla se puede restablecer. Cada cambio
  queda en la auditoría con lo de antes y lo de después.
- **Documentos de la unidad** (DEC-032): la administración sube en la web el manual de convivencia,
  las reglas, los presupuestos aprobados, los históricos de gastos y las actas (PDF o imagen de hasta
  6 MB, revisados por sus primeros bytes y no por el nombre) y **marca quién los puede ver**:
  propietarios, arrendatarios, otros residentes o portería. Cada persona ve en la app solo los suyos,
  agrupados por tipo, y los abre dentro de la app sin guardar nada en el celular; un documento que no
  es suyo responde como si no existiera. Se puede avisar con una notificación a quienes lo ven.
  La administración edita el título, la descripción, el tipo y los públicos, retira un documento (deja
  de verse pero queda guardado) y lo vuelve a publicar con los mismos públicos; para una versión nueva
  se sube un documento nuevo y se retira el viejo. Cada cambio queda en la auditoría.
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
- «Recordar mi correo en este equipo» (HU-074): la casilla empieza apagada; si se marca, el navegador
  guarda el correo y el nombre, nunca la contraseña. En el siguiente ingreso salen como «Cuentas
  recientes en este equipo»: se toca la cuenta y se escribe solo la contraseña, y cada una se quita con
  su X. El servidor no guarda ninguna lista.
- Panel de pendientes, usuarios, estructura de la unidad, documentos de la unidad, datos de la
  unidad, PQRS, reservas, comunicados y zonas con sus reglas, y paquetería y visitas en modo consulta.
- Botón «Filtros» en las listas.
- **Buscador general** (HU-089): una caja arriba de cada página con el filtro «Buscar en» (todo,
  personas, apartamentos, vehículos, PQRS, paquetes o visitas). Muestra los resultados agrupados por
  tipo, con pocos al buscar en todo y más al elegir un solo lugar, y cada uno lleva a su página. Lo
  hace el servidor (`GET /api/search`), el mismo que usará la app para administración y portería.
- **Diseño «Mixto»** (HU-087): menú oscuro a la izquierda y contenido claro, con los mismos colores de
  estado y el contraste revisado por una prueba automática. Abajo del menú va quién entró (nombre,
  rol, Preferencias, Cambiar contraseña y Cerrar sesión) y arriba, la búsqueda y el botón **«+ Nuevo»**
  para crear un comunicado, un usuario, una torre, un apartamento o una PQRS a nombre de un residente.
- **Preferencias**: apariencia (Automático, Mixto u Oscuro), tamaño del texto (normal, grande o muy
  grande) y las cuentas recordadas en ese equipo, que se pueden quitar. Se guardan solo en el
  navegador; el servidor no guarda nada de esto.
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
- Pantalla «Acepto» (app y web de administración): la primera vez que una persona entra, y cada vez
  que cambia la versión de los términos, la política de tratamiento de datos o la autorización,
  debe leerlos y aceptarlos (Ley 1581 de 2012). Hasta entonces el servidor solo le deja ver su
  sesión, leer los textos y aceptar (responde 403 con `legalAcceptanceRequired`). Se guarda cuándo
  aceptó y cuál versión leyó, y queda en la auditoría. Rutas nuevas: `GET /api/auth/legal-acceptance`
  y `POST /api/auth/accept-legal`. Si es menor de edad, acepta su representante legal.
- Los ocho tienen un borrador de demostración (versión 0.1) escrito con todas las funciones de la app: visitas y
  QR, paquetes, vehículos, mascotas y familiares, reservas, PQRS, comunicados, documentos, avisos al celular
  (Firebase), menores de edad y la Ley 1581 de 2012. Cada uno empieza con el aviso «Borrador de
  demostración»; quién es el responsable queda «por completar». Un programa revisa que cada texto esté bien armado y, para la
  versión final, exige que todos estén vigentes (`python -m scripts.verificar_legal`).

**App Android**
- Menú y pantalla de inicio por rol, íconos, colores con nombre y avisos explícitos de éxito y error
  (HU-086, HU-002).
- Buscador con botón «Filtros» en las listas.
- **Buscador general y botón «+ Nuevo»** (HU-089), solo para la administración y la portería: la caja
  del inicio y la lupa de la barra de arriba abren el buscador, con el filtro «Buscar en» (todo,
  personas, apartamentos, vehículos, PQRS, paquetes o visitas) y los resultados agrupados por tipo. Es
  el mismo del servidor que usa la web (`GET /api/search`); la portería no busca en PQRS. Al tocar un
  resultado se abre la pantalla donde se ve, ya con la búsqueda puesta. El botón **«+ Nuevo»** de la
  barra de arriba crea de una vez: en administración un comunicado, un usuario, una torre, un
  apartamento o una PQRS a nombre de un residente; en portería una visita, un paquete o la entrada de
  un vehículo.
- **Preferencias**, en el menú de todos los roles: el tamaño del texto (normal, grande o muy grande),
  que se aplica al instante a toda la app y se suma al que ya tenga el celular, y las cuentas
  recordadas en ese celular, que se quitan de una en una o todas juntas. Se guardan solo en el
  celular; el servidor no guarda nada de esto.
- «Recordar mi correo en este celular» en el inicio de sesión (HU-001): la casilla empieza apagada
  y solo guarda el correo y el nombre, cifrados en el celular, nunca la contraseña. Salen como
  «Cuentas recientes en este celular» (hasta 5): se toca la cuenta y se escribe solo la contraseña.
  Cada una se quita con su X (con «Deshacer»); cerrar sesión no las borra y no se copian a la nube.
- Ícono de la app con el logo de DOMUX (adaptable, para Android 7 y con versión monocromática).

**Calidad e infraestructura**
- Migraciones de la base con Flask-Migrate (TT-008).
- Datos de prueba para todas las opciones (CAL-01): el servidor agrega, sin borrar ni cambiar lo que
  ya hay, lo que falta para llegar a 17 usuarios (1 de administración, 4 guardias y 12 residentes en
  cuatro hogares con propietarios, arrendatarios, dueños que no viven ahí, adultos mayores y menores
  de edad) y lo mínimo de cada opción: parqueaderos, cuartos útiles, vehículos, mascotas, comunicados,
  PQRS con su semáforo, reservas, paquetes de más de 48 y 72 horas, visitas, QR y notificaciones.
  Cada cuenta usa la contraseña de su rol (las mismas variables `SEED_*`) y se cargan una sola vez.
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
- Pruebas de pantallas de la app (SCRUM-240): con datos de mentira, sin servidor y sin celular, la app
  dibuja sus pantallas en el celular y en la tablet para cada rol (administración, portería y
  residente), también con el texto muy grande y en pantallas largas, y les saca una foto. Además
  comprueban a mano lo nuevo de la versión: el buscador, el botón «+ Nuevo», el menú de cada rol y el
  cambio del tamaño del texto en Preferencias. Las fotos se bajan de cada ejecución del pipeline
  (carpeta «fotos-de-pantallas») y sirven de evidencia y para comprobar que ordenar el código no
  cambió nada de lo que se ve.

### Cambiado

- Se quitaron de la app y la web los avisos que decían que algo llegaría «en la versión completa» o que era «de demostración». En los textos legales, el aviso del principio ahora dice que lo preparó el equipo de DOMUX, que no es asesoría legal y que la unidad debe revisarlo con su asesor jurídico.- El Excel se maneja solo en la web de administración; la app no guarda archivos en el celular.
- PQRS: en una queja, un reclamo o un daño hay que decir cuándo pasó (fecha obligatoria, hora opcional; solo de hoy hacia atrás), en la app y en el servidor. La fecha y hora en que se radica la PQRS se guardan solas en todas. La tarjeta muestra «Radicado: …».

- App del residente: en Inicio y en Comunicados los enlaces azules pasaron a botones; los comunicados largos tienen «Leer más»; las notificaciones se marcan solas como leídas al abrirlas y salen con la etiqueta «Nueva».
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

- La API ahora manda las cabeceras `X-Content-Type-Options: nosniff` y `Cache-Control: no-store` (y HSTS en producción), como ya hacía la web.
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
- Que una persona con conocimiento legal revise los ocho borradores de los textos legales, y completar
  quién es el responsable de la unidad, antes de quitarles el aviso «Borrador de demostración».

### Pendiente para la versión completa
- Cambiar los colores de la app (Mixto u Oscuro) desde Preferencias, como ya se puede en la web.
- Cifrar con una clave los archivos que se exportan.
- Recuperar la cuenta por correo (hoy la restablece la administración).
- Guardar los archivos adjuntos aparte de la base de datos y pedirlos solo cuando se abren.
- Notificaciones push (Firebase está suspendido en esta versión).
