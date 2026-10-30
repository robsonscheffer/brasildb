-- Votes per section and hour, on election day. hora_local is the urna clock hour;
-- hora_brasilia = hora_local - fuso (not wrapped to 0-23).
CREATE OR REPLACE VIEW main.votos_hora AS
SELECT e.ano,
       e.turno,
       e.sigla_uf,
       e.id_municipio_tse,
       e.zona,
       e.secao,
       CAST(hour(e.data_hora) AS INTEGER) AS hora_local,
       CAST(hour(e.data_hora) - f.fuso AS INTEGER) AS hora_brasilia,
       count(*) AS votos
FROM main.votos e
JOIN main.fuso_municipio f
  ON f.ano = e.ano AND f.turno = e.turno
 AND f.sigla_uf = e.sigla_uf AND f.id_municipio_tse = e.id_municipio_tse
GROUP BY ALL;
