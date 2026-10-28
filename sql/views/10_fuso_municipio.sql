-- UTC offset per municipality, from the urna clocks: fuso = local - Brasilia, in hours.
-- Median of each section's first vote time (election day only). Fewer than 3 sections
-- falls back to the state default; states not listed have 0.
CREATE OR REPLACE VIEW main.fuso_municipio AS
WITH padrao_uf(sigla_uf, fuso) AS (
    VALUES ('AC', -2), ('AM', -1), ('MT', -1), ('MS', -1), ('RO', -1), ('RR', -1)
),
primeiro_voto AS (
    SELECT e.ano, e.turno, e.sigla_uf, e.id_municipio_tse, e.zona, e.secao,
           min(e.data_hora) AS hora
    FROM br_tse_urna_logs.eventos e
    JOIN main.eleicoes el ON el.ano = e.ano AND el.turno = e.turno
    WHERE e.tipo_evento = 'voto_computado'
      AND CAST(e.data_hora AS DATE) = el.data
    GROUP BY ALL
),
minutos AS (
    SELECT ano, turno, sigla_uf, id_municipio_tse, zona, secao,
           hour(hora) * 60 + minute(hora) AS minuto
    FROM primeiro_voto
),
por_municipio AS (
    SELECT ano, turno, sigla_uf, id_municipio_tse,
           count(*) AS n_secoes,
           median(minuto) AS mediana_minuto
    FROM minutos
    GROUP BY ALL
)
SELECT p.ano,
       p.turno,
       p.sigla_uf,
       p.id_municipio_tse,
       CASE WHEN p.n_secoes >= 3
            THEN CAST(round((p.mediana_minuto - 480) / 60.0) AS INTEGER)
            ELSE coalesce(d.fuso, 0)
       END AS fuso
FROM por_municipio p
LEFT JOIN padrao_uf d ON d.sigla_uf = p.sigla_uf;
