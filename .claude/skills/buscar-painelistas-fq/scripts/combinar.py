#!/usr/bin/env python3
"""Passo 7 (opcional): cortes e combinações entre conceitos — "só banda larga", "banda larga + TV + pós".

Lê os `_base.csv` do resolve (`--com-base`), um por conceito: toda resposta aos padrões aceitos,
com sim=1 (afirma o conceito) ou sim=0 (respondeu a pergunta e marcou outra coisa).

Regras:
  • ALGUMA VEZ: o conceito conta se a pessoa o afirmou em qualquer onda (é a contagem do resolve).
  • ESTADO ATUAL: para cada pessoa e conceito vale a ÚLTIMA onda (job) em que ela respondeu
    um padrão daquele conceito: sim se afirmou nessa onda, não se respondeu e não afirmou.
    Conceito nunca perguntado = desconhecido.
  • Combinação exata só para quem tem TODOS os conceitos conhecidos — um "só X" com algum
    conceito desconhecido não se sustenta (pode ter o outro e nunca ter sido perguntado).
  • DETALHE (--detalhe MOV=PRE,POS,CTRL): o detalhe sai da MESMA onda do estado atual do pai.
    Pai sim e nenhum detalhe afirmado nessa onda → "?" (ex.: plano desconhecido).

Imprime as camadas (alguma vez por conceito; detalhe; combinações de conceitos; combinações com
detalhe) e grava um CSV por painelista.

Uso:
  python "$SKILL/scripts/combinar.py" \
      --conceito BL="Banda Larga"=resultado_vivo_bl_base.csv \
      --conceito TV="TV"=resultado_vivo_tv_base.csv \
      --conceito MOV="Móvel"=resultado_vivo_mov_base.csv \
      --conceito PRE="Pré"=resultado_vivo_pre_base.csv \
      --conceito POS="Pós"=resultado_vivo_pos_base.csv \
      --conceito CTRL="Controle"=resultado_vivo_ctrl_base.csv \
      --detalhe MOV=PRE,POS,CTRL --out combinacoes_vivo.csv
"""
import csv
import argparse
import collections


def ler(caminho):
    """→ {pid: {job: [data, sim]}} — data e sim máximos por onda."""
    obs = collections.defaultdict(dict)
    with open(caminho, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            job = f'{r["fonte"]}|{r["repositorio"]}|{r["codjob"]}'
            o = obs[r["painelistaid"]].setdefault(job, ["", 0])
            o[0] = max(o[0], r["data_resposta"] or "")
            o[1] = max(o[1], int(r["sim"]))
    return obs


def fmt(n):
    return f"{n:,}".replace(",", ".")


def ultima(jobs):
    """Onda mais recente (empate: a que afirma)."""
    return max(jobs.items(), key=lambda kv: (kv[1][0], kv[1][1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conceito", action="append", required=True,
                    help='ROTULO="Nome"=arquivo_base.csv (repita por conceito)')
    ap.add_argument("--detalhe", action="append", default=[],
                    help="PAI=FILHO1,FILHO2,... (filhos também passados em --conceito)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    nomes, obs, ordem = {}, {}, []
    for spec in a.conceito:
        rot, nome, arq = spec.split("=", 2)
        nomes[rot] = nome; obs[rot] = ler(arq); ordem.append(rot)
    detalhe = {}
    for spec in a.detalhe:
        pai, filhos = spec.split("=", 1)
        detalhe[pai] = [x for x in filhos.split(",") if x]
    filhos = {f for fs in detalhe.values() for f in fs}
    principais = [r for r in ordem if r not in filhos]

    pids = sorted(set().union(*[set(o) for o in obs.values()]))
    alguma = {r: {p for p, js in obs[r].items() if any(s for _, s in js.values())} for r in ordem}

    print("=== CAMADA 1 — alguma vez (por conceito)")
    for r in principais:
        print(f"  {nomes[r]:<24} {fmt(len(alguma[r])):>9}")
    qualquer = set().union(*[alguma[r] for r in principais])
    print(f"  {'algum deles':<24} {fmt(len(qualquer)):>9}")
    for pai, fs in detalhe.items():
        print(f"=== CAMADA 2 — {nomes[pai]} por detalhe (alguma vez)")
        for f_ in fs:
            print(f"  {nomes[f_]:<24} {fmt(len(alguma[f_])):>9}")
        com = set().union(*[alguma[f_] for f_ in fs]) & alguma[pai]
        print(f"  {'com detalhe conhecido':<24} {fmt(len(com)):>9}")
        print(f"  {'sem detalhe':<24} {fmt(len(alguma[pai] - com)):>9}")

    linhas, c3, c4, parc = [], collections.Counter(), collections.Counter(), collections.Counter()
    for p in pids:
        est, det_txt = {}, {}
        for r in principais:
            js = obs[r].get(p)
            if not js:
                est[r] = None; continue
            job, (dt, s) = ultima(js)
            est[r] = bool(s)
            if s and r in detalhe:
                fs = [f_ for f_ in detalhe[r] if obs[f_].get(p, {}).get(job, ["", 0])[1]]
                det_txt[r] = "+".join(nomes[f_] for f_ in fs) or "?"
        sims = [r for r in principais if est[r]]
        desc = [nomes[r] for r in principais if est[r] is None]
        comb = " + ".join(nomes[r] for r in sims)
        comb_det = " + ".join(nomes[r] + (f" {det_txt[r]}" if r in det_txt else "") for r in sims)
        if sims and not desc:
            c3[comb] += 1; c4[comb_det] += 1
        elif sims:
            parc[(comb_det, "/".join(desc))] += 1
        if p in qualquer or sims:
            linhas.append([p] + [int(p in alguma[r]) for r in ordem]
                          + [comb or "(nenhum no estado atual)", comb_det or "(nenhum no estado atual)",
                             "/".join(desc) or "-"])

    print(f"=== CAMADA 3 — combinações de conceitos (estado atual, todos conhecidos: {fmt(sum(c3.values()))})")
    for k, v in c3.most_common():
        print(f"  {fmt(v):>9}  {k}")
    if detalhe:
        print("=== CAMADA 4 — combinações com detalhe (mesma base)")
        for k, v in c4.most_common():
            print(f"  {fmt(v):>9}  {k}")
    print(f"=== fora das camadas 3/4 — algum conceito nunca perguntado: {fmt(sum(parc.values()))}")
    for (k, d), v in parc.most_common(15):
        print(f"  {fmt(v):>9}  {k}   [sem info: {d}]")

    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["painelistaid"] + [f"{r.lower()}_alguma_vez" for r in ordem]
                       + ["combinacao", "combinacao_detalhe", "sem_info"])
            w.writerows(linhas)
        print(f"[CSV] {a.out} ({len(linhas)} painelistas)")


if __name__ == "__main__":
    main()
