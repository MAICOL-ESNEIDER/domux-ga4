# Documentos legales de DOMUX

Esta carpeta guarda los textos de los **ocho documentos legales** que DOMUX debe tener publicados: la política de
datos, el aviso de privacidad, los términos y las demás reglas que la ley pide cuando una aplicación guarda datos
de personas. Cada documento es **un archivo de texto**. El servidor lo lee y lo muestra en la web, en la app y en la
API, sin que haga falta tocar nada más.

**Estado de hoy: los ocho archivos son borradores de demostración.** Están escritos teniendo en cuenta todo lo que hace
DOMUX, marcados como `vigente` (versión `0.1`) y cada uno empieza con el aviso «Borrador de demostración»: todavía no
los revisó una persona con conocimiento legal ni los adoptó una unidad residencial real, y lo que depende de la unidad
(quién es el responsable, sus datos de contacto) dice «por completar». Cuando una persona con conocimiento legal los
revise, se reemplaza el texto, se quita el aviso y se sube la versión.

Palabras que se usan aquí:

- **Documento legal**: un texto que explica qué datos se guardan, para qué, y qué derechos tiene cada persona.
  En Colombia la base es la Ley 1581 de 2012 de protección de datos personales y sus decretos.
- **Encabezado**: las líneas del principio de cada archivo, entre dos rayas `---`, que dicen el título, el resumen
  y el estado del documento.
- **Estado**: `pendiente` (todavía no tiene su texto final ni validez) o `vigente` (ya está publicado y rige).
- **Bloque**: un trozo del texto ya separado en título, párrafo o lista. El servidor entrega el texto en bloques para
  que la app y la web lo dibujen igual, sin tener que entender ningún formato.
- **Pipeline**: la revisión automática de GitHub que corre las pruebas con cada cambio.

## 1. Los ocho documentos y dónde se ven

| Archivo | Documento | Dónde se ve hoy | Dónde falta enlazarlo cuando esté el texto |
|---|---|---|---|
| `politica-datos.md` | Política de tratamiento de datos personales | Web: pie de página y pantalla de ingreso. App: lista de «Legal y privacidad» | Ya se acepta en la pantalla «Acepto» del primer ingreso |
| `aviso-privacidad.md` | Aviso de privacidad | Web y app: lista de documentos | Una versión corta antes de pedir datos: ingreso y formularios de usuario y censo |
| `autorizacion-datos.md` | Autorización para el tratamiento de datos | Web: formularios «Nuevo usuario» y «Censo». App: formulario de usuarios | Ya se acepta en la pantalla «Acepto» del primer ingreso |
| `terminos.md` | Términos y condiciones de uso | Web: pie de página y pantalla de ingreso. App: lista (desde el enlace del inicio de sesión) | Ya se acepta en la pantalla «Acepto» del primer ingreso |
| `consultas-reclamos.md` | Consultas, reclamos y eliminación de datos | Web y app: lista de documentos | Un enlace desde PQRS y desde el perfil de cada persona |
| `cookies.md` | Política de cookies | Web: pie de página y pantalla de ingreso | Aviso de cookies de la web, si más adelante se agregan cookies que no sean de sesión |
| `responsable.md` | Responsable y encargado del tratamiento | Web y app: lista de documentos | Pie de la web y «Datos de la unidad» |
| `licencias-terceros.md` | Licencias de terceros | Web y app: lista de documentos | Una pantalla «Acerca de» en la app |

Las columnas se leen así: «hoy» es lo que ya funciona y se puede probar; «falta» es lo que se conecta **después** de
que los textos existan, porque depende de ellos.

Los lugares fijos de hoy:

- **Web de administración:** `/web/legal` (la lista) y `/web/legal/<nombre>` (cada documento). No piden sesión, para
  que se puedan leer antes de ingresar. Los enlaces están en la pantalla de ingreso y en el pie de cada página.
- **App Android:** «Legal y privacidad» dentro de «Más» (administración y portería) o de «Mi hogar» (residente), y un
  enlace en la pantalla de inicio de sesión. Desde ahí se abre la lista y luego cada documento.
- **API:** `GET /api/legal` (la lista) y `GET /api/legal/<nombre>` (el documento con su texto en bloques). Están en
  el contrato `docs/api/openapi.yaml`.

## 2. Cómo es un archivo

Cada archivo empieza con un encabezado y sigue con el texto:

```
---
titulo: Términos y condiciones de uso
resumen: Las reglas para usar la app y la web de DOMUX.
estado: pendiente
version:
vigente_desde:
---
## Documento en preparación

Este documento todavía no está publicado.
```

| Dato del encabezado | Qué es | ¿Obligatorio? |
|---|---|---|
| `titulo` | El nombre del documento, como se muestra | Sí |
| `resumen` | Una frase que dice de qué trata | Sí |
| `estado` | `pendiente` o `vigente` | Sí |
| `version` | La versión del texto publicado, por ejemplo `1.0` | Solo si es `vigente` |
| `vigente_desde` | El día desde el que rige, como `AAAA-MM-DD` (por ejemplo `2026-12-01`) | Solo si es `vigente` |

### Lo que se puede escribir en el texto

El texto es sencillo a propósito: así se ve igual en la app, en la web y en un lector de pantalla.

| Quieres | Escribe |
|---|---|
| Un título de sección | `## Título` (o `### Subtítulo`, un nivel más abajo) |
| Un párrafo | Las líneas seguidas forman un solo párrafo; una línea en blanco empieza otro |
| Una lista con viñetas | Una línea por elemento, empezando con `- ` |
| Una lista numerada | Una línea por elemento, empezando con `1.` o `1)` |
| Seguir un elemento en otra línea | Sangra la línea siguiente con espacios |
| Una nota para quien escribe | `<!-- nota -->` en una sola línea; no se muestra a nadie |

**No se puede** usar: negrita, enlaces, imágenes, tablas, citas con `>`, código, etiquetas HTML, viñetas con `*` ni
listas dentro de listas. Tampoco un título de nivel 1 (`#`): el título del documento va en `titulo:`. Si algo de esto
aparece, la revisión de la sección 4 lo dice con el número de la línea.

## 3. Cómo se publica un documento

1. Escribe el texto en su archivo. Mantén el nombre del archivo.
2. Cambia el encabezado: `estado: vigente`, la `version` y la fecha de `vigente_desde`.
3. Borra el título «Documento en preparación» (un documento vigente no puede conservarlo).
4. Corre la revisión de la sección 4.
5. **Una persona con conocimiento legal revisa el texto** antes de que se marque como vigente. Un texto sin esa
   revisión no debe publicarse como si ya valiera.
6. Súbelo como cualquier cambio (ver `CONTRIBUTING.md`); el pipeline vuelve a revisar los archivos.

Cuando se cambia un texto que ya estaba vigente, se sube la `version` y se actualiza `vigente_desde`; el historial de
versiones queda en el historial de Git.

## 4. La revisión automática

Desde la carpeta `backend`:

```
python -m scripts.verificar_legal                    # revisa que cada archivo esté bien armado
python -m scripts.verificar_legal --exigir-vigentes  # además falla si alguno sigue «pendiente»
```

- La primera forma se puede usar siempre; las pruebas automáticas ya la incluyen.
- La segunda es la **puerta de la entrega**: el pipeline la corre solo cuando se sube una etiqueta de la versión
  final, por ejemplo `v1.0.0` (las etiquetas con guion, como `v1.0.0-rc.1`, son de prueba y no la exigen). Mientras
  falte un documento, esa etiqueta no pasa.

Ambas terminan con código 0 si todo está bien y con 1 si hay algo que arreglar, y dicen qué archivo y qué línea.

## 5. Cómo agregar otro documento

Hoy son ocho. Para sumar uno nuevo:

1. Crea su archivo en esta carpeta con el encabezado de la sección 2.
2. Agrega su nombre (el del archivo, sin `.md`) a `DOCUMENT_SLUGS` en `backend/services/legal_service.py`.
3. Agrégalo al contrato `docs/api/openapi.yaml`, en los tres lugares donde aparece la lista de nombres.
4. Corre las pruebas: si algo falta, dicen qué.

Solo se muestran los nombres de esa lista; ningún otro archivo de la carpeta sale al público (este `LEEME.md`
tampoco).

## 6. Qué no entra aquí

- Los documentos de la versión de venta, que se hacen para esa versión.
- Datos personales reales, claves o contraseñas: estos archivos son públicos y están en el repositorio.
- La pantalla «Acepto» ya existe: pide aceptar los términos, la política de datos y la autorización la primera vez que
  alguien entra y cada vez que la `version` de alguno de esos tres cambia. Por eso subir la `version` de uno de ellos
  hace que todas las personas deban aceptar de nuevo.
