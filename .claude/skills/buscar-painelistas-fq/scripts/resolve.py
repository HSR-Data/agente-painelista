#!/usr/bin/env python3
"""Passo 5 (resolve): decisões por padrão → painelistas das DUAS fontes → contagem e CSV.

Para cada padrão aceito, a decisão (ids LOCAIS de opção, ou allResponses) é aplicada a
todos os membros:
  • opção aceita = mesmo texto normalizado; ou, se a decisão aceitou uma opção que casou
    o termo, as opções que casaram o termo naquele membro;
  • membro antigo com opção de texto vazio (`$FUNCAO_MIDIA` apagado): aceita pelo CÓDIGO
    das opções escolhidas.

fq_     fq_resposta (Parte = código da opção; filtrado por ParteHash, que está no índice)
        → fq_cliente.PainelistaID; data = fq_cliente.DtTrabalho.
antigo  respondentes.PainelistaID (preenchido pelo pipeline antigo); data = DataResposta.
        Só entram IDs que existem em falai.dbo.Painelista.

A contagem é de PainelistaID distintos na UNIÃO das duas fontes (a mesma pessoa aparece
nas duas quando a onda ainda está no FQ e também foi arquivada).

CSV: painelistaid, data_resposta (mais recente), fonte (fq_ | antigo | ambos)
_detalhado.csv: + origem da resposta mais recente (fonte, repositorio, codjob, codquestao)

Uso:
  python "$SKILL/scripts/resolve.py" --validated dados_tmp/validado.json --out resultado_vivo.csv
"""
import os
import sys
import csv
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from painelista_search import make_connection


def expandir(validado, grupos):
    fq_linhas, ant_linhas = set(), set()   # (v, repo, q, cod|None, all) / (job, q, rid|None, all)
    for v in validado.get("validados", []):
        g = grupos.get(v.get("grupo"))
        if not g:
            continue
        todas = bool(v.get("allResponses"))
        ids = [str(int(x)) for x in (v.get("respostaIds") or [])]
        esc = [g["opcoes"][i] for i in ids if i in g["opcoes"]]
        textos = {o["t"] for o in esc}
        cods = {c for o in esc for c in o["cods"]}
        usa_casadas = any(o["casou"] for o in esc)
        for m in g["membros"]:
            if m["fonte"] == "fq_":
                if todas:
                    fq_linhas.add((m["v"], m["repo"], m["q"], None, 1)); continue
                for cod, t, casou in m["ops"]:
                    if t in textos or (usa_casadas and casou):
                        fq_linhas.add((m["v"], m["repo"], m["q"], cod, 0))
            else:
                if todas:
                    ant_linhas.add((m["job"], m["q"], None, 1)); continue
                for rid, cod, t, casou in m["ops"]:
                    if (t and t in textos) or (usa_casadas and casou) or (not t and cod in cods):
                        ant_linhas.add((m["job"], m["q"], rid, 0))
    return fq_linhas, ant_linhas


def _data(v):
    return "" if v is None else str(v)[:16]


def _sufixo(caminho, suf):
    raiz, ext = os.path.splitext(caminho)
    return f"{raiz}{suf}{ext or '.csv'}"


def resolve(validated_path, grupos_path, out_csv=None):
    validado = json.load(open(validated_path, encoding="utf-8"))
    grupos = json.load(open(grupos_path, encoding="utf-8"))
    fq_linhas, ant_linhas = expandir(validado, grupos)
    pessoas = {}   # pid -> [data, fontes:set, origem]

    def soma(pid, data, fonte, origem):
        pid = str(pid).strip().lower()
        p = pessoas.setdefault(pid, [None, set(), None])
        p[1].add(fonte)
        if p[0] is None or (data is not None and data > p[0]):
            p[0], p[2] = data, origem

    conn = make_connection()
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        if fq_linhas:
            cur.execute("CREATE TABLE #vf (fq_version TINYINT, repositorio VARCHAR(128), CodQuestao INT, "
                        "Opcao INT NULL, AllResp BIT, ParteHash BINARY(32) NULL)")
            cur.executemany("INSERT INTO #vf (fq_version, repositorio, CodQuestao, Opcao, AllResp) "
                            "VALUES (?, ?, ?, ?, ?)", list(fq_linhas))
            cur.execute("UPDATE #vf SET ParteHash = HASHBYTES('SHA2_256', "
                        "CAST(CAST(Opcao AS NVARCHAR(20)) AS NVARCHAR(MAX))) WHERE Opcao IS NOT NULL")
            cur.execute("""
                WITH h AS (
                    SELECT DISTINCT r.fq_version, r.repositorio, r.CodCliente, r.CodQuestao
                    FROM fq_resposta r JOIN #vf v ON v.fq_version=r.fq_version
                         AND v.repositorio=r.repositorio AND v.CodQuestao=r.CodQuestao
                         AND (v.AllResp = 1 OR v.ParteHash = r.ParteHash))
                SELECT c.PainelistaID, c.DtTrabalho, h.repositorio, c.CodJob, h.CodQuestao
                FROM h JOIN fq_cliente c ON c.fq_version=h.fq_version AND c.repositorio=h.repositorio
                                        AND c.codCliente=h.CodCliente""")
            for pid, dt, repo, job, q in cur.fetchall():
                soma(pid, dt, "fq_", ("fq_", repo, job, q))
        if ant_linhas:
            cur.execute("CREATE TABLE #vo (codJob INT, CodQuestao INT, RespostaID BIGINT NULL, AllResp BIT)")
            cur.executemany("INSERT INTO #vo VALUES (?, ?, ?, ?)", list(ant_linhas))
            cur.execute("""
                SELECT d.PainelistaID, MAX(d.DataResposta), MAX(d.codJob), MAX(d.CodQuestao)
                FROM respondentes d
                JOIN #vo v ON v.codJob=d.codJob AND v.CodQuestao=d.CodQuestao
                          AND (v.AllResp = 1 OR v.RespostaID = d.RespostaID)
                JOIN falai.dbo.Painelista p ON p.PainelistaID = TRY_CAST(LTRIM(RTRIM(d.PainelistaID)) AS UNIQUEIDENTIFIER)
                WHERE d.PainelistaID IS NOT NULL
                GROUP BY d.PainelistaID""")
            for pid, dt, job, q in cur.fetchall():
                soma(pid, dt, "antigo", ("antigo", "", job, q))
    finally:
        conn.close()

    def fonte(fs):
        return "ambos" if len(fs) == 2 else next(iter(fs))

    res = {"painelistas": len(pessoas),
           "so_fq": sum(1 for p in pessoas.values() if p[1] == {"fq_"}),
           "so_antigo": sum(1 for p in pessoas.values() if p[1] == {"antigo"}),
           "ambos": sum(1 for p in pessoas.values() if len(p[1]) == 2),
           "pares_fq": len(fq_linhas), "pares_antigo": len(ant_linhas)}
    if out_csv:
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
        ordem = sorted(pessoas.items())
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["painelistaid", "data_resposta", "fonte"])
            for pid, (dt, fs, _) in ordem:
                w.writerow([pid, _data(dt), fonte(fs)])
        det = _sufixo(out_csv, "_detalhado")
        with open(det, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["painelistaid", "data_resposta", "fonte", "origem", "repositorio", "codjob", "codquestao"])
            for pid, (dt, fs, org) in ordem:
                w.writerow([pid, _data(dt), fonte(fs)] + list(org or ("", "", "", "")))
        res["csv"], res["csv_detalhado"] = out_csv, det
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validated", required=True)
    ap.add_argument("--grupos", default=os.path.join(os.getcwd(), "dados_tmp", "grupos.json"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    r = resolve(a.validated, a.grupos, a.out)
    print(f"[PAINELISTAS] {r['painelistas']} (fq_ {r['so_fq'] + r['ambos']}, antigo {r['so_antigo'] + r['ambos']}, "
          f"nas duas {r['ambos']}, só no arquivo antigo {r['so_antigo']})")
    if a.out:
        print(f"[CSV] {r['csv']} (painelistaid,data_resposta,fonte)")
        print(f"[CSV_DETALHADO] {r['csv_detalhado']} — só entregar se pedirem")


if __name__ == "__main__":
    main()
