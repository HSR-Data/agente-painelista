#!/usr/bin/env python3
"""Passo 3 (resolve): das perguntas/respostas validadas -> contagem e CSV.

Reporta DOIS números, porque medem coisas diferentes:

  • respondentes  = CodCliente distintos (código do respondente no FastQuest)
  • painelistas   = PainelistaID distintos (pessoas do painel Fala.e)

A distinção importa: na base, 5,6 milhões de CodClientes correspondem a ~525 mil
painelistas — cada pessoa participa de várias pesquisas e recebe um novo código de
respondente em cada uma. Para "quantas PESSOAS do painel", o número correto é o de
painelistas; contar CodCliente infla o resultado em ~4x.

Com --out, grava CSV: id, painelistaid, codjob, codquestao, codresposta

Uso:
  python "$SKILL/scripts/resolve.py" --validated dados_tmp/validado.json
  python "$SKILL/scripts/resolve.py" --validated dados_tmp/validado.json --out resultado.csv
"""
import os
import sys
import json
import csv
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from painelista_search import make_connection, parse_validated

# Casa uma linha de respondentes com algum par validado.
# A chave (codJob, CodQuestao) já é específica de uma pergunta numa pesquisa —
# não é preciso ancorar por job à parte, como o modelo antigo exigia.
MATCH = ("EXISTS (SELECT 1 FROM #validados v "
         "WHERE v.codJob = d.codJob AND v.CodQuestao = d.CodQuestao "
         "AND (v.AllResp = 1 OR v.RespostaID = d.RespostaID))")


def expandir(validado, grupos):
    """Traduz decisões por PADRÃO em pares (codJob, CodQuestao, RespostaID) concretos.

    O subagente julga o texto da pergunta uma vez; aqui a decisão é aplicada a todos os
    pares que compartilham aquele padrão (a mesma pergunta se repete em centenas de
    pesquisas). Para `respostaIds`, usamos os RespostaIDs que casaram o termo EM CADA
    membro — os IDs são por (job, questão), então não dá para reaproveitar os do exemplo.
    """
    itens = []
    for v in validado.get("validados", []):
        gid = v.get("grupo")
        membros = grupos.get(gid, [])
        if not membros:
            continue
        todas = bool(v.get("allResponses"))
        # IDs escolhidos no exemplo: usados para saber SE a decisão foi por resposta casada
        escolhidos = set(int(x) for x in v.get("respostaIds", []) or [])
        for m in membros:
            if todas:
                itens.append({"codJob": m["codJob"], "CodQuestao": m["CodQuestao"],
                              "respostaIds": None, "allResponses": True})
                continue
            # sem allResponses: aceita as respostas que casaram o termo neste membro,
            # mais eventuais IDs do exemplo que pertençam a ele (grid com escala)
            ids = list(dict.fromkeys(list(m.get("match", [])) +
                                     [i for i in m.get("todas", []) if i in escolhidos]))
            if ids:
                itens.append({"codJob": m["codJob"], "CodQuestao": m["CodQuestao"],
                              "respostaIds": ids, "allResponses": False})
    return itens


def _data(v):
    """Data em ISO curto (YYYY-MM-DD HH:MM); vazio se ausente."""
    return "" if v is None else str(v)[:16]


def _sufixo(caminho, suf):
    raiz, ext = os.path.splitext(caminho)
    return f"{raiz}{suf}{ext or '.csv'}"


def _carregar(cur, itens):
    cur.execute("CREATE TABLE #validados (codJob INT, CodQuestao INT, "
                "RespostaID BIGINT NULL, AllResp BIT)")
    linhas = []
    for it in itens:
        if it["allResponses"]:
            linhas.append((it["codJob"], it["CodQuestao"], None, 1))
        else:
            for rid in it["respostaIds"]:
                linhas.append((it["codJob"], it["CodQuestao"], rid, 0))
    if linhas:
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #validados (codJob, CodQuestao, RespostaID, AllResp) "
                        "VALUES (?, ?, ?, ?)", linhas)
    return len(linhas)


def resolve(validated_path, out_csv=None, grupos_path=None):
    with open(validated_path, encoding="utf-8") as f:
        data = json.load(f)
    if grupos_path and os.path.exists(grupos_path):
        with open(grupos_path, encoding="utf-8") as f:
            itens = expandir(data, json.load(f))
    else:
        itens = parse_validated(data)
    if not itens:
        return {"respondentes": 0, "painelistas": 0, "linhas_csv": 0, "pares": 0}

    conn = make_connection()
    try:
        cur = conn.cursor()
        pares = _carregar(cur, itens)

        cur.execute(f"""
            SELECT COUNT(DISTINCT d.CodCliente),
                   COUNT(DISTINCT d.PainelistaID)
            FROM respondentes d WHERE {MATCH}""")
        resp, pain = cur.fetchone()
        res = {"respondentes": int(resp or 0), "painelistas": int(pain or 0),
               "linhas_csv": 0, "pares": pares}

        if out_csv:
            # UMA LINHA POR PAINELISTA, com a data da resposta MAIS RECENTE.
            # ROW_NUMBER resolve empates de forma determinística (mesma data em jobs
            # diferentes): fica a de codJob/CodQuestao maior, sempre a mesma linha.
            cur.execute(f"""
                WITH base AS (
                    SELECT d.PainelistaID, d.DataResposta, d.codJob, d.CodQuestao,
                           ROW_NUMBER() OVER (PARTITION BY d.PainelistaID
                                              ORDER BY d.DataResposta DESC,
                                                       d.codJob DESC, d.CodQuestao DESC) rn
                    FROM respondentes d
                    WHERE {MATCH} AND d.PainelistaID IS NOT NULL
                )
                SELECT PainelistaID, DataResposta, codJob, CodQuestao
                FROM base WHERE rn = 1""")
            linhas = cur.fetchall()

            os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
            with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["painelistaid", "data_resposta"])
                for r in linhas:
                    w.writerow([r[0], _data(r[1])])
            res["linhas_csv"] = len(linhas)

            # Versão detalhada: mesmas linhas + de onde veio aquela resposta.
            # Gerada junto porque sai de graça (a consulta já foi feita) e evita
            # nova espera se alguém pedir depois — mas só uma minoria precisa disso.
            det = _sufixo(out_csv, "_detalhado")
            with open(det, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["painelistaid", "data_resposta", "codjob", "codquestao"])
                for r in linhas:
                    w.writerow([r[0], _data(r[1]), r[2], r[3]])
            res["csv_detalhado"] = det
        return res
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validated", required=True)
    ap.add_argument("--grupos", default=os.path.join(
        os.getcwd(), "dados_tmp", "grupos.json"),
        help="Mapa padrão→membros gerado pelo seed.")
    ap.add_argument("--out", default=None,
                    help="CSV de saída (painelistaid,data_resposta). Gera também o _detalhado.csv (+codjob,codquestao).")
    a = ap.parse_args()

    r = resolve(a.validated, a.out, grupos_path=a.grupos)
    print(f"[PAINELISTAS] {r['painelistas']}")
    print(f"[RESPONDENTES] {r['respondentes']} (inclui não-painelistas; não são pessoas contáveis)")
    if a.out:
        print(f"[CSV] {r['linhas_csv']} linhas em {a.out} (painelistaid,data_resposta)")
        if r.get("csv_detalhado"):
            print(f"[CSV_DETALHADO] {r['csv_detalhado']} (+codjob,codquestao) "
                  f"— só entregar se pedirem")


if __name__ == "__main__":
    main()
