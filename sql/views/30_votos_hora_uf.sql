-- Votes per state and Brasilia hour.
CREATE OR REPLACE VIEW main.votos_hora_uf AS
SELECT ano,
       turno,
       sigla_uf,
       hora_brasilia,
       CAST(sum(votos) AS BIGINT) AS votos
FROM main.votos_hora
GROUP BY ALL;
