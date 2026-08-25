#!/usr/bin/env python3
"""Divide o seed em lotes, para julgamento por subagentes em PARALELO.

Motivação: julgar ~1.500 padrões numa única tarefa degrada a qualidade — a tarefa
atravessa o limite de contexto, o subagente precisa reler o arquivo e passa a errar.
Na prática isso gerou falso negativo em pergunta obviamente de posse
("qual sua principal conta de investimentos → Nubank" foi rejeitada).

Lotes menores mantêm cada subagente dentro de uma carga confortável.

A distribuição é ROUND-ROBIN sobre a ordem por volume: assim cada lote recebe uma
mistura de padrões grandes e pequenos, em vez de um lote só com os gigantes.

Uso:
  python scripts/dividir_seed.py --lotes 6
"""
import os
import sys
import json
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=os.path.join(BASE, "dados_tmp", "seed.json"))
    ap.add_argument("--lotes", type=int, default=6)
    ap.add_argument("--prefixo", default=os.path.join(BASE, "dados_tmp", "lote"))
    a = ap.parse_args()

    seed = json.load(open(a.seed, encoding="utf-8"))
    cands = seed["candidatos"]          # já vem ordenado por volume (desc)
    n = max(1, min(a.lotes, len(cands)))

    baldes = [[] for _ in range(n)]
    for i, c in enumerate(cands):
        baldes[i % n].append(c)         # round-robin: equilibra volume entre lotes

    for i, b in enumerate(baldes, 1):
        caminho = f"{a.prefixo}_{i}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"termo": seed["termo"], "lote": i, "de": n,
                       "total": len(b), "candidatos": b}, f, ensure_ascii=False, indent=1)
        vol = sum(x.get("respondentes", 0) for x in b)
        print(f"  lote {i}/{n}: {len(b):>4} padrões | volume {vol:>12,} | {caminho}")
    print(f"[OK] {len(cands)} padrões divididos em {n} lotes.")


if __name__ == "__main__":
    main()
