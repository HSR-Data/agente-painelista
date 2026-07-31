#!/usr/bin/env python3
"""Passo 3 (resolve): dos InfoIDs/respostas validados -> contagem de respondentes e CSV.

- Sempre imprime: respondentes TOTAIS e quantos têm PainelistaID (GUID Fala.e).
- Com --out, grava um CSV com as colunas: id, painelistaid, codjob, infoid
  (uma linha por respondente x tema x pesquisa).

A contagem é ANCORADA POR JOB: só conta respondentes das perguntas que o subagente
aprovou (o mesmo InfoID pode aparecer em pesquisas não relacionadas).

Uso:
  python scripts/resolve.py --validated dados_tmp/validado.json
  python scripts/resolve.py --validated dados_tmp/validado.json --out resultado.csv
"""
import os
import sys
import json
import csv
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from painelista_search import make_connection, parse_validated

# Casa uma linha de tabela_respondentes com algum par validado (respeitando o job aprovado).
MATCH = (
    "EXISTS (SELECT 1 FROM #validados v WHERE v.InfoID = tr.InfoID "
    "AND (v.AllResp = 1 OR v.RespostaID = tr.RespostaID) "
    "AND (v.codJob IS NULL OR v.codJob = tr.codJob))"
)


def _carrega_validados(cur, items):
    cur.execute("CREATE TABLE #validados (InfoID INT, RespostaID BIGINT NULL, AllResp BIT, codJob INT NULL)")
    rows = []
    for it in items:
        jobs = it.get("codJobs") or [None]
        for job in jobs:
            if it["allResponses"]:
                rows.append((it["InfoID"], None, 1, job))
            else:
                for rid in it["respostaIds"]:
                    rows.append((it["InfoID"], rid, 0, job))
    if rows:
        cur.executemany("INSERT INTO #validados (InfoID, RespostaID, AllResp, codJob) VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def resolve(validated_path, out_csv=None):
    with open(validated_path, encoding="utf-8") as f:
        data = json.load(f)
    items = parse_validated(data)
    if not items:
        return {"total": 0, "com_painelista": 0, "linhas_csv": 0}

    conn = make_connection()
    try:
        cur = conn.cursor()
        _carrega_validados(cur, items)

        # Contagem: total de respondentes e quantos têm PainelistaID.
        cur.execute(
            "SELECT COUNT(DISTINCT tr.CodCliente), "
            "       COUNT(DISTINCT CASE WHEN tr.PainelistaID IS NOT NULL THEN tr.CodCliente END) "
            f"FROM tabela_respondentes tr WHERE {MATCH}")
        total, com_pid = cur.fetchone()
        resultado = {"total": int(total or 0), "com_painelista": int(com_pid or 0), "linhas_csv": 0}

        if out_csv:
            cur.execute(
                "SELECT DISTINCT tr.CodCliente, tr.PainelistaID, tr.codJob, tr.InfoID "
                f"FROM tabela_respondentes tr WHERE {MATCH}")
            os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
            n = 0
            with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["id", "painelistaid", "codjob", "infoid"])
                for r in cur.fetchall():
                    w.writerow([r[0], r[1] if r[1] is not None else "", r[2], r[3]])
                    n += 1
            resultado["linhas_csv"] = n
        return resultado
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validated", required=True)
    ap.add_argument("--out", default=None, help="Caminho do CSV (opcional). Colunas: id,painelistaid,codjob,infoid")
    a = ap.parse_args()

    r = resolve(a.validated, a.out)
    print(f"[RESULTADO] respondentes_totais={r['total']} | com_painelistaid={r['com_painelista']}")
    if a.out:
        print(f"[CSV] {r['linhas_csv']} linhas gravadas em {a.out} (colunas: id,painelistaid,codjob,infoid)")


if __name__ == "__main__":
    main()
