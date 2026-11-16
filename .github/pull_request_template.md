<!--
  Plantilla de pull request de DOMUX (TT-015). Sigue la sección 6.3 de la Guía de Estructura y Evidencias del SENA.
  Borra los comentarios como este y deja cada campo lleno (si no aplica, escribe "No aplica" y por qué).
  Título del PR: igual que un commit, en español y con la clave de Jira, por ejemplo: feat(SCRUM-202): descripción
-->

## Resumen

<!-- Qué cambia y por qué, en pocas líneas y con palabras sencillas. -->

## Requisito relacionado

<!-- Clave de Jira y requisito: HU, RF, RNF, incidencia o tarea técnica. Ejemplo: SCRUM-202 (TT-009) · RNF de respaldo -->

- Jira:
- Requisito:

## Tipo de cambio

- [ ] Funcional (capacidad nueva)
- [ ] Corrección de un error
- [ ] Técnico (orden del código, infraestructura, pruebas)
- [ ] Documental

## Pruebas

<!-- Los comandos que corriste y su resultado. Ejemplo: `python -m unittest discover -s tests` → OK (N pruebas). -->

- Servidor con SQLite:
- Servidor con PostgreSQL:
- App Android / prueba en celular:

## Capturas o evidencia

<!-- Obligatorio si el cambio se ve en la app o en la web: capturas, video o enlace al resultado. Si no se ve, escribe "No aplica". -->

## Riesgos y compatibilidad

<!-- Qué puede salir mal, qué otras partes toca y si cambia algo que ya funcionaba (API, base de datos, app instalada). -->

## Migraciones

- [ ] No hay cambios en la base de datos
- [ ] Sí hay migración (número y nombre del archivo, y cómo se aplica / se deshace):

## Lista de revisión

- [ ] Se cumplen los criterios de aceptación
- [ ] El pipeline está en verde (SQLite, PostgreSQL y app Android) y la cobertura sigue en 70 % o más
- [ ] Ruff no marca errores (`ruff check . --select F,E9 --exclude migrations`)
- [ ] Hay pruebas nuevas o actualizadas
- [ ] No hay secretos, claves ni datos personales en el cambio
- [ ] Las variables nuevas están en `backend/.env.example`
- [ ] Las rutas nuevas de la API están documentadas y en `tests/test_route_guards.py`
- [ ] `CHANGELOG.md` y la documentación afectada están al día
- [ ] Las limitaciones o la deuda que quedan están anotadas
