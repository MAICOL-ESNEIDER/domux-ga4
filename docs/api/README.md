# Contrato de la API de DOMUX

Esta carpeta tiene el **contrato de la API**: un archivo que describe, sin ambigüedades, todo lo que el servidor
de DOMUX sabe hacer. Lo usan la app Android, la web de administración y cualquier persona que quiera
conectarse al servidor.

| Archivo | Qué es |
|---|---|
| `openapi.yaml` | El contrato en formato **OpenAPI 3.0** (un estándar para describir APIs, escrito en YAML, un formato de texto parecido a una lista con sangrías) |

## Qué dice el contrato

- Las **127 operaciones** de la API (94 direcciones, cada una con sus métodos GET, POST, PUT o DELETE).
- Quién puede usar cada una (`x-roles`: `ADMIN`, `GUARD` o `RESIDENT`) y que todas piden sesión menos
  `GET /api/health`, `POST /api/auth/login` y los dos documentos legales (`GET /api/legal` y
  `GET /api/legal/{slug}`), que se leen antes de iniciar sesión.
- Los datos que recibe cada operación (cuerpo, parámetros de la dirección y de la consulta) y los que devuelve, con
  sus tipos, límites y valores permitidos.
- Los **errores**: los códigos que usa el servidor, su forma `{ "error": "...", "status": 400 }` y en qué rutas
  puede aparecer cada uno (es el catálogo de errores del proyecto).
- Las reglas que se repiten: formato de fechas (hora de Colombia), paginación, la vista liviana `view=summary`,
  adjuntos y bloqueos por intentos fallidos. Están al comienzo del archivo, en `info.description`.

No incluye la web de administración (`/web/...`): son páginas HTML para un navegador, no una API.

## Cómo verlo

El archivo se puede leer como texto, pero se entiende mejor en un visor de OpenAPI:

- En Visual Studio Code, con la extensión «OpenAPI (Swagger) Editor».
- En el navegador, abriendo el archivo en el editor de Swagger (`editor.swagger.io`). El contrato no tiene
  claves ni datos privados, así que se puede pegar ahí sin problema.

## Cómo se mantiene al día

El contrato solo sirve si dice lo mismo que el servidor. Por eso lo vigila una prueba automática,
`backend/tests/test_api_contract.py`, que corre en cada cambio (y en el pipeline) y comprueba dos cosas:

1. **La forma:** que el contrato tenga exactamente las rutas del servidor, con los mismos métodos, parámetros,
   roles y exigencia de sesión que el código. Si agregas una ruta y no la anotas, la prueba falla y dice cuál es.
2. **El contenido:** hace un recorrido real por la API y comprueba que cada respuesta (y cada cuerpo que se
   envía) cumpla los esquemas del contrato. Si el servidor agrega, quita o cambia un dato y el contrato no se
   actualiza, también falla.

Para correrla (desde la carpeta `backend`, con el entorno virtual activo):

```
python -m unittest discover -s tests -p "test_api_contract.py"
```

### Qué hacer cuando cambias la API

1. Haz el cambio en el servidor (ruta, datos de entrada o de salida).
2. Edita `docs/api/openapi.yaml` para que diga lo nuevo: la operación en `paths` y, si cambió un dato, su esquema
   en `components/schemas`.
3. Corre la prueba de arriba. Si algo no coincide, el mensaje dice cuál ruta y cuál dato.
4. Si la ruta es nueva, agrégala también al recorrido de `test_api_contract.py` (la prueba avisa si una operación
   del contrato quedó sin probar).

### Lo que la prueba no alcanza a verificar

Los errores que la prueba provoca a propósito son el 400, 401, 403, 404, 405, 409, 413 y 429 (el 405 y el 404 de una
dirección que no existe, en una prueba aparte). Los demás códigos de error que el contrato anota en cada ruta, y el
500 (falla interna), salen de leer el código del servidor: se revisan a mano al hacer cambios.

## Versión

`info.version` del contrato sigue la versión del producto (hoy, la candidata a la versión reducida 1.0). Se
actualiza cuando se publica una versión nueva, junto con el `CHANGELOG.md`.
