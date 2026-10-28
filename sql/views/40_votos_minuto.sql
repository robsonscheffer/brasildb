-- Votes per municipality and minute, in Brasilia time, on election day. Feeds the replay
-- map (P2): minuto_bsb = urna clock - the town's fuso.
CREATE OR REPLACE VIEW main.votos_minuto AS
SELECT e.ano,
       e.turno,
       e.sigla_uf,
       e.id_municipio_tse,
       date_trunc('minute', e.data_hora - to_hours(f.fuso)) AS minuto_bsb,
       count(*) AS votos
FROM br_tse_urna_logs.eventos e
JOIN main.eleicoes el ON el.ano = e.ano AND el.turno = e.turno
JOIN main.fuso_municipio f
  ON f.ano = e.ano AND f.turno = e.turno
 AND f.sigla_uf = e.sigla_uf AND f.id_municipio_tse = e.id_municipio_tse
WHERE e.tipo_evento = 'voto_computado'
  AND CAST(e.data_hora AS DATE) = el.data
GROUP BY ALL;
