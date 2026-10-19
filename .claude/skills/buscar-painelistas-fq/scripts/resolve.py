#!/usr/bin/env python3
"""Passo 5 (resolve): decisões por padrão → painelistas das DUAS fontes → contagem e CSV.

Para cada padrão aceito, a decisão (ids LOCAIS de opção, ou allResponses) é aplicada a
todos os membros:
  • opção aceita = mesmo texto normalizado; ou, se a decisão aceitou uma opção que casou
    o termo, as opções que casaram o termo naquele membro;
  • membro antigo com opção de texto vazio (`$FUNCAO_MIDIA` apagado): aceita pelo CÓDIGO
    das opções escolhidas;
  • membro CONDICIONAL (pergunta que cita a resposta de outra, ex. "Nesta sua linha da
    {RU("P8")...}"): só conta quem também marcou a opção do termo na pergunta referida.

fq_     fq_resposta (Parte = código da opção; filtrado por ParteHash, que está no índice)
        → fq_cliente.PainelistaID; data = fq_cliente.DtTrabalho.
antigo  respondentes.PainelistaID (preenchido pelo pipeline antigo); data = DataResposta.
        Só entram IDs que existem em falai.dbo.Painelista.

A contagem é de PainelistaID distintos na UNIÃO das duas fontes (a mesma pessoa aparece
nas duas quando a onda ainda está no FQ e também foi arquivada).

Saídas (com --out resultado.csv):
  resultado.csv              painelistaid, data_resposta (mais recente), fonte (fq_ | antigo | ambos)
  resultado_detalhado.csv    + origem da resposta mais recente (fonte, repositorio, codjob, codquestao)
  resultado_padroes.csv      uma linha por padrão aceito: textos, condição, painelistas (fq_/antigo)
                             e, com --com-base, quantos responderam o padrão — confere de onde vem o número
  resultado_base.csv         (só com --com-base) TODA resposta aos padrões aceitos, com sim=1 (afirma o
                             conceito) ou sim=0 (respondeu outra coisa). É o "não" que falta para cortes
                             exclusivos ("só banda larga") e combinações — ver combinar.py.

--conceito ROTULO: quando o julgamento foi multi-conceito (cada aceite traz "conceito"), resolve só
os aceites desse rótulo.

Uso:
  python "$SKILL/scripts/resolve.py" --validated dados_tmp/validado.json --out resultado_vivo.csv
  python "$SKILL/scripts/resolve.py" --conceito BL --com-base --out resultado_vivo_bl.csv
"""
import os
import sys
import csv
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from painelista_search import make_connection


def escolher(validado, conceito):
    vs = validado.get("validados", [])
    rotulos = sorted({v.get("conceito") for v in vs if v.get("conceito")})
    if conceito:
        if conceito not in rotulos:
            sys.exit(f"ERRO: conceito '{conceito}' não está no validado (há: {', '.join(rotulos) or 'nenhum'}).")
        return [v for v in vs if v.get("conceito") == conceito]
    if rotulos:
        sys.exit(f"ERRO: julgamento multi-conceito — passe --conceito ({', '.join(rotulos)}).")
    return vs


def expandir(validados, grupos):
    """Linhas aceitas por membro. fq_: (grupo, v, repo, q, cod|None, all, condq|None, condcod|None);
    antigo: (grupo, job, q, rid|None, all, condq|None, condrid|None)."""
    fq_linhas, ant_linhas = set(), set()
    for v in validados:
        gid = v.get("grupo")
        g = grupos.get(gid)
        if not g:
            continue
        todas = bool(v.get("allResponses"))
        ids = [str(int(x)) for x in (v.get("respostaIds") or [])]
        esc = [g["opcoes"][i] for i in ids if i in g["opcoes"]]
        textos = {o["t"] for o in esc}
        cods = {c for o in esc for c in o["cods"]}
        usa_casadas = any(o["casou"] for o in esc)
        for m in g["membros"]:
            cond = m.get("cond") or {}
            if m["fonte"] == "fq_":
                conds = [(cond["q"], c) for c in cond.get("cods", [])] or [(None, None)]
                for cq, cc in conds:
                    if todas:
                        fq_linhas.add((gid, m["v"], m["repo"], m["q"], None, 1, cq, cc)); continue
                    for cod, t, casou in m["ops"]:
                        if t in textos or (usa_casadas and casou):
                            fq_linhas.add((gid, m["v"], m["repo"], m["q"], cod, 0, cq, cc))
            else:
                conds = [(cond["q"], r) for r in cond.get("rids", [])] or [(None, None)]
                for cq, cr in conds:
                    if todas:
                        ant_linhas.add((gid, m["job"], m["q"], None, 1, cq, cr)); continue
                    for rid, cod, t, casou in m["ops"]:
                        if (t and t in textos) or (usa_casadas and casou) or (not t and cod in cods):
                            ant_linhas.add((gid, m["job"], m["q"], rid, 0, cq, cr))
    return fq_linhas, ant_linhas


def membros_base(validados, grupos):
    """Todos os membros dos padrões aceitos, sem filtro de opção (para o "não")."""
    fq_b, ant_b = set(), set()
    for v in validados:
        g = grupos.get(v.get("grupo"))
        if not g:
            continue
        for m in g["membros"]:
            cond = m.get("cond") or {}
            if m["fonte"] == "fq_":
                for cq, cc in [(cond["q"], c) for c in cond.get("cods", [])] or [(None, None)]:
                    fq_b.add((v["grupo"], m["v"], m["repo"], m["q"], cq, cc))
            else:
                for cq, cr in [(cond["q"], r) for r in cond.get("rids", [])] or [(None, None)]:
                    ant_b.add((v["grupo"], m["job"], m["q"], cq, cr))
    return fq_b, ant_b


_HASH = "HASHBYTES('SHA2_256', CAST(CAST({c} AS NVARCHAR(20)) AS NVARCHAR(MAX)))"
_COND_FQ = """(v.CondQ IS NULL OR EXISTS (SELECT 1 FROM fq_resposta x WHERE x.fq_version=r.fq_version
                 AND x.repositorio=r.repositorio AND x.CodQuestao=v.CondQ AND x.CodCliente=r.CodCliente
                 AND x.ParteHash=v.CondHash))"""
_COND_ANT = """(v.CondQ IS NULL OR EXISTS (SELECT 1 FROM respondentes x WHERE x.codJob=d.codJob
                 AND x.CodQuestao=v.CondQ AND x.CodCliente=d.CodCliente AND x.RespostaID=v.CondRid))"""


def _fq(cur, linhas, base):
    """Respostas fq_ → (grupo, pid, data, repo, job, q). base=True: sem filtro de opção."""
    cur.execute("CREATE TABLE #v (grupo VARCHAR(16), fq_version TINYINT, repositorio VARCHAR(128), "
                "CodQuestao INT, Opcao INT NULL, AllResp BIT, CondQ INT NULL, CondOpcao INT NULL, "
                "ParteHash BINARY(32) NULL, CondHash BINARY(32) NULL)")
    if base:
        rows = [(g, v, r, q, None, 1, cq, cc) for g, v, r, q, cq, cc in linhas]
    else:
        rows = list(linhas)
    cur.executemany("INSERT INTO #v (grupo, fq_version, repositorio, CodQuestao, Opcao, AllResp, CondQ, CondOpcao) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    cur.execute(f"UPDATE #v SET ParteHash = {_HASH.format(c='Opcao')} WHERE Opcao IS NOT NULL")
    cur.execute(f"UPDATE #v SET CondHash = {_HASH.format(c='CondOpcao')} WHERE CondOpcao IS NOT NULL")
    cur.execute(f"""
        SELECT DISTINCT v.grupo, r.fq_version, r.repositorio, r.CodCliente, r.CodQuestao INTO #h
        FROM fq_resposta r JOIN #v v ON v.fq_version=r.fq_version AND v.repositorio=r.repositorio
             AND v.CodQuestao=r.CodQuestao AND (v.AllResp = 1 OR v.ParteHash = r.ParteHash)
        WHERE {_COND_FQ}""")
    cur.execute("""SELECT h.grupo, LOWER(CAST(c.PainelistaID AS VARCHAR(40))), c.DtTrabalho, h.repositorio,
                          c.CodJob, h.CodQuestao
                   FROM #h h JOIN fq_cliente c ON c.fq_version=h.fq_version AND c.repositorio=h.repositorio
                                              AND c.codCliente=h.CodCliente""")
    out = cur.fetchall()
    cur.execute("DROP TABLE #h; DROP TABLE #v")
    return out


def _antigo(cur, linhas, base):
    cur.execute("CREATE TABLE #o (grupo VARCHAR(16), codJob INT, CodQuestao INT, RespostaID BIGINT NULL, "
                "AllResp BIT, CondQ INT NULL, CondRid BIGINT NULL)")
    rows = [(g, j, q, None, 1, cq, cr) for g, j, q, cq, cr in linhas] if base else list(linhas)
    cur.executemany("INSERT INTO #o VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    cur.execute(f"""
        SELECT v.grupo, LOWER(LTRIM(RTRIM(d.PainelistaID))), MAX(d.DataResposta), d.codJob, d.CodQuestao
        FROM respondentes d
        JOIN #o v ON v.codJob=d.codJob AND v.CodQuestao=d.CodQuestao
                 AND (v.AllResp = 1 OR v.RespostaID = d.RespostaID)
        JOIN falai.dbo.Painelista p ON p.PainelistaID = TRY_CAST(LTRIM(RTRIM(d.PainelistaID)) AS UNIQUEIDENTIFIER)
        WHERE d.PainelistaID IS NOT NULL AND {_COND_ANT}
        GROUP BY v.grupo, LOWER(LTRIM(RTRIM(d.PainelistaID))), d.codJob, d.CodQuestao""")
    out = cur.fetchall()
    cur.execute("DROP TABLE #o")
    return out


def _data(v):
    return "" if v is None else str(v)[:19]


def _sufixo(caminho, suf):
    raiz, ext = os.path.splitext(caminho)
    return f"{raiz}{suf}{ext or '.csv'}"


def resolve(validated_path, grupos_path, out_csv=None, conceito=None, com_base=False):
    validado = json.load(open(validated_path, encoding="utf-8"))
    grupos = json.load(open(grupos_path, encoding="utf-8"))
    validados = escolher(validado, conceito)
    fq_linhas, ant_linhas = expandir(validados, grupos)
    pessoas = {}            # pid -> [data, fontes:set, origem]
    sim = {}                # grupo -> {fonte: set(pid)}
    hits = set()            # (fonte, pid, job, q, grupo) — para marcar sim/não na base

    def soma(pid, data, fonte, origem, grupo, job, q):
        pid = str(pid).strip().lower()
        p = pessoas.setdefault(pid, [None, set(), None])
        p[1].add(fonte)
        if p[0] is None or (data is not None and data > p[0]):
            p[0], p[2] = data, origem
        sim.setdefault(grupo, {}).setdefault(fonte, set()).add(pid)
        hits.add((fonte, pid, str(job), int(q), grupo))

    base_rows = []
    conn = make_connection()
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        if fq_linhas:
            for g, pid, dt, repo, job, q in _fq(cur, fq_linhas, False):
                soma(pid, dt, "fq_", ("fq_", repo, job, q), g, f"{repo}#{job}", q)
        if ant_linhas:
            for g, pid, dt, job, q in _antigo(cur, ant_linhas, False):
                soma(pid, dt, "antigo", ("antigo", "", job, q), g, f"job#{job}", q)
        if com_base:
            fq_b, ant_b = membros_base(validados, grupos)
            if fq_b:
                for g, pid, dt, repo, job, q in _fq(cur, fq_b, True):
                    pid = str(pid).strip().lower(); jk = f"{repo}#{job}"
                    base_rows.append((pid, _data(dt), "fq_", repo, job, q, g,
                                      int(("fq_", pid, jk, int(q), g) in hits)))
            if ant_b:
                for g, pid, dt, job, q in _antigo(cur, ant_b, True):
                    pid = str(pid).strip().lower(); jk = f"job#{job}"
                    base_rows.append((pid, _data(dt), "antigo", "", job, q, g,
                                      int(("antigo", pid, jk, int(q), g) in hits)))
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
                w.writerow([pid, _data(dt)[:16], fonte(fs)])
        det = _sufixo(out_csv, "_detalhado")
        with open(det, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["painelistaid", "data_resposta", "fonte", "origem", "repositorio", "codjob", "codquestao"])
            for pid, (dt, fs, org) in ordem:
                w.writerow([pid, _data(dt)[:16], fonte(fs)] + list(org or ("", "", "", "")))
        # um padrão por linha: de onde vem o número
        base_por = {}
        for pid, _, fo, _, _, _, g, _ in base_rows:
            base_por.setdefault(g, set()).add(pid)
        pad = _sufixo(out_csv, "_padroes")
        linhas = []
        for v in validados:
            g = v["grupo"]; gg = grupos.get(g, {}); s = sim.get(g, {})
            todos = set().union(*s.values()) if s else set()
            cond = gg.get("condicao") or {}
            linhas.append([g, v.get("conceito", ""), len(todos), len(s.get("fq_", ())), len(s.get("antigo", ())),
                           len(base_por.get(g, ())) if com_base else "",
                           gg.get("pergunta", ""), gg.get("mae", ""), gg.get("contexto", ""),
                           (f'{cond.get("pergunta", "")[:120]} = {cond.get("resposta", "")}' if cond else ""),
                           "todas" if v.get("allResponses") else ",".join(str(x) for x in v.get("respostaIds") or []),
                           v.get("motivo", "")])
        linhas.sort(key=lambda x: -x[2])
        with open(pad, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["grupo", "conceito", "painelistas_sim", "sim_fq", "sim_antigo", "painelistas_base",
                        "pergunta", "mae", "contexto", "condicao", "respostas_aceitas", "motivo"])
            w.writerows(linhas)
        res["csv"], res["csv_detalhado"], res["csv_padroes"] = out_csv, det, pad
        if com_base:
            bpath = _sufixo(out_csv, "_base")
            with open(bpath, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["painelistaid", "data_resposta", "fonte", "repositorio", "codjob", "codquestao",
                            "grupo", "sim"])
                w.writerows(sorted(set(base_rows)))
            res["csv_base"] = bpath
            res["base"] = len({r[0] for r in base_rows})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validated", default=os.path.join(os.getcwd(), "dados_tmp", "validado.json"))
    ap.add_argument("--grupos", default=os.path.join(os.getcwd(), "dados_tmp", "grupos.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--conceito", default=None, help="rótulo do conceito (julgamento multi-conceito)")
    ap.add_argument("--com-base", action="store_true",
                    help="grava também _base.csv: toda resposta aos padrões aceitos, com sim=1/0")
    a = ap.parse_args()
    r = resolve(a.validated, a.grupos, a.out, a.conceito, a.com_base)
    rot = f" [{a.conceito}]" if a.conceito else ""
    print(f"[PAINELISTAS]{rot} {r['painelistas']} (fq_ {r['so_fq'] + r['ambos']}, antigo {r['so_antigo'] + r['ambos']}, "
          f"nas duas {r['ambos']}, só no arquivo antigo {r['so_antigo']})")
    if a.out:
        print(f"[CSV] {r['csv']} (painelistaid,data_resposta,fonte)")
        print(f"[CSV_PADROES] {r['csv_padroes']} — de onde vem o número, um padrão por linha")
        print(f"[CSV_DETALHADO] {r['csv_detalhado']} — só entregar se pedirem")
        if a.com_base:
            print(f"[CSV_BASE] {r['csv_base']} — {r['base']} painelistas responderam os padrões (sim=1/0)")


if __name__ == "__main__":
    main()
