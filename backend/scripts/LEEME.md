# Copias de seguridad de la base de datos (TT-009)

Esta carpeta tiene dos programas que protegen los datos de DOMUX (residentes, visitas, reservas,
PQRS...). Úsalos desde la carpeta `backend`.

| Programa | Para qué sirve |
|---|---|
| `python -m scripts.copia_diaria` | Hace una copia de toda la base de datos y deja solo las **últimas 7**. |
| `python -m scripts.restaurar_copia` | Devuelve una copia a una base de datos (para recuperar datos o probar que la copia sirve). |

Palabras que se usan aquí:

- **Copia de seguridad** (o *backup*): un archivo `.dump` con todo el contenido de la base de datos en
  un momento exacto.
- **PostgreSQL**: el programa que guarda los datos. Estas copias son solo para PostgreSQL.
- **`pg_dump` y `pg_restore`**: los programas de PostgreSQL que hacen y leen la copia. Vienen con su instalador.
- **PATH**: la lista de carpetas donde Windows busca programas. Si `pg_dump` no está ahí, se indica su
  carpeta en `PG_BIN_DIR`.
- **Huella SHA-256**: un código de 64 letras y números calculado con el contenido del archivo. Si
  cambia un solo byte, la huella cambia. Sirve para saber que la copia no se dañó ni la tocaron.
- **Ficha**: el archivo `.dump.json` que se guarda junto a cada copia, con su huella y el número de
  filas de cada tabla.

## 1. Configuración (una sola vez)

Abre `backend/.env` (se crea copiando `.env.example`) y escribe estas líneas:

```
DATABASE_URL=postgresql://usuario:clave@localhost:5432/domux
BACKUP_DIR=E:\copias_domux
BACKUP_KEEP=7
PG_BIN_DIR=C:\Program Files\PostgreSQL\16\bin
```

- `BACKUP_DIR` es la carpeta de las copias. Para cumplir "fuera del computador", usa un **disco externo o USB**
  (aquí la `E:` es el USB). El programa se niega a usar una carpeta dentro del proyecto.
- `PG_BIN_DIR` solo hace falta si al probar sale el error "No encontré pg_dump". Cambia el `16` por la
  versión de tu PostgreSQL.
- `BACKUP_KEEP` es opcional (si falta, son 7).

## 2. Hacer la primera copia a mano

```
cd backend
venv\Scripts\python.exe -m scripts.copia_diaria
```

Si todo va bien, termina con un mensaje parecido a:

```
COPIA LISTA: domux_20261116_020000.dump (112.5 KB, 31 tablas, 36 filas). Huella SHA-256: 6277...
```

En la carpeta del USB quedan el archivo `.dump`, su ficha `.dump.json` y un `copias.log` con el historial.
Para ver las copias que hay y comprobar que ninguna está dañada:

```
venv\Scripts\python.exe -m scripts.copia_diaria --listar
```

## 3. Programarla todos los días en Windows

El archivo `scripts\copia_diaria.bat` ya trae lo necesario (busca el entorno `venv` y no lleva claves).

**Con el Programador de tareas** (lo más fácil):

1. Abre **Programador de tareas** desde el menú Inicio.
2. A la derecha, **Crear tarea básica...** y ponle el nombre `DOMUX copia diaria`.
3. Desencadenador: **Diariamente** y la hora (por ejemplo las 2:00 p. m., una hora en que el computador
   siempre esté encendido y el USB conectado).
4. Acción: **Iniciar un programa**. En *Programa o script* busca `backend\scripts\copia_diaria.bat`
   con el botón *Examinar*. Termina con **Finalizar**.
5. Haz doble clic en la tarea, ve a la pestaña **Configuración** y marca *Ejecutar la tarea lo antes posible
   después de un inicio programado omitido* (así, si el computador estaba apagado, la hace al encenderlo).
6. Para probarla ya mismo: clic derecho sobre la tarea > **Ejecutar**, y revisa que aparezca una copia nueva.

**Con una sola línea de comandos** (equivale a lo anterior, ejecutada en una consola normal):

```
schtasks /Create /TN "DOMUX copia diaria" /SC DAILY /ST 14:00 /TR "\"C:\ruta\a\domux\backend\scripts\copia_diaria.bat\""
schtasks /Run /TN "DOMUX copia diaria"
```

**En Linux o Mac** (cron), cada día a las 2:00 a. m.:

```
0 2 * * * cd /ruta/a/domux/backend && venv/bin/python -m scripts.copia_diaria
```

> Nota: la programación en Windows no se pudo probar desde donde se desarrolló el programa (solo se
> probó la copia y la restauración). La primera vez, revisa que de verdad aparezca la copia.

## 4. Revisar que sigue funcionando

- Cada vez que quieras, `python -m scripts.copia_diaria --listar` muestra las copias, su fecha, su tamaño y
  si están **íntegras**. Si la más nueva tiene 2 días o más, escribe un **AVISO** (la tarea dejó de funcionar o
  el USB no estaba conectado).
- Cada ejecución queda anotada en `copias.log`, en el USB y también en `backend\instance\copias.log`
  (este segundo queda aunque el USB no esté puesto, así se ve el error).
- El programa termina con código 1 cuando falla, para que el Programador de tareas lo marque como error.

## 5. Probar la restauración (esta es la prueba que se entrega como evidencia)

Restaurar **no toca** la base real: crea una base nueva llamada `<nombre>_restaurada`.

```
venv\Scripts\python.exe -m scripts.restaurar_copia --ultima
```

El programa revisa la huella, restaura, cuenta las filas de cada tabla y las compara con las que había al
hacer la copia. Debe terminar con:

```
RESTAURACIÓN CORRECTA: todas las tablas tienen las mismas filas que cuando se hizo la copia.
```

Toma una captura de la pantalla completa: es la evidencia. Para borrar la base de prueba cuando termines,
desde `psql` o pgAdmin: `DROP DATABASE domux_restaurada;`

## 6. Si de verdad se perdieron datos

1. **Apaga el servidor de DOMUX.**
2. Elige la copia: la más nueva (`--ultima`) o una anterior (`--archivo E:\copias_domux\domux_AAAAMMDD_HHMMSS.dump`).
3. Ejecuta, con el nombre de tu base real (el que sale al final de `DATABASE_URL`):

```
venv\Scripts\python.exe -m scripts.restaurar_copia --ultima --base domux --reemplazar
```

4. El programa pide **escribir el nombre de la base** para confirmar, borra la base dañada y deja la copia en su lugar.
   Lo que se guardó después de la copia se pierde.
5. Vuelve a encender el servidor y revisa que los datos estén.

## 7. Cuidados importantes

- **La copia contiene datos reales** de los residentes y las contraseñas protegidas (hash). La carpeta debe
  ser solo tuya. Nunca la subas a GitHub, a un grupo de WhatsApp ni a una nube compartida. (El repositorio
  ignora los archivos `.dump`, pero no dependas de eso.) Cifrar las copias queda para la versión completa.
- No es lo mismo que el **Respaldo legal** de la página web (el Excel de la administración): ese exporta
  datos para entregarlos y no sirve para recuperar el sistema.
- No ejecutes dos copias al mismo tiempo.
- La base gratuita de Render **no hace copias** y se borra a los 30 días: estas copias son para la base
  PostgreSQL de la entrega local.

## Cómo está hecho

| Archivo | Qué contiene |
|---|---|
| `copias_comun.py` | Lo que usan los dos programas: leer la configuración, buscar `pg_dump`, huella, fichas y borrado de copias viejas. |
| `copia_diaria.py` | Hace la copia en un archivo temporal, la revisa con `pg_restore --list`, le calcula la huella y solo entonces le da su nombre final y borra las sobrantes. Si algo falla, no se borra ninguna copia buena. |
| `restaurar_copia.py` | Revisa la huella, crea la base nueva, restaura y compara las filas. |
| `copia_diaria.bat` | Atajo para el Programador de tareas de Windows. |
| `tests/test_db_backup.py` | Pruebas automáticas (con un PostgreSQL de mentira y, si hay servidor, con uno de verdad). |
