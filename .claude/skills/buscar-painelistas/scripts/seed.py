#!/usr/bin/env python3
"""Passo 1 (seed): acha PADRÕES de pergunta candidatos para um termo.

Busca o termo em TRÊS lugares, porque cada um cobre um caso que os outros perdem:

  1. respostas.TextoResposta  — "Quais streamings você assina? ☑ Netflix"
  2. perguntas.TextoPergunta  — "Você é usuário Netflix?" com respostas só "Sim/Não";
                                aqui o termo NUNCA aparece na resposta.
  3. pergunta-mãe do grid     — grid "avalie sua satisfação" cuja FILHA é "NETFLIX".

AGRUPAMENTO: a mesma pergunta se repete em centenas de pesquisas (medido: 26.127 pares
(codJob,CodQuestao) para "Nubank", mas apenas 1.003 textos distintos). O subagente julga
o TEXTO uma vez e a decisão vale para todos os pares daquele padrão — cobertura de 100%
sem truncar, e julgamento consistente entre pesquisas.

Gera dois arquivos:
  seed.json    → padrões a julgar (vai para o subagente)
  grupos.json  → padrão → membros (codJob, CodQuestao, RespostaIDs) — usado pelo resolve

Uso:
  python "$SKILL/scripts/seed.py" --termo "Nubank"
  python "$SKILL/scripts/seed.py" --termo "Netflix" --incluir-abertas
"""
import os
import re
import sys
import json
import hashlib
import argparse
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from painelista_search import make_connection, like_pattern, COLLATE

BASE = os.getcwd()
DEFAULT_OUT = os.path.join(BASE, "dados_tmp", "seed.json")
DEFAULT_GRUPOS = os.path.join(BASE, "dados_tmp", "grupos.json")


def norm(t: str) -> str:
    """Normaliza texto para agrupar: sem acento, minúsculo, espaços colapsados."""
    t = (t or "").strip().lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t)


def chave_grupo(pergunta, mae, textos_casados):
    """Identidade do padrão: pergunta + mãe + quais respostas casaram.

    A mãe entra porque filha de grid costuma ter texto curto ou vazio — sem ela,
    perguntas completamente diferentes cairiam no mesmo grupo. As respostas casadas
    entram porque a mesma pergunta com opções diferentes é um caso diferente.
    """
    base = norm(pergunta) + "||" + norm(mae) + "||" + "|".join(sorted(norm(t) for t in textos_casados))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def buscar(term, max_respostas, max_text, incluir_abertas=False):
    conn = make_connection()
    try:
        cur = conn.cursor()
        pat = like_pattern(term)

        cur.execute(f"SELECT codJob, CodQuestao FROM perguntas "
                    f"WHERE TextoPergunta COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat,))
        por_pergunta = {(r[0], r[1]) for r in cur.fetchall()}

        cur.execute(f"SELECT DISTINCT codJob, CodQuestao FROM respostas "
                    f"WHERE TextoResposta COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat,))
        por_resposta = {(r[0], r[1]) for r in cur.fetchall()}

        cur.execute(f"""
            SELECT f.codJob, f.CodQuestao
            FROM perguntas f
            JOIN perguntas m ON m.codJob = f.codJob AND m.CodQuestao = f.CodQuestaoPrincipal
            WHERE f.CodQuestaoPrincipal IS NOT NULL
              AND m.TextoPergunta COLLATE {COLLATE} LIKE ? ESCAPE '\\'""", (pat,))
        por_mae = {(r[0], r[1]) for r in cur.fetchall()}

        chaves = por_pergunta | por_resposta | por_mae
        if not chaves:
            return None, None, 0

        cur.execute("CREATE TABLE #cand (codJob INT, CodQuestao INT)")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #cand VALUES (?, ?)", [(int(j), int(q)) for j, q in chaves])

        cur.execute("""
            SELECT p.codJob, p.CodQuestao, p.CodTipoQuestao,
                   CAST(p.TextoPergunta AS NVARCHAR(MAX)),
                   CAST(m.TextoPergunta AS NVARCHAR(MAX))
            FROM perguntas p
            JOIN #cand c ON c.codJob = p.codJob AND c.CodQuestao = p.CodQuestao
            LEFT JOIN perguntas m ON m.codJob = p.codJob AND m.CodQuestao = p.CodQuestaoPrincipal""")
        meta = {(r[0], r[1]): {"tipo": r[2], "pergunta": r[3] or "", "mae": r[4] or ""}
                for r in cur.fetchall()}

        # Volume em agregações únicas: subquery por candidato é inviável em centenas
        # de milhões de linhas (o JOIN com #cand usa o prefixo da PK, então é seek).
        cur.execute("""SELECT d.codJob, d.CodQuestao, COUNT(*) FROM respondentes d
                       JOIN #cand c ON c.codJob=d.codJob AND c.CodQuestao=d.CodQuestao
                       GROUP BY d.codJob, d.CodQuestao""")
        vol = {(r[0], r[1]): int(r[2] or 0) for r in cur.fetchall()}

        cur.execute("""SELECT d.RespostaID, COUNT(*) FROM respondentes d
                       JOIN #cand c ON c.codJob=d.codJob AND c.CodQuestao=d.CodQuestao
                       GROUP BY d.RespostaID""")
        freqs = {int(r[0]): int(r[1] or 0) for r in cur.fetchall()}

        cur.execute(f"""
            SELECT r.codJob, r.CodQuestao, r.RespostaID, CAST(r.TextoResposta AS NVARCHAR(MAX)),
                   r.flagExclusivo, r.aberta,
                   CASE WHEN r.TextoResposta COLLATE {COLLATE} LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END
            FROM respostas r
            JOIN #cand c ON c.codJob = r.codJob AND c.CodQuestao = r.CodQuestao""", (pat,))
        respostas = {}
        for j, qs, rid, txt, excl, aberta, casou in cur.fetchall():
            respostas.setdefault((j, qs), []).append(
                {"RespostaID": int(rid), "texto": (txt or "")[:max_text],
                 "freq": freqs.get(int(rid), 0), "excl": bool(excl),
                 "aberta": bool(aberta), "casou": bool(casou)})

        # ── agrupa por padrão ────────────────────────────────────────────
        grupos, descartados = {}, 0
        for chave in chaves:
            m = meta.get(chave)
            if not m:
                continue
            todas = sorted(respostas.get(chave, []), key=lambda x: x["freq"], reverse=True)
            casadas = [r for r in todas if r["casou"]]

            # Posse vem de OPÇÃO FECHADA. Termo só em texto livre é quase sempre
            # verbatim de recall ("lembro da propaganda") — 75% dos casos na base.
            if casadas and all(r["aberta"] for r in casadas) and not incluir_abertas \
                    and "pergunta" not in _marcas(chave, por_resposta, por_pergunta, por_mae) \
                    and "mae" not in _marcas(chave, por_resposta, por_pergunta, por_mae):
                descartados += 1
                continue

            gid = chave_grupo(m["pergunta"], m["mae"], [r["texto"] for r in casadas])
            g = grupos.setdefault(gid, {
                "grupo": gid, "tipo": m["tipo"], "pergunta": m["pergunta"], "mae": m["mae"],
                "casou_por": set(), "respondentes": 0, "n_perguntas": 0,
                "respostas_match": [], "respostas_amostra": [], "_membros": [],
            })
            g["casou_por"] |= set(_marcas(chave, por_resposta, por_pergunta, por_mae))
            g["respondentes"] += vol.get(chave, 0)
            g["n_perguntas"] += 1
            g["_membros"].append({"codJob": chave[0], "CodQuestao": chave[1],
                                  "match": [r["RespostaID"] for r in casadas],
                                  "todas": [r["RespostaID"] for r in todas]})
            if not g["respostas_match"]:      # amostra do 1º membro representa o padrão
                g["respostas_match"] = [_res(r) for r in casadas[:max_respostas]]
                g["respostas_amostra"] = [_res(r) for r in todas if not r["casou"]][:max_respostas]

        ordenados = sorted(grupos.values(), key=lambda g: g["respondentes"], reverse=True)
        seed = {"termo": term, "total": len(ordenados),
                "descartados_so_texto_aberto": descartados,
                "candidatos": [{k: (sorted(v) if isinstance(v, set) else v)
                                for k, v in g.items() if k != "_membros"} for g in ordenados]}
        mapa = {g["grupo"]: g["_membros"] for g in ordenados}
        return seed, mapa, len(chaves)
    finally:
        conn.close()


def _marcas(chave, por_resposta, por_pergunta, por_mae):
    m = []
    if chave in por_resposta:
        m.append("resposta")
    if chave in por_pergunta:
        m.append("pergunta")
    if chave in por_mae:
        m.append("mae")
    return m


def _res(r):
    o = {"RespostaID": r["RespostaID"], "texto": r["texto"], "freq": r["freq"]}
    if r["excl"]:
        o["exclusiva"] = 1
    if r["aberta"]:
        o["aberta"] = 1
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termo", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--grupos", default=DEFAULT_GRUPOS)
    ap.add_argument("--max-respostas", type=int, default=25)
    ap.add_argument("--max-text", type=int, default=400)
    ap.add_argument("--incluir-abertas", action="store_true",
                    help="Inclui padrões cujo termo aparece só em texto livre (verbatim).")
    a = ap.parse_args()

    seed, mapa, bruto = buscar(a.termo, a.max_respostas, a.max_text, a.incluir_abertas)
    if not bruto:
        print(f"[VAZIO] Nenhuma pergunta/resposta casou com '{a.termo}'.")
        return

    if seed["descartados_so_texto_aberto"]:
        print(f"[INFO] {seed['descartados_so_texto_aberto']} perguntas descartadas por casarem "
              f"só em texto livre (verbatim). Use --incluir-abertas para trazê-las.")
    for caminho, dados in ((a.out, seed), (a.grupos, mapa)):
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
    print(f"[OK] {seed['total']} PADRÕES de pergunta (de {bruto} pares job/questão) em {a.out}")
    print(f"     membros de cada padrão em {a.grupos}")


if __name__ == "__main__":
    main()
