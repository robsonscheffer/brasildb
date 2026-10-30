-- UTC offset per municipality, from the urna clocks: fuso = local - Brasilia, in hours, and
-- fuso_minutos in minutes (use it: some cities abroad are 30 or 45 minutes off). Abroad (ZZ)
-- takes main.fuso_exterior; fuso there is fuso_minutos / 60 rounded, for votos_hora only.
-- Median of each section's first vote time (election day only); polls open at 08:00 Brasilia
-- everywhere. With fewer than 3 sections one late opening can skew the median, so the derived
-- value is kept only if the state has that offset (western AM is -2, Noronha in PE is +1);
-- otherwise the state default. States not listed have default 0 and no other offset.
CREATE OR REPLACE VIEW main.fuso_municipio AS
WITH padrao_uf(sigla_uf, fuso, outro) AS (
    VALUES ('AC', -2, NULL), ('AM', -1, -2), ('MT', -1, NULL), ('MS', -1, NULL),
           ('RO', -1, NULL), ('RR', -1, NULL), ('PE', 0, 1)
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
       CASE WHEN p.sigla_uf = 'ZZ' THEN CAST(round(x.fuso_minutos / 60.0) AS INTEGER)
            WHEN p.n_secoes >= 3 OR p.derivado = d.outro THEN p.derivado
            ELSE coalesce(d.fuso, 0)
       END AS fuso,
       CASE WHEN p.sigla_uf = 'ZZ' THEN x.fuso_minutos
            WHEN p.n_secoes >= 3 OR p.derivado = d.outro THEN p.derivado * 60
            ELSE coalesce(d.fuso, 0) * 60
       END AS fuso_minutos
FROM (SELECT *, CAST(round((mediana_minuto - 480) / 60.0) AS INTEGER) AS derivado
      FROM por_municipio) p
LEFT JOIN padrao_uf d ON d.sigla_uf = p.sigla_uf
LEFT JOIN main.fuso_exterior x ON p.sigla_uf = 'ZZ' AND x.id_municipio_tse = p.id_municipio_tse
WHERE p.sigla_uf <> 'ZZ' OR x.fuso_minutos IS NOT NULL;
