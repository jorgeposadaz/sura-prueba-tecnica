WITH
parametros AS (
    SELECT
        CURRENT_DATE - 1 AS fecha_corte,
        DATE_TRUNC('month', CURRENT_DATE - 1) AS inicio_mes_actual,
        DATE_TRUNC('month', DATEADD(month, -1, CURRENT_DATE - 1)) AS inicio_mes_anterior,
        DATEADD(month, -1, CURRENT_DATE - 1) AS fecha_corte_mes_anterior
),

casos_mes_actual AS (
    SELECT ca.id_cliente, COUNT(*) AS casos_mes_actual
    FROM casos ca
    CROSS JOIN parametros p
    WHERE ca.fecha_ocurrencia >= p.inicio_mes_actual
      AND ca.fecha_ocurrencia <= p.fecha_corte
    GROUP BY ca.id_cliente
),

casos_mes_anterior AS (
    -- mismo número de días transcurridos que el mes actual, para una comparación justa
    SELECT ca.id_cliente, COUNT(*) AS casos_mes_anterior
    FROM casos ca
    CROSS JOIN parametros p
    WHERE ca.fecha_ocurrencia >= p.inicio_mes_anterior
      AND ca.fecha_ocurrencia <= p.fecha_corte_mes_anterior
    GROUP BY ca.id_cliente
),

trabajadores_actuales AS (
    SELECT f.id_cliente, f.trabajadores_activos
    FROM facturacion f
    CROSS JOIN parametros p
    WHERE f.periodo = p.inicio_mes_actual
),

prevencion_30d AS (
    SELECT pr.id_cliente, COUNT(*) AS actividades_prevencion_30d
    FROM prevencion pr
    CROSS JOIN parametros p
    WHERE pr.fecha BETWEEN p.fecha_corte - 30 AND p.fecha_corte
    GROUP BY pr.id_cliente
)

SELECT
    c.id_cliente,
    c.nombre,
    c.clase_riesgo,
    COALESCE(cma.casos_mes_actual, 0) AS casos_mes_actual,
    COALESCE(cma.casos_mes_actual, 0) - COALESCE(can.casos_mes_anterior, 0) AS variacion_vs_mes_anterior,
    ta.trabajadores_activos,
    ROUND(COALESCE(cma.casos_mes_actual, 0) * 100.0 / NULLIF(ta.trabajadores_activos, 0), 2) AS tasa_incidencia,
    COALESCE(p30.actividades_prevencion_30d, 0) AS actividades_prevencion_30d,
    CASE
        WHEN ta.trabajadores_activos IS NULL OR ta.trabajadores_activos = 0 THEN 'sin datos'
        WHEN COALESCE(cma.casos_mes_actual, 0) * 100.0 / ta.trabajadores_activos > 5 THEN 'crítico'
        WHEN COALESCE(cma.casos_mes_actual, 0) * 100.0 / ta.trabajadores_activos >= 2 THEN 'moderado'
        ELSE 'bajo'
    END AS clasificacion
FROM clientes c
LEFT JOIN casos_mes_actual cma ON c.id_cliente = cma.id_cliente
LEFT JOIN casos_mes_anterior can ON c.id_cliente = can.id_cliente
LEFT JOIN trabajadores_actuales ta ON c.id_cliente = ta.id_cliente
LEFT JOIN prevencion_30d p30 ON c.id_cliente = p30.id_cliente
WHERE c.estado = 'activo';
