"""
data_quality_validator.py

Valida la calidad del archivo de facturación antes de que entre al pipeline.
Simula el proceso de validación que correría automáticamente con cada carga
nueva, antes de que el dato llegue al modelo semántico / tablero ejecutivo.

Prueba técnica - Analista de Datos y Analítica - Sección 3, Ejercicio 3.1

Uso:
    python data_quality_validator.py
        Genera un archivo de prueba (1,000+ registros con problemas
        intencionales) y lo valida.

    python data_quality_validator.py --input ruta/a/facturacion.csv
        Valida un archivo de facturación real en lugar de generar uno de
        prueba. El archivo debe tener las columnas:
        id_cliente, periodo, trabajadores_activos, valor_contrato.

Salidas (en ./output/):
    facturacion_raw.csv            Archivo de prueba generado (solo si no
                                    se pasó --input).
    facturacion_validos.parquet    Registros que pasaron las 5 reglas.
    facturacion_rechazados.xlsx    Registros rechazados, con la razón.
    reporte_calidad.json           Score por dimensión y totales.

Autor: Jorge
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Configuración general
# --------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("data_quality_validator")

OUTPUT_DIR = Path(__file__).parent / "output"
RAW_DATA_PATH = OUTPUT_DIR / "facturacion_raw.csv"
VALID_DATA_PATH = OUTPUT_DIR / "facturacion_validos.parquet"
REJECTED_DATA_PATH = OUTPUT_DIR / "facturacion_rechazados.xlsx"
QUALITY_REPORT_PATH = OUTPUT_DIR / "reporte_calidad.json"

MAX_DIAS_ATRASO = 60  # Regla de Oportunidad: tope de atraso permitido, en días
N_CLIENTES = 1050  # una carga típica trae un período por cliente -> ~1,050+ registros base

CAMPOS_OBLIGATORIOS = ["id_cliente", "periodo", "trabajadores_activos", "valor_contrato"]
ID_CLIENTE_PATTERN = re.compile(r"^\d+$")
FORMATOS_FECHA_ACEPTADOS = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d", "%d-%b-%Y"]


# --------------------------------------------------------------------------
# 1. Generación de datos de prueba con problemas intencionales
# --------------------------------------------------------------------------

def _id_cliente_formats(id_numero: int) -> str:
    """Devuelve id_numero en uno de varios formatos de texto, varios de ellos
    'sucios' a propósito, simulando cómo distintos sistemas de origen
    representan el mismo id_cliente de forma inconsistente.
    """
    formatos = [
        lambda n: f"{n}",      # "123"            (limpio)
        lambda n: f" {n} ",    # " 123 "          (espacios en blanco)
        lambda n: f"CLI-{n}",  # "CLI-123"        (prefijo con guion)
        lambda n: f"{n}.0",    # "123.0"          (típico al exportar desde Excel)
        lambda n: f"{n:06d}",  # "000123"         (con ceros a la izquierda)
    ]
    return random.choice(formatos)(id_numero)


def _periodo_formats(fecha: date) -> str:
    """Devuelve la fecha de período en uno de varios formatos de texto,
    simulando que la fuente heredada no estandariza el formato de fecha.
    """
    return random.choice([fecha.strftime(fmt) for fmt in FORMATOS_FECHA_ACEPTADOS])


def generate_test_data(n_clientes: int = N_CLIENTES, seed: int = 42) -> pd.DataFrame:
    """Genera un archivo de facturación sintético con 1,000+ registros,
    incluyendo intencionalmente los 4 tipos de problema que pide el ejercicio:

    1. IDs de cliente con formatos inconsistentes.
    2. Períodos en distintos formatos de fecha.
    3. Valores negativos o nulos en campos críticos.
    4. Duplicados por cliente + período (con formato de ID/fecha distinto
       entre el original y el duplicado, para forzar que la detección de
       duplicados se haga sobre valores normalizados, no sobre texto crudo).

    Nota de diseño: una carga real de facturación llega periódicamente (un
    período por cliente en cada carga), no con el historial completo de cada
    cliente. Por eso el archivo de prueba simula una sola carga del período
    recién cerrado (mes anterior) para muchos clientes, en lugar de varios
    meses de historia por cliente, que haría que casi todo el archivo
    pareciera "atrasado" frente a la regla de Oportunidad sin que eso
    refleje un escenario real.
    """
    random.seed(seed)
    np.random.seed(seed)

    hoy = date.today()
    primer_dia_mes_actual = date(hoy.year, hoy.month, 1)
    periodo_carga = (pd.Timestamp(primer_dia_mes_actual) - pd.DateOffset(months=1)).date()

    # Tarifa mensual por trabajador en pesos colombianos, calibrada a un
    # rango realista para un servicio de riesgo laboral/prevención (similar
    # a una cotización de ARL: entre $15,000 y $45,000 COP por trabajador al
    # mes). El valor del contrato depende del número de trabajadores, no es
    # un monto aleatorio independiente, para que campos como costo_x_trab
    # (calculados en otras secciones del examen) tengan sentido de negocio.
    TARIFA_MIN_POR_TRABAJADOR = 15_000
    TARIFA_MAX_POR_TRABAJADOR = 45_000

    base = []
    for id_numero in range(1, n_clientes + 1):
        trabajadores = int(np.random.randint(5, 500))
        tarifa_por_trabajador = np.random.uniform(TARIFA_MIN_POR_TRABAJADOR, TARIFA_MAX_POR_TRABAJADOR)
        base.append(
            {
                "id_numero": id_numero,
                "periodo_fecha": periodo_carga,
                "trabajadores_activos": trabajadores,
                "valor_contrato": round(trabajadores * tarifa_por_trabajador, -3),  # redondeado a miles de COP
            }
        )
    df_base = pd.DataFrame(base)

    # --- Problema: duplicados por cliente + periodo (~3% de filas extra) ---
    # Se duplican ANTES de aplicar formato de texto; el formato de id/periodo
    # se asigna de forma independiente a cada copia más abajo, para simular
    # el caso real donde el mismo cliente llega como "007" en una carga y
    # "7" en otra: son duplicados reales, pero solo se detectan comparando
    # valores ya normalizados.
    duplicados = df_base.sample(frac=0.03, random_state=seed).copy()
    df_base = pd.concat([df_base, duplicados], ignore_index=True)
    df_base = df_base.sample(frac=1, random_state=seed).reset_index(drop=True)

    # Aplicar formato de texto "sucio" a id_cliente y periodo
    df_base["id_cliente"] = df_base["id_numero"].apply(_id_cliente_formats)
    df_base["periodo"] = df_base["periodo_fecha"].apply(_periodo_formats)
    df = df_base[["id_cliente", "periodo", "trabajadores_activos", "valor_contrato"]].copy()

    # --- Problema: nulos en campos críticos (~2% por campo) ---
    df.loc[df.sample(frac=0.02, random_state=seed + 1).index, "trabajadores_activos"] = None
    df.loc[df.sample(frac=0.02, random_state=seed + 2).index, "valor_contrato"] = None
    df.loc[df.sample(frac=0.01, random_state=seed + 3).index, "id_cliente"] = None

    # --- Problema: valores negativos en campos críticos (~1% por campo) ---
    idx_neg_trab = df.sample(frac=0.01, random_state=seed + 4).index
    df.loc[idx_neg_trab, "trabajadores_activos"] = -df.loc[idx_neg_trab, "trabajadores_activos"].fillna(10).abs()

    idx_neg_valor = df.sample(frac=0.01, random_state=seed + 5).index
    df.loc[idx_neg_valor, "valor_contrato"] = -df.loc[idx_neg_valor, "valor_contrato"].fillna(1_000_000).abs()

    # --- Problema: periodos fuera de la ventana de Oportunidad (~2%) ---
    idx_futuro = df.sample(frac=0.01, random_state=seed + 6).index
    df.loc[idx_futuro, "periodo"] = (hoy + timedelta(days=15)).strftime("%Y-%m-%d")

    idx_atrasado = df.sample(frac=0.01, random_state=seed + 7).index
    df.loc[idx_atrasado, "periodo"] = (hoy - timedelta(days=120)).strftime("%d/%m/%Y")

    df = df.sample(frac=1, random_state=seed + 8).reset_index(drop=True)

    logger.info("Datos de prueba generados: %d registros", len(df))
    return df


# --------------------------------------------------------------------------
# 2. Normalización
# --------------------------------------------------------------------------

def normalize_id_cliente(valor) -> tuple[int | None, bool]:
    """Intenta normalizar id_cliente a un entero positivo limpio, aceptando
    las variantes de formato generadas arriba (prefijo CLI-, espacios,
    sufijo decimal, ceros a la izquierda). Devuelve (valor_normalizado, es_valido).
    """
    if pd.isna(valor):
        return None, False

    texto = str(valor).strip()
    texto = re.sub(r"^CLI-?", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\.0$", "", texto)
    texto = texto.lstrip("0") or "0"

    if ID_CLIENTE_PATTERN.match(texto) and int(texto) > 0:
        return int(texto), True
    return None, False


def normalize_periodo(valor) -> tuple[date | None, bool]:
    """Intenta parsear el período probando cada formato de fecha aceptado.
    Devuelve (fecha_normalizada, es_valido).
    """
    if pd.isna(valor):
        return None, False

    texto = str(valor).strip()
    for fmt in FORMATOS_FECHA_ACEPTADOS:
        try:
            return datetime.strptime(texto, fmt).date(), True
        except ValueError:
            continue
    return None, False


def coerce_numeric_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte trabajadores_activos y valor_contrato a numérico, forzando
    a NaN cualquier valor no interpretable. Necesario tanto si los datos
    vienen de un CSV real (donde todo llega como texto) como del generador
    de prueba.
    """
    df = df.copy()
    df["trabajadores_activos"] = pd.to_numeric(df["trabajadores_activos"], errors="coerce")
    df["valor_contrato"] = pd.to_numeric(df["valor_contrato"], errors="coerce")
    return df


# --------------------------------------------------------------------------
# 3. Validación por regla
# --------------------------------------------------------------------------

def validate_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica las 5 reglas de calidad del ejercicio (Completitud, Validez,
    Unicidad, Consistencia, Oportunidad) y devuelve el DataFrame enriquecido
    con: columnas normalizadas, el resultado booleano de cada regla, la
    razón de rechazo concatenada, y la bandera final es_valido.

    Cada regla se evalúa de forma independiente (para que el score por
    dimensión sea preciso), evitando que la ausencia de un dato (ya cubierta
    por Completitud) se cuente también como fallo de Consistencia u
    Oportunidad, donde simplemente no hay suficiente información para
    evaluar la regla.
    """
    df = df.copy()
    hoy = date.today()

    # --- Normalización (requisito previo para Validez, Unicidad y Oportunidad) ---
    df["id_cliente_norm"], df["id_valido"] = zip(*df["id_cliente"].apply(normalize_id_cliente))
    df["periodo_norm"], df["periodo_valido"] = zip(*df["periodo"].apply(normalize_periodo))

    # --- Completitud: campos obligatorios sin nulos ---
    df["regla_completitud"] = df[CAMPOS_OBLIGATORIOS].notna().all(axis=1)

    # --- Validez: valores dentro de rangos y formatos esperados ---
    trabajadores_valido = df["trabajadores_activos"].apply(lambda x: pd.notna(x) and x >= 0)
    valor_valido = df["valor_contrato"].apply(lambda x: pd.notna(x) and x >= 0)
    df["regla_validez"] = df["id_valido"] & df["periodo_valido"] & trabajadores_valido & valor_valido

    # --- Unicidad: sin duplicados por id_cliente + periodo, ya normalizados ---
    clave = df["id_cliente_norm"].astype(str) + "_" + df["periodo_norm"].astype(str)
    df["regla_unicidad"] = ~clave.duplicated(keep="first")

    # --- Consistencia: trabajadores_activos > 0 cuando valor_contrato > 0 ---
    def _check_consistencia(row) -> bool:
        if pd.isna(row["trabajadores_activos"]) or pd.isna(row["valor_contrato"]):
            return True  # sin dato suficiente para evaluar; ya lo captura Completitud
        if row["valor_contrato"] > 0:
            return row["trabajadores_activos"] > 0
        return True

    df["regla_consistencia"] = df.apply(_check_consistencia, axis=1)

    # --- Oportunidad: periodo no futuro, ni con más de 60 días de atraso ---
    def _check_oportunidad(periodo_norm) -> bool:
        if periodo_norm is None:
            return True  # formato inválido ya lo captura Validez
        if periodo_norm > hoy:
            return False
        return (hoy - periodo_norm).days <= MAX_DIAS_ATRASO

    df["regla_oportunidad"] = df["periodo_norm"].apply(_check_oportunidad)

    # --- Razón de rechazo y bandera final ---
    mensajes_regla = {
        "completitud": "Completitud: campo obligatorio nulo",
        "validez": "Validez: formato o rango inválido",
        "unicidad": "Unicidad: duplicado por id_cliente + periodo",
        "consistencia": "Consistencia: trabajadores_activos no > 0 con valor_contrato > 0",
        "oportunidad": f"Oportunidad: periodo futuro o con más de {MAX_DIAS_ATRASO} días de atraso",
    }

    def _build_reason(row) -> str:
        return "; ".join(
            mensaje for regla, mensaje in mensajes_regla.items() if not row[f"regla_{regla}"]
        )

    df["razon_rechazo"] = df.apply(_build_reason, axis=1)
    df["es_valido"] = df["razon_rechazo"] == ""

    return df


# --------------------------------------------------------------------------
# 4. Reporte de calidad
# --------------------------------------------------------------------------

def build_quality_report(df: pd.DataFrame) -> dict:
    """Construye el reporte de calidad: score por dimensión (% de registros
    que pasan esa regla), total de registros, válidos y rechazados por regla.
    """
    total = len(df)
    dimensiones = ["completitud", "validez", "unicidad", "consistencia", "oportunidad"]

    score_por_dimension = {}
    rechazados_por_regla = {}
    for dim in dimensiones:
        aprobados = int(df[f"regla_{dim}"].sum())
        score_por_dimension[dim] = round(aprobados / total * 100, 2) if total else 0.0
        rechazados_por_regla[dim] = total - aprobados

    return {
        "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "total_registros": total,
        "registros_validos": int(df["es_valido"].sum()),
        "registros_rechazados": int((~df["es_valido"]).sum()),
        "score_calidad_global": round(df["es_valido"].mean() * 100, 2) if total else 0.0,
        "score_por_dimension": score_por_dimension,
        "rechazados_por_regla": rechazados_por_regla,
    }


# --------------------------------------------------------------------------
# 5. Exportación de resultados
# --------------------------------------------------------------------------

COLUMNAS_VALIDOS = {
    "id_cliente_norm": "id_cliente",
    "periodo_norm": "periodo",
    "trabajadores_activos": "trabajadores_activos",
    "valor_contrato": "valor_contrato",
}
COLUMNAS_RECHAZADOS = [
    "id_cliente", "periodo", "trabajadores_activos", "valor_contrato", "razon_rechazo",
]


def export_results(df: pd.DataFrame, reporte: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    validos = df.loc[df["es_valido"], list(COLUMNAS_VALIDOS)].rename(columns=COLUMNAS_VALIDOS)
    # id_cliente_norm llega como float si la columna completa (antes del
    # filtro) tuvo nulos; en los registros válidos nunca hay nulos, así que
    # se castea de vuelta a entero para no exportar "202.0" en vez de "202".
    validos["id_cliente"] = validos["id_cliente"].astype("int64")
    validos.to_parquet(VALID_DATA_PATH, index=False)
    logger.info("Registros válidos exportados a %s (%d filas)", VALID_DATA_PATH, len(validos))

    rechazados = df.loc[~df["es_valido"], COLUMNAS_RECHAZADOS]
    rechazados.to_excel(REJECTED_DATA_PATH, index=False, sheet_name="rechazados")
    logger.info("Registros rechazados exportados a %s (%d filas)", REJECTED_DATA_PATH, len(rechazados))

    with open(QUALITY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)
    logger.info("Reporte de calidad exportado a %s", QUALITY_REPORT_PATH)


# --------------------------------------------------------------------------
# 6. Orquestación
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida la calidad de un archivo de facturación antes de que entre al pipeline."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help=(
            "Ruta a un CSV de facturación real (columnas: id_cliente, periodo, "
            "trabajadores_activos, valor_contrato). Si no se indica, se genera "
            "un archivo de prueba con problemas intencionales."
        ),
    )
    args = parser.parse_args()

    try:
        if args.input:
            logger.info("Cargando archivo de entrada: %s", args.input)
            df_raw = pd.read_csv(args.input, dtype=str)
            faltantes = set(CAMPOS_OBLIGATORIOS) - set(df_raw.columns)
            if faltantes:
                logger.error("El archivo de entrada no tiene las columnas requeridas: %s", faltantes)
                sys.exit(1)
        else:
            df_raw = generate_test_data()
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            df_raw.to_csv(RAW_DATA_PATH, index=False)
            logger.info("Archivo de prueba guardado en %s", RAW_DATA_PATH)

        df_raw = coerce_numeric_fields(df_raw)

        logger.info("Validando %d registros...", len(df_raw))
        df_validado = validate_dataframe(df_raw)

        reporte = build_quality_report(df_validado)
        export_results(df_validado, reporte)

        logger.info(
            "Validación completa: %d válidos, %d rechazados (score global: %.2f%%)",
            reporte["registros_validos"],
            reporte["registros_rechazados"],
            reporte["score_calidad_global"],
        )
        print(json.dumps(reporte, indent=2, ensure_ascii=False))

    except FileNotFoundError:
        logger.error("No se encontró el archivo de entrada: %s", args.input)
        sys.exit(1)
    except Exception:
        logger.exception("Error inesperado durante la validación")
        sys.exit(1)


if __name__ == "__main__":
    main()
