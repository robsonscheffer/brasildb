-- One row per section and round: the day's shape from the log. Times are Brasilia (urna clock
-- minus the town's fuso), election day only. A section whose urna was replaced has two logs
-- (arquivo_membro); counts sum both, times span both, modelo is the closing urna's.
-- quedas and min_bateria count energia=bateria lines between the first and last vote; a line
-- lasts until the next energia line of the same log, so a flicker counts as a few seconds.
CREATE OR REPLACE VIEW main.secao_dia AS
WITH dia AS (
    SELECT e.*, e.data_hora - to_minutes(f.fuso_minutos) AS hora_bsb
    FROM br_tse_urna_logs.eventos e
    JOIN main.eleicoes el ON el.ano = e.ano AND el.turno = e.turno
    JOIN main.fuso_municipio f
      ON f.ano = e.ano AND f.turno = e.turno
     AND f.sigla_uf = e.sigla_uf AND f.id_municipio_tse = e.id_municipio_tse
    WHERE CAST(e.data_hora AS DATE) = el.data
),
votos AS (
    SELECT ano, turno, sigla_uf, id_municipio_tse, zona, secao,
           min(hora_bsb) AS primeiro_voto, max(hora_bsb) AS ultimo_voto, count(*) AS votos
    FROM dia WHERE tipo_evento = 'voto_computado'
    GROUP BY ALL
),
energia AS (
    SELECT d.ano, d.turno, d.sigla_uf, d.id_municipio_tse, d.zona, d.secao, d.hora_bsb, d.valor,
           lead(d.hora_bsb) OVER (PARTITION BY d.ano, d.turno, d.sigla_uf, d.id_municipio_tse,
                                   d.zona, d.secao, d.arquivo_hash, d.arquivo_membro
                                   ORDER BY d.hora_bsb, d.linha) AS proxima
    FROM dia d
    WHERE d.tipo_evento = 'energia'
),
quedas AS (
    SELECT en.ano, en.turno, en.sigla_uf, en.id_municipio_tse, en.zona, en.secao,
           count(*) AS quedas,
           sum(epoch(coalesce(en.proxima, v.ultimo_voto) - en.hora_bsb)) / 60.0 AS min_bateria,
           min(en.hora_bsb) AS primeira_queda
    FROM energia en
    JOIN votos v USING (ano, turno, sigla_uf, id_municipio_tse, zona, secao)
    WHERE en.valor = 'bateria' AND en.hora_bsb > v.primeiro_voto AND en.hora_bsb < v.ultimo_voto
    GROUP BY ALL
),
resto AS (
    SELECT ano, turno, sigla_uf, id_municipio_tse, zona, secao,
           min(hora_bsb) FILTER (WHERE tipo_evento = 'urna_pronta') AS abertura,
           max(hora_bsb) FILTER (WHERE tipo_evento = 'encerramento') AS encerramento,
           count(*) FILTER (WHERE tipo_evento = 'eleitor_habilitado') AS habilitados,
           count(*) FILTER (WHERE tipo_evento = 'habilitacao') AS biometricos,
           count(*) FILTER (WHERE tipo_evento = 'solicita_digital') AS tentativas_digital,
           count(*) FILTER (WHERE tipo_evento = 'timeout_digital') AS timeouts_digital,
           count(*) FILTER (WHERE tipo_evento = 'tecla_indevida') AS teclas_indevidas,
           count(*) FILTER (WHERE tipo_evento = 'sem_atividade') AS sem_atividade,
           count(*) FILTER (WHERE tipo_evento = 'justificativa') AS justificativas,
           bool_or(tipo_evento = 'contingencia') AS contingencia,
           count(DISTINCT arquivo_membro) AS n_logs,
           max(valor) FILTER (WHERE tipo_evento = 'modelo_urna' AND arquivo_membro = 'logd.dat') AS modelo
    FROM dia
    GROUP BY ALL
)
SELECT r.ano, r.turno, r.sigla_uf, r.id_municipio_tse, r.zona, r.secao,
       r.abertura, v.primeiro_voto, v.ultimo_voto, r.encerramento,
       coalesce(v.votos, 0) AS votos,
       r.habilitados, r.biometricos, r.tentativas_digital, r.timeouts_digital,
       r.teclas_indevidas, r.sem_atividade, r.justificativas,
       coalesce(q.quedas, 0) AS quedas,
       coalesce(q.min_bateria, 0) AS min_bateria,
       q.primeira_queda,
       r.contingencia, r.n_logs, r.modelo
FROM resto r
LEFT JOIN votos v USING (ano, turno, sigla_uf, id_municipio_tse, zona, secao)
LEFT JOIN quedas q USING (ano, turno, sigla_uf, id_municipio_tse, zona, secao);
