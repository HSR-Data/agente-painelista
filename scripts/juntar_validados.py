#!/usr/bin/env python3
"""Junta os validados dos lotes num único validado.json.

Cada subagente julgou um lote; a decisão final é a UNIÃO das decisões. Se o mesmo
grupo aparecer em mais de um lote (não deveria, mas é barato garantir), o primeiro
aceite prevalece — e `allResponses` ganha de uma lista de respostas, por ser mais
abrangente.

Uso:
  python scripts/juntar_validados.py --entradas dados_tmp/validado_*.json
"""
import os
import sys
import json
import glob
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entradas", nargs="+",
                    default=[os.path.join(BASE, "dados_tmp", "validado_*.json")])
    ap.add_argument("--out", default=os.path.join(BASE, "dados_tmp", "validado.json"))
    a = ap.parse_args()

    arquivos = []
    for padrao in a.entradas:
        arquivos.extend(sorted(glob.glob(padrao)) if any(c in padrao for c in "*?[") else [padrao])
    arquivos = [f for f in arquivos if os.path.exists(f) and os.path.abspath(f) != os.path.abspath(a.out)]
    if not arquivos:
        sys.exit("Nenhum arquivo de lote encontrado.")

    por_grupo, termo, tc, ta, rej = {}, None, 0, 0, 0
    for f in arquivos:
        d = json.load(open(f, encoding="utf-8"))
        termo = termo or d.get("termo")
        tc += int(d.get("total_candidatos") or 0)
        ta += int(d.get("total_avaliados") or 0)
        rej += int((d.get("rejeitados_resumo") or {}).get("total") or 0)
        n_lote = 0
        for v in d.get("validados", []):
            g = v.get("grupo")
            if not g:
                continue
            n_lote += 1
            if g not in por_grupo or (v.get("allResponses") and not por_grupo[g].get("allResponses")):
                por_grupo[g] = v
        print(f"  {os.path.basename(f)}: {n_lote} aceitos")

    saida = {"termo": termo, "total_candidatos": tc, "total_avaliados": ta,
             "validados": list(por_grupo.values()),
             "rejeitados_resumo": {"total": rej, "padroes": ["ver validados por lote"]}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    print(f"[OK] {len(por_grupo)} grupos aceitos (de {ta}/{tc} avaliados) em {a.out}")
    if tc and ta < tc:
        print(f"[AVISO] cobertura parcial: {tc-ta} padrões não avaliados.")


if __name__ == "__main__":
    main()
