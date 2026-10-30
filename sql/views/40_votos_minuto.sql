-- Votes per municipality and minute, in Brasilia time, on election day. Feeds the replay
-- map (P2). Counts main.votos: minuto_bsb = urna clock - the town's fuso.
CREATE OR REPLACE VIEW main.votos_minuto AS
SELECT e.ano,
       e.turno,
       e.sigla_uf,
       e.id_municipio_tse,
       date_trunc('minute', e.data_hora - to_minutes(f.fuso_minutos)) AS minuto_bsb,
       count(*) AS votos
FROM main.votos e
JOIN main.fuso_municipio f
  ON f.ano = e.ano AND f.turno = e.turno
 AND f.sigla_uf = e.sigla_uf AND f.id_municipio_tse = e.id_municipio_tse
GROUP BY ALL;
