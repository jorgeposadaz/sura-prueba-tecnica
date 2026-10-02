WITH
casos_recientes AS (
    -- Severidad y frecuencia de los últimos 30 días
    SELECT
        id_cliente,
        COUNT(*) AS casos_30d,
        SUM(CASE WHEN tipo = 'grave' THEN 1 ELSE 0 END) AS casos_graves_30d
    FROM casos
    WHERE fecha_ocurrencia >= DATEADD(day, -30, CURRENT_DATE)
    GROUP BY id_cliente
),

incidencia_actual AS (
    -- Tasa de incidencia del mes en curso, para comparar tendencia
    SELECT
        ca.id_cliente,
        COUNT(ca.id_caso) AS casos_mes_actual,
        AVG(f.trabajadores_activos) AS trabajadores_mes_actual
    FROM casos ca
    JOIN facturacion f 
        ON ca.id_cliente = f.id_cliente
        AND f.periodo = DATE_TRUNC('month', CURRENT_DATE)
    WHERE ca.fecha_ocurrencia >= DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY ca.id_cliente
),

incidencia_anterior AS (
    -- Tasa de incidencia del mes anterior, para calcular tendencia
    SELECT
        ca.id_cliente,
        COUNT(ca.id_caso) AS casos_mes_anterior,
        AVG(f.trabajadores_activos) AS trabajadores_mes_anterior
    FROM casos ca
    JOIN facturacion f 
        ON ca.id_cliente = f.id_cliente
        AND f.periodo = DATE_TRUNC('month', DATEADD(month, -1, CURRENT_DATE))
    WHERE ca.fecha_ocurrencia >= DATE_TRUNC('month', DATEADD(month, -1, CURRENT_DATE))
        AND ca.fecha_ocurrencia < DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY ca.id_cliente
),

ultima_prevencion AS (
    -- Días transcurridos desde la última actividad de prevención
    SELECT
        id_cliente,
        MAX(fecha) AS fecha_ultima_prevencion,
        DATEDIFF(day, MAX(fecha), CURRENT_DATE) AS dias_sin_prevencion
    FROM prevencion
    GROUP BY id_cliente
),

score_final AS (
    SELECT
        c.id_cliente,
        c.nombre,
        c.clase_riesgo,
        COALESCE(cr.casos_30d, 0) AS casos_30d,
        COALESCE(cr.casos_graves_30d, 0) AS casos_graves_30d,
        COALESCE(ia.casos_mes_actual * 100.0 / NULLIF(ia.trabajadores_mes_actual, 0), 0) AS tasa_actual,
        COALESCE(ian.casos_mes_anterior * 100.0 / NULLIF(ian.trabajadores_mes_anterior, 0), 0) AS tasa_anterior,
        COALESCE(up.dias_sin_prevencion, 999) AS dias_sin_prevencion,
        -- Score ponderado: severidad reciente (35%) + tendencia (30%) + clase de riesgo (20%) + falta de prevención (15%)
        ROUND(
            (COALESCE(cr.casos_graves_30d, 0) * 10 + COALESCE(cr.casos_30d, 0) * 3) * 0.35
            + GREATEST(
                COALESCE(ia.casos_mes_actual * 100.0 / NULLIF(ia.trabajadores_mes_actual, 0), 0)
                - COALESCE(ian.casos_mes_anterior * 100.0 / NULLIF(ian.trabajadores_mes_anterior, 0), 0),
                0
              ) * 0.30
            + c.clase_riesgo * 4 * 0.20
            + LEAST(COALESCE(up.dias_sin_prevencion, 999), 90) / 90.0 * 10 * 0.15
        , 2) AS score_prioridad
    FROM clientes c
    LEFT JOIN casos_recientes cr ON c.id_cliente = cr.id_cliente
    LEFT JOIN incidencia_actual ia ON c.id_cliente = ia.id_cliente
    LEFT JOIN incidencia_anterior ian ON c.id_cliente = ian.id_cliente
    LEFT JOIN ultima_prevencion up ON c.id_cliente = up.id_cliente
    WHERE c.estado = 'activo'
)

SELECT
    id_cliente,
    nombre,
    clase_riesgo,
    casos_30d,
    casos_graves_30d,
    ROUND(tasa_actual, 2) AS tasa_incidencia_actual,
    ROUND(tasa_actual - tasa_anterior, 2) AS variacion_tasa,
    dias_sin_prevencion,
    score_prioridad
FROM score_final
ORDER BY score_prioridad DESC
LIMIT 15;
