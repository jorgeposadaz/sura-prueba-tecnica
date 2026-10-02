# Prueba Técnica — Analista de Datos y Analítica

**Candidato:** Jorge Mario Zapata Posada
**Cargo:** Analista de Datos y Analítica
**Empresa:** Sura

Este repositorio contiene la entrega de la prueba técnica: Las Secciones
Sección 3 (Python: automatización y validación de calidad del dato) y
Sección 4 (Tablero ligero en HTML u otra herramienta sin licencia)
como código ejecutable, y las Secciones 1, 2, 5 y 6 como documento
adjunto con las respuestas escritas.

## Estructura del repositorio

```text
/sura-prueba-tecnica
├── README.md
├── seccion_2/
│ ├── query_2_2.sql
│ └── query_2_3.sql
├── seccion_3/
│ ├── data_quality_validator.py
│ ├── requirements.txt
│ └── output/ (se genera al ejecutar el script)
├── seccion_4/
│ └── dashboard_monitoreo_operativo.html
└── sura_prueba_tecnica_respuestas.pdf (Secciones 1, 2, 5 y 6)
```

## Sección 3 — Validación de calidad del dato (Python)

### Descripción

Script que valida la calidad de un archivo de facturación antes de que entre
al pipeline, simulando el proceso de validación automática que correría con
cada carga nueva. Aplica 5 reglas de calidad (Completitud, Validez, Unicidad,
Consistencia, Oportunidad), genera un reporte de calidad en JSON, y separa
los registros válidos (Parquet) de los rechazados (Excel, con la razón de
rechazo).

### Instalación

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux
pip install -r seccion_3/requirements.txt
```

### Ejecución

**Opción A — con datos de prueba generados automáticamente** (incluye
intencionalmente los 4 problemas pedidos: formatos de ID inconsistentes,
períodos en distintos formatos de fecha, valores negativos/nulos, y
duplicados por cliente + período):

```bash
python seccion_3/data_quality_validator.py
```

**Opción B — validando un archivo de facturación real**, con columnas
`id_cliente`, `periodo`, `trabajadores_activos`, `valor_contrato`:

```bash
python seccion_3/data_quality_validator.py --input ruta/a/tu_archivo.csv
```

### Solución de problemas

**Error: "An Application Control policy has blocked this file" (Windows)**

Este error proviene de una política de seguridad de Windows (Smart App Control
u otra política de control de aplicaciones) que bloquea la carga de archivos
binarios compilados recién instalados vía `pip`, no de un error en el código
ni en las dependencias — el problema persiste incluso fijando versiones
maduras y ampliamente usadas de cada librería.

Alternativas, en orden de preferencia:
1. Si ya tiene conda/Miniconda instalado, cree el entorno con conda en lugar
   de venv:
```bash
conda create -n sura_prueba python=3.11 -y
conda activate sura_prueba
pip install -r seccion_3/requirements.txt
```
2. Ejecute el script dentro de WSL (Windows Subsystem for Linux), que
   proporciona un entorno Linux independiente de las políticas de ejecución de
   aplicaciones de Windows.
   Si WSL no está instalado puede instalarse desde PowerShell con:
```powershell
wsl --install
```
  Después de reiniciar el equipo, abra Ubuntu desde el menú Inicio y, dentro de
  WSL, ubíquese en el directorio del repositorio. Por ejemplo, si el repositorio
  se encuentra en C:\Users\<usuario>\Documents\sura_prueba:
```bash
cd /mnt/c/Users/<usuario>/Documents/sura_prueba
```
  A continuación, cree un entorno virtual e instale las dependencias:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r seccion_3/requirements.txt
```
  Finalmente, ejecute el script desde WSL:
```bash
python seccion_3/data_quality_validator.py
```

### Salidas

Todas se generan en `seccion_3/output/`:

| Archivo | Contenido |
|---|---|
| `facturacion_raw.csv` | Archivo de prueba generado (solo si no se usó `--input`) |
| `facturacion_validos.parquet` | Registros que pasaron las 5 reglas de calidad |
| `facturacion_rechazados.xlsx` | Registros rechazados, con columna `razon_rechazo` |
| `reporte_calidad.json` | Score por dimensión, total de registros, válidos y rechazados por regla |

El reporte de calidad también se imprime en consola al finalizar la ejecución.

### Decisiones de diseño relevantes

- Los campos `id_cliente` y `periodo` se normalizan antes de evaluarse,
  aceptando las variantes de formato típicas de una fuente heredada (prefijos,
  espacios, ceros a la izquierda, distintos formatos de fecha).
- La detección de duplicados se hace sobre los valores ya normalizados, no
  sobre el texto crudo, para capturar casos donde el mismo cliente llega con
  un formato de ID distinto entre cargas.
- Un registro puede fallar varias reglas simultáneamente; la columna
  `razon_rechazo` las lista todas, separadas por `;`.
- Tiempo de ejecución: menos de 1 segundo con el volumen de prueba generado.

## Sección 4 — Tablero de monitoreo operativo (HTML)

### Ejecución

1. Clonar o descargar este repositorio.
2. Abrir `seccion_4/dashboard_monitoreo_operativo.html` directamente con doble
   clic (se abre en el navegador predeterminado).
3. (Opcional, solo si el navegador restringe la carga del CDN desde un
   archivo local) servir la carpeta con un servidor estático simple:
   `python -m http.server` desde `seccion_4/`, y abrir `localhost:8000`.

### Contenido del tablero

- 3 KPIs (total de casos, costo total, tasa de incidencia) con variación
  vs. el mes anterior.
- Tendencia de los últimos 12 meses con línea de referencia del promedio
  histórico.
- Top 10 clientes con más casos, con su clase de riesgo visible.
- Distribución de casos por tipo (leve/grave) y por clase de riesgo (1-5).
- Filtro por clase de riesgo (selección múltiple), que recalcula todas las
  visualizaciones, no solo las oculta.

Los datos se generan programáticamente en el navegador al cargar la página
(con semilla fija, para que los resultados sean reproducibles entre cargas),
sin depender de ningún archivo externo.

### Herramienta elegida y por qué

Se eligió HTML + JavaScript puro (sin frameworks ni librerías con licencia),
usando Chart.js (MIT, cargado vía CDN) solo para el renderizado de gráficos.
La razón: el criterio de esta sección es que un coordinador pueda usar el
tablero "el lunes sin que nadie se lo explique". Un archivo HTML autocontenido
se abre con doble clic en cualquier navegador, sin instalar Python ni depender
de un servidor activo (a diferencia de Streamlit o Dash), lo que minimiza la
fricción tanto para el usuario final como para quien evalúa esta entrega.

### Cómo conectaría este tablero a datos reales de un Lakehouse en producción

Mantendría la página como un archivo estático y liviano, sin backend propio:
un pipeline (notebook o Dataflow en Fabric) correría periódicamente sobre el
Lakehouse, calcularía las mismas agregaciones que hoy genera el JavaScript
(serie mensual, KPIs, top 10, distribuciones) y las publicaría como un
archivo JSON pequeño en un storage accesible (por ejemplo, un contenedor de
Blob Storage con lectura pública dentro de la red corporativa). El tablero,
en lugar de generar datos sintéticos, haría un `fetch()` a ese JSON al
cargar la página. Esto mantiene la filosofía "sin licencia y sin servidor"
del tablero, mientras el trabajo pesado (leer y agregar datos del Lakehouse)
sigue corriendo donde corresponde: en la capa de datos, no en el navegador.