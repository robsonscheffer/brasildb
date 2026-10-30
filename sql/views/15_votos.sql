-- One row per vote counted on election day (urna clock). Every vote count reads this view, not
-- eventos. Two cases in a section's archive would count a vote twice:
-- a member whose setup lines name another section ("Seção Eleitoral: 0112" inside the archive
-- of 0085) is that section's log, filed here too; it is dropped. A contingency urna names 0000
-- and stays. A member that copies another member's lines (a replaced urna's card, "...ME.jez")
-- repeats its vote seconds; one urna never logs two votes in the same second, so a second
-- counts once per section.
CREATE OR REPLACE VIEW main.votos AS
WITH carga AS (
    SELECT ano, turno, sigla_uf, id_municipio_tse, zona, secao, arquivo_hash, arquivo_membro,
           bool_or(regexp_extract(mensagem, 'Seção Eleitoral: (\d+)', 1) IN (secao, '0000')) AS propria
    FROM br_tse_urna_logs.eventos
    WHERE mensagem LIKE 'Seção Eleitoral: %'
    GROUP BY ALL
)
SELECT e.ano, e.turno, e.sigla_uf, e.id_municipio_tse, e.zona, e.secao,
       e.data_hora, e.arquivo_hash, e.arquivo_membro, e.linha
FROM br_tse_urna_logs.eventos e
JOIN main.eleicoes el ON el.ano = e.ano AND el.turno = e.turno
LEFT JOIN carga c
  ON  c.ano = e.ano AND c.turno = e.turno AND c.sigla_uf = e.sigla_uf
  AND c.id_municipio_tse = e.id_municipio_tse AND c.zona = e.zona AND c.secao = e.secao
  AND c.arquivo_hash = e.arquivo_hash AND c.arquivo_membro = e.arquivo_membro
WHERE e.tipo_evento = 'voto_computado'
  AND CAST(e.data_hora AS DATE) = el.data
  AND coalesce(c.propria, true)
QUALIFY row_number() OVER (PARTITION BY e.ano, e.turno, e.sigla_uf, e.id_municipio_tse, e.zona,
                                        e.secao, e.data_hora
                           ORDER BY e.arquivo_membro, e.linha) = 1;
