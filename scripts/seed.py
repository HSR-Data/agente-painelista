#!/usr/bin/env python3
"""Passo 1 (seed): acha InfoIDs candidatos para um termo e grava um JSON compacto.

O subagente `painelista-filter` lê esse JSON e decide quais realmente indicam posse/uso.

Uso:
  python scripts/seed.py --termo "Nubank"
  python scripts/seed.py --termo "Nubank" --out dados_tmp/seed.json --max-infoids 2000
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from painelista_search import make_connection, like_pattern, build_seed_bundle, COLLATE

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "dados_tmp", "seed.json")


def _ph(n):
    return ", ".join(["?"] * n)


def fetch_and_build(term, limits):
    conn = make_connection()
    try:
        cur = conn.cursor()
        pat = like_pattern(term)

        cur.execute(
            f"SELECT InfoID, RespostaID, Valor FROM mapeamento_respostas "
            f"WHERE Label_resposta COLLATE {COLLATE} LIKE ? ESCAPE '\\' "
            f"   OR Valor COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat, pat))
        matched = [{"InfoID": r[0], "RespostaID": r[1], "Valor": r[2]} for r in cur.fetchall()]
        matched_ids = {m["InfoID"] for m in matched}

        cur.execute(
            f"SELECT DISTINCT InfoID FROM mapeamento_questoes "
            f"WHERE DescQuestaoPOR COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat,))
        question_infoids = {r[0] for r in cur.fetchall()}

        cur.execute(
            f"SELECT DISTINCT InfoID FROM mapeamento_info "
            f"WHERE Label COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat,))
        label_infoids = {r[0] for r in cur.fetchall()}

        candidate_ids = matched_ids | question_infoids | label_infoids
        if not candidate_ids:
            return build_seed_bundle(term, [], set(), set(), {}, {}, {}, {}, **limits), 0

        ids = sorted(candidate_ids)[:limits["max_infoids"]]
        kept = set(ids)
        ph = _ph(len(ids))

        cur.execute(f"SELECT InfoID, Label, Categoria FROM mapeamento_info WHERE InfoID IN ({ph})", ids)
        info_meta = {r[0]: {"Label": r[1], "Categoria": r[2]} for r in cur.fetchall()}

        cur.execute(f"SELECT DISTINCT InfoID, codJob, DescQuestaoPOR FROM mapeamento_questoes WHERE InfoID IN ({ph})", ids)
        questions_by_info = {}
        for r in cur.fetchall():
            iid, job, texto = r[0], r[1], r[2]
            if not texto:
                continue
            by_text = questions_by_info.setdefault(iid, {})
            entry = by_text.setdefault(texto, {"texto": texto, "codJobs": set()})
            if job is not None:
                entry["codJobs"].add(int(job))
        questions_by_info = {
            iid: [{"texto": e["texto"], "codJobs": sorted(e["codJobs"])} for e in by_text.values()]
            for iid, by_text in questions_by_info.items()
        }

        non_matched_ids = sorted((kept & (question_infoids | label_infoids)) - matched_ids)
        responses_by_info = {}
        if non_matched_ids:
            ph2 = _ph(len(non_matched_ids))
            cur.execute(f"SELECT InfoID, RespostaID, Valor FROM mapeamento_respostas WHERE InfoID IN ({ph2})", non_matched_ids)
            for r in cur.fetchall():
                responses_by_info.setdefault(r[0], []).append({"RespostaID": r[1], "Valor": r[2]})

        cur.execute(
            f"SELECT InfoID, RespostaID, COUNT(*) FROM tabela_respondentes "
            f"WHERE InfoID IN ({ph}) GROUP BY InfoID, RespostaID", ids)
        freq = {(r[0], r[1]): r[2] for r in cur.fetchall()}

        bundle = build_seed_bundle(term, matched, question_infoids, label_infoids,
                                   info_meta, questions_by_info, responses_by_info, freq, **limits)
        return bundle, len(candidate_ids)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termo", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--max-infoids", type=int, default=2000)
    ap.add_argument("--max-responses-per-infoid", type=int, default=5,
                    help="amostra de respostas NÃO casadas (só pra dar noção da escala)")
    ap.add_argument("--max-matched-per-infoid", type=int, default=30,
                    help="teto de respostas casadas por InfoID (abertas/recall chegam a centenas)")
    ap.add_argument("--max-text", type=int, default=400, help="tamanho máx de cada texto")
    ap.add_argument("--sample-questions", type=int, default=2)
    ap.add_argument("--max-questions-matched", type=int, default=10)
    a = ap.parse_args()

    limits = {"max_infoids": a.max_infoids,
              "max_responses_per_infoid": a.max_responses_per_infoid,
              "max_matched_per_infoid": a.max_matched_per_infoid,
              "max_text": a.max_text,
              "sample_questions": a.sample_questions,
              "max_questions_matched": a.max_questions_matched}
    bundle, total_bruto = fetch_and_build(a.termo, limits)

    if total_bruto == 0:
        print(f"[VAZIO] Nenhum InfoID casou com o termo '{a.termo}'. Tente outro termo.")
        return

    dropped = bundle["truncado"]["infoids_dropados"]
    if dropped > 0:
        print(f"[AVISO] {dropped} InfoIDs acima do teto --max-infoids={a.max_infoids} ficaram de fora. "
              f"Rode de novo com --max-infoids maior para cobrir todos ({total_bruto}).")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=1)
    print(f"[OK] {len(bundle['candidatos'])} InfoIDs candidatos gravados em {a.out} "
          f"(total bruto {total_bruto}).")


if __name__ == "__main__":
    main()
