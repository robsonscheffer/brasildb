-- Per section and round: votes in the urna log on election day vs comparecimento from the CSV.
-- votos_log is the count of voto_computado lines; NULL when the section has no election-day log lines.
-- comparecimento is the max over cargos; NULL when there is no CSV row.
-- contingencia: the log shows a replacement urna. With the nested archive parsed (arquivo_membro)
-- the votes of both urnas are counted; a lake built before that fix is short here.
-- status: ok (equal) | diferente (not equal) | sem_log (CSV row, no log) | sem_csv (log, no CSV row).
CREATE OR REPLACE VIEW main.check_comparecimento AS
WITH log_dia AS (
    SELECT e.ano, e.turno, e.sigla_uf, e.id_municipio_tse, e.zona, e.secao,
           count(*) FILTER (WHERE e.tipo_evento = 'voto_computado') AS votos_log,
           bool_or(e.mensagem LIKE '%Urna de contingência%') AS contingencia
    FROM br_tse_urna_logs.eventos e
    JOIN main.eleicoes el ON el.ano = e.ano AND el.turno = e.turno
    WHERE CAST(e.data_hora AS DATE) = el.data
    GROUP BY ALL
),
comparecimento AS (
    SELECT ano, turno, sigla_uf, id_municipio_tse, zona, secao,
           max(comparecimento) AS comparecimento
    FROM br_tse_eleicoes.detalhes_votacao_secao
    GROUP BY ALL
)
SELECT coalesce(l.ano, c.ano) AS ano,
       coalesce(l.turno, c.turno) AS turno,
       coalesce(l.sigla_uf, c.sigla_uf) AS sigla_uf,
       coalesce(l.id_municipio_tse, c.id_municipio_tse) AS id_municipio_tse,
       coalesce(l.zona, c.zona) AS zona,
       coalesce(l.secao, c.secao) AS secao,
       l.votos_log,
       c.comparecimento,
       coalesce(l.contingencia, false) AS contingencia,
       CASE WHEN l.ano IS NULL THEN 'sem_log'
            WHEN c.ano IS NULL THEN 'sem_csv'
            WHEN l.votos_log = c.comparecimento THEN 'ok'
            ELSE 'diferente'
       END AS status
FROM log_dia l
FULL OUTER JOIN comparecimento c
  ON  l.ano = c.ano AND l.turno = c.turno AND l.sigla_uf = c.sigla_uf
  AND l.id_municipio_tse = c.id_municipio_tse AND l.zona = c.zona AND l.secao = c.secao;
