#!/usr/bin/env python3
"""Divide o seed em lotes, para julgamento por subagentes em PARALELO.

Motivação: julgar ~1.500 padrões numa única tarefa degrada a qualidade — a tarefa
atravessa o limite de contexto, o subagente precisa reler o arquivo e passa a errar.

A distribuição é ROUND-ROBIN sobre a ordem por volume: assim cada lote recebe uma
mistura de padrões grandes e pequenos, em vez de um lote só com os gigantes.

FORMATO: um candidato por LINHA, JSON compacto. Com `indent`, um lote de 250 padrões
passava de 20.000 linhas e estourava o `limit` do Read do subagente, que caía em
leitura por blocos — custo quadrático (o contexto é reenviado a cada turno) e perda
de cobertura. Uma linha por candidato mantém o lote em ~250 linhas: uma leitura só.

Payload enxuto e pré-filtro determinístico vêm LIGADOS. Para desligar (depuração):
--gordo          mantém o payload cru, com tudo que o julgamento não usa
--sem-prefiltro  manda ao LLM até o que a regra rejeitaria sempre

Uso:
  python scripts/dividir_seed.py --lotes 4
"""
import os
import re
import unicodedata
import sys
import json
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- sugestão 3: regras determinísticas -------------------------------------
# Rótulo interno de script: não é frase natural, não afirma posse por si só.
ROTULO = re.compile(r'^(GRAVA|PAVAL|COTA|PLAYER|PERFIL|AMOSTRA|EXTERNO|BANCO[_ ]?(FRASE|\d)|Q\d+_)', re.I)
# Recall de propaganda: lembrança de anúncio nunca é posse.
PROPAGANDA = re.compile(r'propaganda|an[uú]ncio|comercial de|publicidade|lembra de ter visto|patroc[ií]nio', re.I)
# Preferência e posse-de-empresa: dois falsos positivos medidos, que custaram 1.361
# painelistas indevidos. Tentei ensinar isso ao modelo e saiu pior — ele ficou conservador
# em tudo e perdeu 1.517 painelistas legítimos. Como regra em Python é cirúrgico e grátis.
PREFERENCIA = re.compile(r'prefer[ie]|predile|se pudesse escolher|consideraria', re.I)
EMPRESA = re.compile(r'(sua|da) empresa (possui|tem|utiliza)|a empresa possui', re.I)
# Verbo de posse: se aparecer, o LLM decide — regra nenhuma descarta.
# `client` solto de propósito: rótulos de cota ("Cliente Nubank", "Backbook - Cliente
# Nubank") e respostas como "Eu já sou cliente Nubank" afirmam posse sem verbo algum.
# Inclusive "Não Cliente Nubank" cai aqui — e deve mesmo: quem decide o sinal é o LLM,
# a regra só escolhe o que NÃO vale a pena mandar pra ele.
POSSE = re.compile(r'possui|client|tem conta|têm conta|utiliza|usa |contrat|'
                   r'banco principal|principal.*(conta|cartão|banco)|relacionamento com|'
                   r'recebe sal|investe|assina', re.I)


def motivo_descarte(c):
    """Retorna o motivo do descarte determinístico, ou None para manter."""
    if not c.get("respondentes"):
        return "0 respondentes"          # nunca soma um painelista, mesmo se aceito
    # Inclui o texto das respostas que casaram: em rótulo de script o verbo costuma
    # estar na resposta ("Clientes Nubank", "Já uso no Nubank PJ"), não no enunciado.
    # NFC: o banco devolve acento decomposto (E + U+0301). Sem normalizar, um regex
    # com "é" nunca casa — e a regra falha em silêncio, deixando passar/descartando errado.
    texto = unicodedata.normalize("NFC", " ".join(
        [c.get("mae") or "", c.get("pergunta") or ""]
        + [r.get("texto", "") for r in c.get("respostas_match", [])]).strip())
    if ROTULO.match(unicodedata.normalize("NFC", (c.get("mae") or c.get("pergunta") or "").strip())) and not POSSE.search(texto):
        return "rotulo de script"   # "GRAVA BANCOS QUE É CLIENTE" tem prefixo de script MAS afirma posse
    enunciado = unicodedata.normalize("NFC", ((c.get("mae") or "") + " " + (c.get("pergunta") or "")))
    # Propaganda: o guarda de posse olha SÓ o enunciado, nunca as respostas. Numa pergunta
    # aberta de recall os verbatins citam "cliente" por acaso ("a propaganda é boa, sou
    # cliente há anos") e isso deixava passar 92 padrões — 34% do payload, dos quais a
    # referência aceitou 2. O enunciado é que decide se a pergunta mede posse.
    # Casos legítimos continuam passando porque o verbo está no próprio enunciado:
    # "Após ver essa propaganda, você quis se tornar cliente Nubank?"
    if PROPAGANDA.search(texto) and not POSSE.search(enunciado):
        return "recall de propaganda"
    if PREFERENCIA.search(enunciado):
        return "preferencia, nao posse"
    if EMPRESA.search(enunciado):
        return "posse da empresa, nao do respondente"
    return None


def enxugar(c):
    """Mantém os nomes de campo, corta o que o julgamento não usa.

    `respostas_amostra` era 52% do payload e carregava RespostaID/freq de respostas
    que NÃO casaram — o subagente nunca precisa desses IDs, só do texto, para saber
    que tipo de pergunta é. Fica `outras_opcoes`: 5 textos, sem ID, sem freq.
    """
    # NFC em tudo: o banco devolve acento decomposto, que gasta ~9% mais tokens e
    # ainda quebra regex. Normalizar é economia grátis.
    def n(x, lim):
        return unicodedata.normalize("NFC", x or "")[:lim]

    return {
        "grupo": c["grupo"],
        "tipo": c.get("tipo"),
        "respondentes": c.get("respondentes"),
        "casou_por": c.get("casou_por"),
        "pergunta": n(c.get("pergunta"), 300),
        "mae": n(c.get("mae"), 200),
        # par [RespostaID, texto] em vez de objeto: as chaves repetidas custavam 28
        # caracteres por resposta, e são 4,6 respostas por candidato em média.
        "match": [[r["RespostaID"], n(r["texto"], 80)] for r in c.get("respostas_match", [])],
        "outras_opcoes": [n(r["texto"], 40) for r in c.get("respostas_amostra", [])[:5]],
    }
    # Cortar mais que isto foi testado e sai caro: com `respondentes`/`casou_por` fora,
    # textos em 60 e 3 outras_opcoes, os agentes ficaram mais agressivos e rejeitaram
    # 39 padrões legítimos ("Principal Conta Pessoa Física (CPF)" -> Nubank), custando
    # 1.291 painelistas. O payload não é o gargalo; o custo fixo por subagente é.


def gravar(caminho, cabecalho, candidatos):
    """Um candidato por linha — JSON válido, ~N+3 linhas em vez de ~20.000."""
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(json.dumps(cabecalho, ensure_ascii=False)[:-1] + ',"candidatos":[\n')
        for i, c in enumerate(candidatos):
            f.write(json.dumps(c, ensure_ascii=False, separators=(",", ":")))
            f.write(",\n" if i < len(candidatos) - 1 else "\n")
        f.write("]}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=os.path.join(BASE, "dados_tmp", "seed.json"))
    ap.add_argument("--lotes", type=int, default=6)
    ap.add_argument("--prefixo", default=os.path.join(BASE, "dados_tmp", "lote"))
    ap.add_argument("--gordo", dest="enxuto", action="store_false", default=True)
    ap.add_argument("--sem-prefiltro", dest="prefiltro", action="store_false", default=True)
    a = ap.parse_args()

    seed = json.load(open(a.seed, encoding="utf-8"))
    cands = seed["candidatos"]          # já vem ordenado por volume (desc)

    descartados = {}
    if a.prefiltro:
        mantidos = []
        for c in cands:
            m = motivo_descarte(c)
            if m:
                descartados.setdefault(m, []).append(c["grupo"])
            else:
                mantidos.append(c)
        for m, gs in sorted(descartados.items(), key=lambda x: -len(x[1])):
            print(f"  [prefiltro] {len(gs):>4} descartados: {m}")
        print(f"  [prefiltro] {len(cands)} -> {len(mantidos)} candidatos para o LLM")
        with open(os.path.join(BASE, "dados_tmp", "prefiltrados.json"), "w", encoding="utf-8") as f:
            json.dump({"total": len(cands) - len(mantidos), "por_motivo": {k: len(v) for k, v in descartados.items()},
                       "grupos": descartados}, f, ensure_ascii=False, indent=1)
        cands = mantidos

    if a.enxuto:
        cands = [enxugar(c) for c in cands]

    n = max(1, min(a.lotes, len(cands)))
    baldes = [[] for _ in range(n)]
    for i, c in enumerate(cands):
        baldes[i % n].append(c)         # round-robin: equilibra volume entre lotes

    for i, b in enumerate(baldes, 1):
        caminho = f"{a.prefixo}_{i}.json"
        gravar(caminho, {"termo": seed["termo"], "lote": i, "de": n, "total": len(b)}, b)
        vol = sum(x.get("respondentes", 0) for x in b)
        kb = os.path.getsize(caminho) / 1024
        linhas = len(b) + 2
        print(f"  lote {i}/{n}: {len(b):>4} padrões | volume {vol:>12,} | {kb:>6.0f} KB | {linhas:>5} linhas")
    print(f"[OK] {len(cands)} padrões divididos em {n} lotes.")


if __name__ == "__main__":
    main()
