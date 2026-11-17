# Pruebas de pantallas de la app (SCRUM-240)

Estas pruebas dibujan las pantallas de la app con **datos de mentira** (sin servidor y sin celular),
les sacan una foto y comprueban lo nuevo de la versión. Corren en el computador, dentro de GitHub
Actions, en el trabajo **«Pantallas (fotos de la app)»**.

## Qué se usa

- **Robolectric**: simula Android en el computador, así la app se dibuja sin celular ni emulador.
- **Compose Test**: encuentra los botones y los textos de la pantalla, los toca y escribe en ellos.
- **Roborazzi**: guarda la foto (captura de pantalla) de lo que se dibujó.

## Qué hay en esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `DatosDeMentira.kt` | Responde en lugar del servidor: un conjunto ficticio («Altos de DOMUX») con usuarios, PQRS, reservas, paquetes, visitas y vehículos. Todo es inventado. |
| `BaseDeFotos.kt` | Lo que comparten las pruebas: la sesión de cada rol, las mismas rutas de la app y cómo se dibuja y fotografía una pantalla. |
| `FotosDeCelularTest.kt` | Las pantallas de cada rol en un celular (411 × 891 dp). |
| `FotosDeTabletTest.kt` | Las pantallas principales en una tablet (1280 × 800 dp). |
| `FotosDeTextoGrandeTest.kt` | Pantallas con el tamaño de texto «Muy grande» de Preferencias. |
| `FotosLargasTest.kt` | Pantallas con listas largas, dibujadas enteras (de arriba a abajo). |
| `InteraccionesTest.kt` | Tocan la app como una persona: escribir en el buscador y abrir un resultado, abrir «+ Nuevo» y cambiar el tamaño del texto. |
| `NovedadesDeLaVersionTest.kt` | Comprueban la lógica de lo nuevo: qué crea cada rol con «+ Nuevo», qué lleva el menú de cada rol y a dónde lleva cada resultado del buscador. |

## Cómo se corren

- **En GitHub**: se corren solas con cada cambio. Las fotos quedan en la ejecución, en
  «Artifacts → fotos-de-pantallas-N» (se guardan 14 días).
- **Para verlas sin bajarlas**: en la pestaña Actions, «Run workflow» sobre la rama y marcar
  `ver_fotos`; las fotos salen impresas en pequeño en el registro del trabajo.
- **En un computador con Android Studio**: desde la carpeta `android`,
  `./gradlew :app:testProdDebugUnitTest -Proborazzi.test.record=true`; las fotos quedan en
  `android/app/build/fotos-de-pantallas/`.

## Cosas que conviene saber

- Lo único que cambió en el código de la app para poder probarla es que `RetrofitClient.api` y
  `RetrofitClient.structureApi` se pueden reemplazar desde las pruebas (`internal set`).
- Las dos ventanitas «Nueva torre» y «Nuevo apartamento» no se fotografían: dentro del simulador esas
  ventanas no dejan terminar la prueba. Se revisan a mano con las listas de chequeo.
- La fecha y la hora que se ven en algunas fotos son las del día en que corre la prueba, y el cursor
  de las cajas de texto puede aparecer o no: por eso las fotos no se comparan píxel por píxel.
