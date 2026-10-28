-- Election rounds, same values as brasildb/config.py ELECTIONS. Views filter log lines by data.
CREATE OR REPLACE VIEW main.eleicoes AS
SELECT * FROM (VALUES
    (2026, 1, '3220', DATE '2026-10-04'),
    (2026, 2, '3221', DATE '2026-10-25')
) AS t(ano, turno, id_pleito, data);
