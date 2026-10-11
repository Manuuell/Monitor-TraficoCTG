# Revisión y pruebas locales — 10 de octubre de 2026

El dashboard está ejecutándose en http://127.0.0.1:8502, accesible únicamente desde este equipo. La revisión no aplicó correcciones al código del producto. Los archivos de esta carpeta contienen las pruebas y sus evidencias.

## Resultado

- **13 pruebas de lógica e integración: 8 pasaron y 5 fallaron.** Los cinco fallos son reproducibles y están detallados abajo.
- **16 escenarios de interfaz con Streamlit AppTest: todos pasaron**, sin excepciones de ejecución. Incluyen comprobaciones de mensajes y estados esperados.
- **9 combinaciones de filtros PostgreSQL/pandas coinciden**, con tolerancia numérica de 1e-10. Estas combinaciones forman parte de una de las 13 pruebas de integración.
- **18 archivos Python y 9 celdas de código del notebook** pasan el análisis de sintaxis.
- **Las 9 celdas del notebook se ejecutaron correctamente** contra la base local, sin guardar cambios en el notebook. Tras el filtro de confianza, analiza 359.664 observaciones de 113 nodos.
- **Navegador real:** carga de mapas, selección de septiembre, cálculo de ruta, capa oscura, histórico, generación y descarga del reporte HTML verificados.
- **HTTP:** `/_stcore/health` respondió `ok`.

Pasar las pruebas de interfaz significa que esos flujos se ejecutan y producen los estados comprobados; no elimina los defectos de integridad de datos y trazado identificados por las pruebas de lógica.

## Fallos confirmados

### 1. P1 — Cambio incompatible de columnas en Google Sheets

Ubicación: [descargar_trafico.py](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/src/descargar_trafico.py:257>).

`llave_id` se introduce antes de `error_msg`. `asegurar_encabezados()` sustituye la fila de encabezados al detectar más columnas, pero no migra las filas históricas. La prueba usa el escritor real con un servicio Google simulado: un valor que pertenecía a `fecha` se vuelve a leer como `velocidad_ratio`.

Consecuencia: al desplegar el nuevo ETL sobre un libro con el esquema anterior, métricas y campos temporales del histórico quedan interpretados bajo encabezados equivocados. Esto demuestra el defecto del cambio; no afirma que ya se haya alterado el libro de producción.

Corrección propuesta: conservar el orden anterior y añadir la columna al final, o implementar una migración explícita y verificada. Considerar también los CSV antiguos que procesa el backfill.

### 2. P2 — La rotación abandona un nodo antes de agotar las alternativas

Ubicación: [descargar_trafico.py](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/src/descargar_trafico.py:224>).

Con A y C agotadas y B funcional, la secuencia fue A, C, C, B, B. El primer nodo quedó fallido, aunque B podía resolverlo. Solo se reintenta una vez por nodo y el fallo de ese segundo intento no se clasifica inmediatamente.

Corrección propuesta: probar las llaves disponibles en un bucle acotado para el mismo nodo y clasificar cada respuesta, sin repetir indefinidamente llaves agotadas.

### 3. P2 — Registrar consumo rehabilita una llave que acaba de agotarse

Ubicación: [rotacion_llaves.py](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/src/rotacion_llaves.py:179>).

La llave A responde correctamente una vez y luego devuelve `InsufficientFunds`. Al cerrar la corrida, `registrar_consumo()` vuelve a poner `agotada=False` por sus éxitos anteriores. La prueba comprueba directamente el archivo temporal de estado.

Corrección propuesta: separar el conteo acumulado del estado de disponibilidad y respetar el orden temporal entre éxito y descarte.

### 4. P2 — La geometría de vuelta se obtiene invirtiendo la ida

Ubicación: [red_nodos.py](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/dashboard/red_nodos.py:145>).

El JSON almacena un solo `path`. `_trazo()` lo invierte para viajar en sentido contrario. La conexión AER_CRE–TUN_CRE tiene 7.939 m en un sentido y 1.616 m en el otro, pero reutiliza la misma geometría. Hay 155 conexiones guardadas con una diferencia de distancias superior a 400 m; esto señala la extensión de la asimetría, sin afirmar que todas tengan exactamente el mismo problema vial.

Corrección propuesta: capturar la geometría de cada sentido, guardarlas separadamente y seleccionar la que corresponde a cada tramo. El cálculo de Dijkstra sí usa las distancias específicas de cada dirección.

### 5. P2 — Fallar toda la captura devuelve éxito al sistema

Ubicación: [descargar_trafico.py](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/src/descargar_trafico.py:360>).

Con todas las respuestas simuladas en HTTP 403, `main()` devuelve 0. El JSONL registra el error, pero cron y los procesos que comprueban el código de salida ven éxito.

**Es preexistente:** el mismo `return 0` está en HEAD, antes de los cambios locales.

Corrección propuesta: devolver un código distinto de cero si ninguna consulta tiene éxito; definir explícitamente el resultado deseado ante fallos parciales.

## Interfaz y operación

- En la ventana inspeccionada, de aproximadamente 897 píxeles de ancho, la barra lateral más las columnas `[1, 3]` dejan el panel de filtros demasiado estrecho. Los selectores y las fechas se truncan y «Restablecer filtros» se divide en varias líneas. Se observa en la captura. Revisar el ancho mínimo o apilar filtros y mapa en ventanas estrechas. Referencias: [mapa](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/dashboard/monitor.py:1228>) y [red](</Users/manuelesteban/Library/Mobile Documents/com~apple~CloudDocs/proyectos/proyect_r/dashboard/monitor.py:1315>).
- La base PostgreSQL local contiene **382.392 filas**, del **30/05/2026 al 30/09/2026**. El navegador obtuvo un snapshot posterior desde Sheets: **10/10/2026 a las 11:00, 113 nodos**. Es una mezcla de fuentes prevista por el fallback; el histórico local no incluye octubre.
- En septiembre el mapa mostró **81.359 mediciones válidas** de 113 nodos. El histórico del 23 al 30 de septiembre mostró **22.374 registros y 198 ejecuciones**.
- La ruta Aeropuerto → Túnel de Crespo produjo **5,8 km, 8,8 minutos y 3 nodos** con el snapshot utilizado. Son resultados de esa prueba, no una estimación permanente.
- El libro resuelto por la configuración local informó **9.998.810 de 10.000.000 celdas**. No se verificó el puntero de rotación de los VPS remotos, por lo que no se concluye que ese sea su libro actualmente activo.
- La captura de red contiene **88 conexiones señaladas para revisión** por discrepancias entre TomTom y OSRM. Las pruebas comprueban estructura, correspondencia con los nodos activos y renderizado; no certifican el sentido real de cada calle.
- `PROYECT_1.R` solo cambia finales de línea; no tiene cambios semánticos respecto a HEAD.
- El notebook identifica supuestos tramos compartidos por coincidencia de estadísticas redondeadas. Su ejecución correcta no demuestra identidad de segmentos viales. Conviene validar esos grupos con identificadores o geometrías antes de eliminar consultas por considerarlas redundantes.

## Cobertura de interfaz

Carga inicial; septiembre; franja AM; horas personalizadas; lunes; nodo individual; velocidad actual; velocidad libre; mes sin datos; restablecimiento; ruta origen–destino; origen igual a destino; ruta sin observaciones; corredores vacíos; fechas históricas invertidas; generación del reporte HTML.

AppTest usa observaciones históricas reales y simula los accesos a Google y el snapshot reciente para que los escenarios sean reproducibles. El navegador ejecuta el dashboard normal y sí realizó lecturas reales de Sheets. Las consultas PostgreSQL de pruebas y del servidor se configuraron con `default_transaction_read_only=on`, comprobado con SQL.

## Límites de la verificación

No se ejecutó el ETL contra TomTom ni se recapturó la red. Las respuestas del ETL se simularon y sus archivos se escribieron en directorios temporales. No se hicieron escrituras de mediciones en Sheets, Drive, PostgreSQL o Firestore. No se probaron despliegues remotos, cron, restauración de backups, fotos Street View ni concurrencia de los dos VPS. Las comprobaciones visuales se limitaron al tamaño actual del navegador.

## Reproducir

Desde la raíz del proyecto, con PostgreSQL local disponible:

```sh
venv/bin/python reports/revision_2026-10-10/checks.py
venv/bin/python reports/revision_2026-10-10/ui_checks.py
```

El primer comando **debe terminar con cinco fallos** mientras sigan presentes los defectos descritos. No son pruebas marcadas como éxito esperado. Los scripts configuran el usuario local `manuelesteban` y la base `trafico`; ajustar esos parámetros si se ejecutan en otro equipo.

Servidor usado:

```sh
env FUENTE_DASHBOARD=db DB_HOST=127.0.0.1 DB_USER=manuelesteban DB_NAME=trafico PGOPTIONS='-c default_transaction_read_only=on' TZ=America/Bogota SUBIR_A_GOOGLE=false SUBIR_A_FIRESTORE=false GUARDAR_EN_DB=false venv/bin/python -m streamlit run dashboard/monitor.py --server.address 127.0.0.1 --server.port 8502 --server.headless true
```

`results.json` y `ui_results.json` conservan los resultados estructurados. `reporte_historico.html` es la descarga verificada desde el navegador y contiene dos gráficos Plotly y la tabla de franjas. `dashboard-local.jpg` conserva la vista probada.
