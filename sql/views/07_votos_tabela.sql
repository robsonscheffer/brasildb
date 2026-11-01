-- optional: runs only when br_tse_urna_logs.votos is in the lake (see 06_votos.sql).
CREATE OR REPLACE VIEW main.votos AS
SELECT ano, turno, sigla_uf, id_municipio_tse, zona, secao, data_hora, arquivo_hash, arquivo_membro, linha
FROM br_tse_urna_logs.votos;
