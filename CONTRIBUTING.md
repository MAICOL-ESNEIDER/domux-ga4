# Guía para colaborar en DOMUX

Estas son las reglas del equipo (Maicol, Sebastián y Nicolás) para trabajar juntos en el repositorio. Siguen la
*Guía de Estructura y Evidencias del Repositorio* del SENA (secciones 3, 6 y 7) y las decisiones del proyecto
(DEC-062 sobre los commits y DEC-107 sobre las pruebas). Si algo de esta guía no sirve en la práctica, se cambia aquí con un pull request, no se ignora.

Palabras que se usan:

- **Rama (branch):** una línea de trabajo separada. Los cambios nuevos se hacen en una rama y no en la principal.
- **Commit:** un cambio guardado en el historial, con un mensaje que dice qué se hizo.
- **Pull request (PR):** la solicitud para unir una rama a otra. En él se explica el cambio y otra persona lo revisa.
- **Pipeline (CI):** las pruebas automáticas que GitHub corre en cada cambio (archivo `.github/workflows/ci.yml`).
- **Jira / clave:** cada trabajo tiene una clave, por ejemplo `SCRUM-202`, que se escribe en la rama, el commit y el PR.

## 1. Cómo está organizado el repositorio

| Ruta | Qué va ahí | Qué NO va |
|---|---|---|
| `backend/` | El servidor (Flask y PostgreSQL) y la página web de administración | Secretos, copias de la base, archivos temporales |
| `backend/routes/` | La API REST: recibe la petición y responde (sin reglas de negocio) | Consultas y reglas largas |
| `backend/services/` | Las reglas de negocio (PQRS, reservas, visitas, paquetes...) | Código de pantallas |
| `backend/web/` | La página de administración (`templates/` con Jinja2, `static/` con estilos, scripts y logo) | Librerías externas copiadas |
| `backend/migrations/` | Los cambios de la base de datos (Alembic), uno por archivo: `NNNN_descripcion_en_español.py` | SQL manual sin control |
| `backend/scripts/` | Programas de operación: copia de seguridad y restauración (ver su `LEEME.md`) | Programas que borran datos sin avisar |
| `backend/tests/` | Pruebas automáticas, un archivo `test_<tema>.py` por tema | Evidencia manual sin contexto |
| `android/` | La app Android (Kotlin, Jetpack Compose, MVVM) | `local.properties` ni `google-services.json` |
| `android/app/src/main/java/com/dracknoval/domux/` | Pantallas (`XxxScreen.kt`), su estado (`XxxViewModel.kt`), `data/` (llamadas a la API) y `ui/` (tema) | Lógica del servidor |
| `.github/` | El pipeline y la plantilla de pull request | Tokens |
| `Documentacion_Proyecto_ADSO/` y `docs/` | La documentación del proyecto, las decisiones (ADR), la API y las evidencias | Copias viejas sin versión |
| Raíz | `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `.gitignore`, `render.yaml` | Código |

## 2. Nombres y comentarios

- **Python:** estilo PEP 8 (lo revisa Ruff). Archivos y funciones en `snake_case`, clases en `PascalCase`.
  Las pruebas se llaman `test_<tema>.py`.
- **Kotlin:** clases y pantallas en `PascalCase` (`PqrsScreen`), funciones y variables en `camelCase`. Cada pantalla
  tiene su `ViewModel` (`PqrsViewModel`). Los iconos son `ic_<nombre>.xml` en `res/drawable`.
- **Base de datos:** tablas y columnas en inglés y `snake_case` (como el resto del modelo). Toda modificación va en una
  migración nueva; nunca se edita una migración que ya se subió.
- **Comentarios:** en español, claros para quien llega nuevo. Explican **para qué** sirve el código, no solo qué hace.
  En Python, con *docstrings*; en Kotlin, con KDoc.
- **Textos que ve el usuario:** en español sencillo (sin siglas sin explicar).

## 3. Ramas (Git Flow ligero)

| Rama | Para qué | Sale de | Se une a |
|---|---|---|---|
| `main` | Versiones **entregadas**, cada una con su etiqueta (`v1.0.0`) | `release/*` o `hotfix/*` | — |
| `develop` | Integración de la versión completa (después de la entrega) | `release/*` o `hotfix/*` | `release/*` |
| `release/v1.0-reducida` | Línea de integración de la versión reducida (entrega del 1 de diciembre de 2026) | ya existe | `main` y `develop`, solo al entregar |
| `feature/SCRUM-<n>-<nombre-corto>` | Una necesidad completa: **una historia (HU) o una tarea técnica (TT) por rama**, no un detalle suelto | la rama de integración | la rama de integración |
| `fix/SCRUM-<n>-<nombre-corto>` | Corrección no urgente (con una prueba que evite que vuelva el error) | la rama de integración | la rama de integración |
| `hotfix/<nombre>` | Corrección **urgente** de algo ya entregado | `main` | `main` y `develop` |
| `docs/<nombre>` | Solo documentación, sin tocar código | la rama de integración | la rama de integración |

Reglas:

1. **Nadie sube directamente a `main`, `develop` ni `release/*`.** Todo entra con un pull request.
2. Un PR se une solo con el **pipeline en verde**: servidor con SQLite, servidor con PostgreSQL (cobertura mínima de
   70 %) y la app Android.
3. Se une con un **commit de unión (merge commit)**: así se conserva el historial. **No se reescribe el historial**
   (nada de `push --force`, `rebase` de ramas compartidas ni `commit --amend` de algo ya subido): DEC-062.
4. Antes de abrir el PR, se trae lo último de la rama de integración a tu rama y se resuelven los choques ahí.
5. Las ramas viejas no se borran mientras sirvan de evidencia.
6. Las etiquetas (`v1.0.0-rc.1`, `v1.0.0`) y las uniones a `main` y `develop` las hace el líder del proyecto cuando
   el equipo lo decide, no antes.

## 4. Commits

El mensaje va **en español**, con palabras normales y con la clave de Jira:

```
tipo(SCRUM-<n>): qué se hizo, en una frase que se entienda
```

| Tipo | Uso | Ejemplo |
|---|---|---|
| `feat` | Una capacidad nueva | `feat(SCRUM-151): registrar cuartos útiles` |
| `fix` | Corregir un error | `fix(SCRUM-123): rechazar el código de recogida vencido` |
| `docs` | Documentación | `docs(SCRUM-227): licencia del proyecto y avisos de terceros` |
| `test` | Pruebas | `test(SCRUM-123): cubrir reservas que se cruzan` |
| `refactor` | Ordenar el código sin cambiar lo que hace | `refactor(SCRUM-123): separar las reglas de PQRS` |
| `chore` | Mantenimiento | `chore(SCRUM-123): fijar las versiones de las librerías` |
| `ci` | El pipeline | `ci(SCRUM-123): sumar la revisión de seguridad de librerías` |

Las claves `SCRUM-123` de los ejemplos son inventadas; las reales salen de Jira.

- Un commit = un cambio con sentido completo. Mejor varios commits pequeños que uno gigante.
- Si hace falta explicar el **por qué**, se escribe en el cuerpo del mensaje, después de una línea en blanco.
- Cada persona hace sus commits con **su propia identidad de GitHub** (`git config user.name` y `user.email`), para que
  la contribución de cada quien se vea en el historial.
- Nunca se suben secretos (ver la sección 6).

## 5. Pull request y revisión

1. Abre el PR con el título en el mismo formato del commit (`feat(SCRUM-202): ...`). La plantilla trae los campos que pide
   la guía del SENA: resumen, requisito relacionado, tipo de cambio, pruebas, evidencia, riesgos, migraciones y lista de revisión.
2. Lo ideal es que lo revise **otra persona del equipo**. Si nadie puede revisar a tiempo, quien lo escribió lo revisa
   con la lista de abajo y lo deja anotado en el PR.
3. Cuando se une, la evidencia (el enlace al commit o al PR) se pega en la tarea de Jira.

### Lista de revisión antes de unir una rama

Es la "definición de listo" del equipo. Todo lo que aplique debe estar marcado:

- [ ] Se cumplen los criterios de aceptación de la historia o la tarea.
- [ ] El pipeline está en verde (servidor con SQLite, servidor con PostgreSQL y app Android).
- [ ] Hay pruebas nuevas o actualizadas para lo que cambió, y la cobertura sigue en 70 % o más.
- [ ] Ruff no marca errores: `ruff check . --select F,E9 --exclude migrations`.
- [ ] No hay secretos ni datos personales en el cambio (ver la sección 6).
- [ ] Si el cambio tocó la base de datos, hay una migración nueva y se probó en SQLite y en PostgreSQL.
- [ ] Si hay una variable de entorno nueva, está en `backend/.env.example` con una explicación.
- [ ] Si hay una ruta de la API nueva, está documentada y registrada en las pruebas de permisos
  (`tests/test_route_guards.py`).
- [ ] Si el cambio se ve en la app, se probó en un celular con el APK que arma el pipeline.
- [ ] El `CHANGELOG.md` y la documentación afectada están al día.
- [ ] Las limitaciones o la deuda que quedan están anotadas.

## 6. Qué nunca se sube al repositorio

El repositorio es **público**. Nunca se suben:

- Archivos `.env` reales, contraseñas, llaves, tokens ni certificados.
- `google-services.json` ni la clave de la cuenta de servicio de Firebase.
- Copias de la base de datos (`*.dump`) ni cualquier archivo con datos reales de residentes.
- Registros (logs) con datos personales.
- Compilaciones ni dependencias que se vuelven a generar (`build/`, `venv/`).

Si un secreto se sube por error, se **cambia de inmediato** (no basta con borrarlo) y se avisa al equipo.
Las claves de la demostración se escriben en `.env`, que está en `.gitignore`.

## 7. Cómo probar en el computador

Desde la carpeta `backend` y con el entorno virtual activado:

```
pip install -r requirements-dev.txt
python -m unittest discover -s tests                      # pruebas con SQLite (en memoria)
ruff check . --select F,E9 --exclude migrations           # errores de código
coverage run -m unittest discover -s tests && coverage report   # cobertura (mínimo 70 %)
pip-audit -r requirements.txt                             # librerías con fallas conocidas
```

Para repetir las pruebas con PostgreSQL, se crea una base vacía (por ejemplo `domux_pruebas`) y se indica con
`TEST_DATABASE_URL`:

```
# Linux / macOS
TEST_DATABASE_URL=postgresql://usuario@localhost:5432/domux_pruebas python -m unittest discover -s tests
# Windows (PowerShell)
$env:TEST_DATABASE_URL = "postgresql://usuario@localhost:5432/domux_pruebas"; python -m unittest discover -s tests
```

La app Android se compila desde Android Studio o, como lo hace el pipeline, con `./gradlew :app:assembleProdDebug`
dentro de la carpeta `android`.

## 8. Versiones y registro de cambios

- Las versiones siguen **SemVer** (`1.0.0`) y su etiqueta en Git es `v1.0.0`.
- Cada cambio que el usuario puede notar se anota en `CHANGELOG.md`, bajo `[Sin publicar]`, en una de estas
  categorías: *Añadido, Cambiado, Obsoleto, Eliminado, Corregido, Seguridad*.
- Antes de entregar una versión, `[Sin publicar]` pasa a llevar el número de la versión y la fecha.

## 9. Uso de inteligencia artificial

Usar herramientas de IA es válido, pero cada integrante es responsable de **entender, probar y poder sustentar** lo
que entrega. El uso de IA se declara en el informe de cierre (qué se usó, en qué partes y cómo se revisó).
