#!/usr/bin/env python3
"""Passo 1 (seed): acha PADRÕES de pergunta candidatos para um termo, em DUAS fontes.

  fq_      cópia fiel e atual do FastQuest (fq_questao, fq_questao_opcao, fq_resposta,
           fq_cliente). Só tem painelistas (CodClienteCAWI = PainelistaID). Texto
           preservado, inclusive os tokens `$FUNCAO_MIDIA(VIVO)` que são a opção da marca.
  antigo   tabelas do pipeline anterior (perguntas, respostas, respondentes): arquivo
           congelado das ondas que o FastQuest JÁ APAGOU. Texto limpo — e o limpador
           apagou os `$FUNCAO_MIDIA(...)`, então muitas opções de marca ficaram vazias.

Em cada fonte o termo é buscado em três lugares (opção/resposta, pergunta, mãe do grid).

As duas fontes viram UM conjunto de padrões: a chave é o texto normalizado
(pergunta + mãe + contexto), então "Qual a empresa da sua internet banda larga fixa?"
de uma onda de 2026 (fq_) e de uma onda de 2025 (antigo) caem no mesmo padrão e o
subagente julga uma vez só.

TRANSFERÊNCIA: perguntas antigas com opções de texto vazio (o `$FUNCAO_MIDIA` apagado)
nunca casam o termo. Elas entram como membro do padrão fq_ de mesmo texto, e a opção
é ligada pelo CÓDIGO (respostas.CodResposta = fq_questao_opcao.Opcao). Foi assim que
o P10C "VIVO" (código 4012) das ondas apagadas foi recuperado.

CONTEXTO: no FQ a filha de grid traz só o rótulo da linha ("Vivo") e a mãe costuma ter
texto vazio; o enunciado real está na pergunta raiz anterior ("Na sua residência, você
ou alguém possui serviços de outras operadoras?"). Ela vai no campo `contexto`.

CONDICIONAIS: muitas perguntas não citam a marca — citam a RESPOSTA de outra pergunta
(`{RU("OPERADORA_AVA").Selecionada().Descricao()}`, "Nesta sua linha da {RU("P8")...}, qual
o tipo de plano?"). Se a pergunta referida (X, mesmo questionário) tem opção que casa o termo,
a pergunta vira um padrão CONDICIONAL: o placeholder é trocado pela opção ("VIVO") e só contam
os respondentes que marcaram essa opção em X. Foi assim que saíram os planos (pré/pós/controle)
da linha Vivo e a banda larga de quem avaliou a Vivo — antes, só cruzando à mão.

IDs de opção no seed são LOCAIS ao padrão (1..n): a mesma opção tem códigos/IDs
diferentes em cada pesquisa. O resolve traduz a decisão por texto (e por código).

Gera:
  dados_tmp/seed.json    padrões a julgar (vai para o subagente)
  dados_tmp/grupos.json  padrão → opções locais + membros das duas fontes (usado pelo resolve)

Uso:
  python "$SKILL/scripts/seed.py" --termo "Vivo"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# antes de hashlib: o config.py define OPENSSL_CONF, que o OpenSSL só lê no primeiro uso
from painelista_search import make_connection, like_pattern, COLLATE

import re
import json
import hashlib
import argparse
import unicodedata
import time

_T0 = time.time()


def etapa(msg):
    print(f"  [{time.time() - _T0:6.0f}s] {msg}", file=sys.stderr, flush=True)

BASE = os.getcwd()
DEFAULT_OUT = os.path.join(BASE, "dados_tmp", "seed.json")
DEFAULT_GRUPOS = os.path.join(BASE, "dados_tmp", "grupos.json")

MIDIA = re.compile(r'\{?\$FUNCAO_MIDIA\(\s*"?([^";,)]*)[^)]*\)\}?', re.I)
CHAVES = re.compile(r'\{[^{}]*\}')


def _ascii(t):
    t = unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()
    return t


def norm_q(t):
    """Texto de pergunta para agrupar entre fontes: sem mídia, sem {placeholders},
    sem acento, só letras e dígitos. O limpador antigo e o _sem_html diferem em espaços,
    pontuação e tokens — isto iguala os dois."""
    t = MIDIA.sub(" ", t or "")
    t = CHAVES.sub(" ", t)
    return re.sub(r"[^a-z0-9]+", "", _ascii(t))


def norm_o(t):
    """Texto de opção: o token de mídia VIRA o nome da marca ($FUNCAO_MIDIA(VIVO) → vivo)."""
    t = MIDIA.sub(lambda m: " " + m.group(1) + " ", t or "")
    return re.sub(r"[^a-z0-9]+", " ", _ascii(t)).strip()


def chave_grupo(pergunta, mae, contexto):
    base = norm_q(pergunta) + "||" + norm_q(mae) + "||" + norm_q(contexto)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _usa_contexto(pergunta, mae, eh_filha):
    """Contexto só quando o enunciado próprio não basta: filha de grid com mãe vazia,
    ou pergunta sem texto."""
    return (eh_filha and not norm_q(mae)) or not norm_q(pergunta)


def resolver_ru(texto, nr, rotulo):
    """Troca o placeholder que cita RU("nr") pela opção escolhida ("VIVO"). Placeholders
    aninhados ({var op = RU("X")...; if(...){...}}) sobram em parte e caem no CHAVES."""
    if not texto:
        return texto or ""
    alvo = re.compile(r'\{[^{}]*RU\("' + re.escape(nr) + r'"\)[^{}]*\}')
    novo = alvo.sub(rotulo, texto)
    if novo == texto:   # RU fora de chaves
        novo = texto.replace(f'RU("{nr}")', rotulo)
    return novo


def rotulo_opcao(t):
    """Texto de opção para leitura: $FUNCAO_MIDIA(VIVO) -> VIVO."""
    return re.sub(r"\s+", " ", MIDIA.sub(lambda m: " " + m.group(1) + " ", t or "")).strip()


# ─────────────────────────────── fq_ ────────────────────────────────

def buscar_fq(cur, pat):
    cur.execute(f"""SELECT DISTINCT fq_version, repositorio, CodQuestao FROM fq_questao_opcao
                    WHERE DescOpcaoPOR_sem_html COLLATE {COLLATE} LIKE ? ESCAPE '\\'""", (pat,))
    por_resposta = {tuple(r) for r in cur.fetchall()}
    cur.execute(f"""SELECT fq_version, repositorio, CodQuestao FROM fq_questao
                    WHERE DescQuestaoPOR_sem_html COLLATE {COLLATE} LIKE ? ESCAPE '\\'""", (pat,))
    por_pergunta = {tuple(r) for r in cur.fetchall()}
    cur.execute(f"""SELECT f.fq_version, f.repositorio, f.CodQuestao FROM fq_questao f
                    JOIN fq_questao m ON m.fq_version=f.fq_version AND m.repositorio=f.repositorio
                                     AND m.CodQuestao=f.CodQuestaoPrincipal
                    WHERE m.DescQuestaoPOR_sem_html COLLATE {COLLATE} LIKE ? ESCAPE '\\'""", (pat,))
    por_mae = {tuple(r) for r in cur.fetchall()}
    chaves = por_resposta | por_pergunta | por_mae
    etapa(f"fq_: {len(chaves)} perguntas casaram; lendo enunciados e volumes")
    if not chaves:
        return {}
    det = buscar_fq_detalhes(cur, chaves, pat)
    out = {}
    for k in chaves:
        m = det.get(k)
        if not m:
            continue
        marcas = [x for x, s in (("resposta", por_resposta), ("pergunta", por_pergunta),
                                 ("mae", por_mae)) if k in s]
        out[k] = dict(m, casou_por=marcas)
    return out


def buscar_fq_detalhes(cur, chaves, pat, T="#fc"):
    """Enunciado, mãe, contexto, volume e opções (com frequência) de um conjunto de perguntas fq_.
    `T` = nome da tabela temporária (a função roda mais de uma vez na mesma conexão)."""
    cur.execute(f"CREATE TABLE {T} (fq_version TINYINT, repositorio VARCHAR(128), CodQuestao INT, "
                "PRIMARY KEY (fq_version, repositorio, CodQuestao))")
    cur.fast_executemany = True
    cur.executemany(f"INSERT INTO {T} VALUES (?, ?, ?)", [(int(v), r, int(q)) for v, r, q in chaves])

    # enunciado, mãe e contexto (raiz anterior com texto no mesmo questionário)
    cur.execute(f"""
        SELECT p.fq_version, p.repositorio, p.CodQuestao, p.CodTipoQuestao, p.CodQuestaoPrincipal,
               p.DescQuestaoPOR_sem_html, m.DescQuestaoPOR_sem_html, ctx.t
        FROM fq_questao p JOIN {T} c ON c.fq_version=p.fq_version AND c.repositorio=p.repositorio
                                     AND c.CodQuestao=p.CodQuestao
        LEFT JOIN fq_questao m ON m.fq_version=p.fq_version AND m.repositorio=p.repositorio
                              AND m.CodQuestao=p.CodQuestaoPrincipal
        OUTER APPLY (SELECT TOP 1 x.DescQuestaoPOR_sem_html t FROM fq_questao x
                     WHERE x.fq_version=p.fq_version AND x.repositorio=p.repositorio
                       AND x.CodQuestionario=p.CodQuestionario AND x.CodQuestaoPrincipal IS NULL
                       AND x.CodQuestao < ISNULL(p.CodQuestaoPrincipal, p.CodQuestao)
                       AND LEN(x.DescQuestaoPOR_sem_html) > 0
                     ORDER BY x.CodQuestao DESC) ctx""")
    meta = {}
    for v, r, q, tipo, princ, perg, mae, ctx in cur.fetchall():
        meta[(v, r, q)] = {"tipo": tipo, "pergunta": perg or "", "mae": mae or "",
                           "contexto": ctx or "", "filha": princ is not None}

    # volume: painelistas que responderam a pergunta (fq_ só tem painelistas)
    cur.execute(f"""SELECT r.fq_version, r.repositorio, r.CodQuestao, COUNT(DISTINCT r.CodCliente)
                   FROM fq_resposta r JOIN {T} c ON c.fq_version=r.fq_version
                        AND c.repositorio=r.repositorio AND c.CodQuestao=r.CodQuestao
                   GROUP BY r.fq_version, r.repositorio, r.CodQuestao""")
    vol = {(v, r, q): int(n) for v, r, q, n in cur.fetchall()}

    # opções com frequência: resposta fechada guarda o código da opção em Parte;
    # ParteHash está no índice IX_fq_resposta_questao (chave do clustered), então é barato.
    cur.execute(f"""SELECT r.fq_version, r.repositorio, r.CodQuestao, r.ParteHash, COUNT(*) n INTO {T}_ff
                   FROM fq_resposta r JOIN {T} c ON c.fq_version=r.fq_version
                        AND c.repositorio=r.repositorio AND c.CodQuestao=r.CodQuestao
                   GROUP BY r.fq_version, r.repositorio, r.CodQuestao, r.ParteHash""")
    cur.execute(f"CREATE CLUSTERED INDEX ix ON {T}_ff (fq_version, repositorio, CodQuestao, ParteHash)")
    # _fo criada antes: SELECT INTO com parâmetro roda num sp_prepexec e a tabela some no fim dele
    cur.execute(f"CREATE TABLE {T}_fo (fq_version TINYINT, repositorio VARCHAR(128), CodQuestao INT, Opcao INT, "
                "DescOpcaoPOR_sem_html NVARCHAR(4000), flagExclusivo BIT, casou INT, h VARBINARY(32))")
    cur.execute(f"""
        INSERT INTO {T}_fo
        SELECT o.fq_version, o.repositorio, o.CodQuestao, o.Opcao, o.DescOpcaoPOR_sem_html, o.flagExclusivo,
               CASE WHEN o.DescOpcaoPOR_sem_html COLLATE {COLLATE} LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END casou,
               HASHBYTES('SHA2_256', CAST(CAST(o.Opcao AS NVARCHAR(20)) AS NVARCHAR(MAX))) h
        FROM fq_questao_opcao o JOIN {T} c ON c.fq_version=o.fq_version
             AND c.repositorio=o.repositorio AND c.CodQuestao=o.CodQuestao""", (pat,))
    cur.execute(f"""SELECT o.fq_version, o.repositorio, o.CodQuestao, o.Opcao, o.DescOpcaoPOR_sem_html,
                          o.flagExclusivo, ISNULL(f.n, 0), o.casou
                   FROM {T}_fo o LEFT JOIN {T}_ff f ON f.fq_version=o.fq_version AND f.repositorio=o.repositorio
                        AND f.CodQuestao=o.CodQuestao AND f.ParteHash=o.h""")
    opcoes = {}
    for v, r, q, op, txt, excl, n, casou in cur.fetchall():
        opcoes.setdefault((v, r, q), []).append(
            {"cod": int(op), "texto": txt or "", "excl": bool(excl), "freq": int(n), "casou": bool(casou)})

    out = {}
    for k in chaves:
        m = meta.get(k)
        if m:
            out[k] = dict(m, volume=vol.get(k, 0), opcoes=opcoes.get(k, []))
    return out


# ────────────────────────────── antigo ──────────────────────────────

_SQL_META_ANTIGO = """
    SELECT p.codJob, p.CodQuestao, p.CodTipoQuestao, p.CodQuestaoPrincipal,
           CAST(p.TextoPergunta AS NVARCHAR(MAX)), CAST(m.TextoPergunta AS NVARCHAR(MAX)),
           CAST(ctx.t AS NVARCHAR(MAX))
    FROM perguntas p JOIN {tab} c ON c.codJob=p.codJob AND c.CodQuestao=p.CodQuestao
    LEFT JOIN perguntas m ON m.codJob=p.codJob AND m.CodQuestao=p.CodQuestaoPrincipal
    OUTER APPLY (SELECT TOP 1 x.TextoPergunta t FROM perguntas x
                 WHERE x.codJob=p.codJob AND x.CodQuestaoPrincipal IS NULL
                   AND x.CodQuestao < ISNULL(p.CodQuestaoPrincipal, p.CodQuestao)
                   AND LEN(CAST(x.TextoPergunta AS NVARCHAR(4000))) > 0
                 ORDER BY x.CodQuestao DESC) ctx"""


def _meta_antigo(cur, tab):
    cur.execute(_SQL_META_ANTIGO.format(tab=tab))
    return {(j, q): {"tipo": tipo, "pergunta": perg or "", "mae": mae or "", "contexto": ctx or "",
                     "filha": princ is not None}
            for j, q, tipo, princ, perg, mae, ctx in cur.fetchall()}


def _opcoes_antigo(cur, tab, pat):
    cur.execute(f"""SELECT d.RespostaID, COUNT(*) FROM respondentes d
                    JOIN {tab} c ON c.codJob=d.codJob AND c.CodQuestao=d.CodQuestao
                    GROUP BY d.RespostaID""")
    freqs = {int(r): int(n) for r, n in cur.fetchall()}
    cur.execute(f"""SELECT r.codJob, r.CodQuestao, r.RespostaID, r.CodResposta,
                           CAST(r.TextoResposta AS NVARCHAR(400)), r.flagExclusivo, r.aberta,
                           CASE WHEN r.TextoResposta COLLATE {COLLATE} LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END
                    FROM respostas r JOIN {tab} c ON c.codJob=r.codJob AND c.CodQuestao=r.CodQuestao""",
                (pat,))
    out = {}
    for j, q, rid, cod, txt, excl, aberta, casou in cur.fetchall():
        out.setdefault((j, q), []).append(
            {"rid": int(rid), "cod": None if cod is None else int(cod), "texto": txt or "",
             "excl": bool(excl), "aberta": bool(aberta), "freq": freqs.get(int(rid), 0),
             "casou": bool(casou)})
    return out


def _volume_antigo(cur, tab):
    cur.execute(f"""SELECT d.codJob, d.CodQuestao, COUNT(DISTINCT d.PainelistaID) FROM respondentes d
                    JOIN {tab} c ON c.codJob=d.codJob AND c.CodQuestao=d.CodQuestao
                    GROUP BY d.codJob, d.CodQuestao""")
    return {(j, q): int(n) for j, q, n in cur.fetchall()}


def buscar_antigo(cur, pat):
    cur.execute(f"SELECT codJob, CodQuestao FROM perguntas "
                f"WHERE TextoPergunta COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat,))
    por_pergunta = {tuple(r) for r in cur.fetchall()}
    cur.execute(f"SELECT DISTINCT codJob, CodQuestao FROM respostas "
                f"WHERE TextoResposta COLLATE {COLLATE} LIKE ? ESCAPE '\\'", (pat,))
    por_resposta = {tuple(r) for r in cur.fetchall()}
    cur.execute(f"""SELECT f.codJob, f.CodQuestao FROM perguntas f
                    JOIN perguntas m ON m.codJob=f.codJob AND m.CodQuestao=f.CodQuestaoPrincipal
                    WHERE m.TextoPergunta COLLATE {COLLATE} LIKE ? ESCAPE '\\'""", (pat,))
    por_mae = {tuple(r) for r in cur.fetchall()}
    chaves = por_pergunta | por_resposta | por_mae
    if not chaves:
        return {}
    cur.execute("CREATE TABLE #ac (codJob INT, CodQuestao INT, PRIMARY KEY (codJob, CodQuestao))")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO #ac VALUES (?, ?)", [(int(j), int(q)) for j, q in chaves])
    meta, ops, vol = _meta_antigo(cur, "#ac"), _opcoes_antigo(cur, "#ac", pat), _volume_antigo(cur, "#ac")
    out = {}
    for k in chaves:
        if k not in meta:
            continue
        marcas = [x for x, s in (("resposta", por_resposta), ("pergunta", por_pergunta),
                                 ("mae", por_mae)) if k in s]
        out[k] = dict(meta[k], volume=vol.get(k, 0), opcoes=ops.get(k, []), casou_por=marcas)
    return out


def antigos_sem_texto(cur, pat, ja):
    """Perguntas antigas com opção fechada de texto vazio (mídia apagada pelo limpador).
    Candidatas à transferência por código; quem já veio pela busca do termo fica de fora."""
    cur.execute("""SELECT DISTINCT codJob, CodQuestao INTO #av FROM respostas
                   WHERE aberta = 0 AND (TextoResposta IS NULL OR LTRIM(CAST(TextoResposta AS NVARCHAR(400))) = '')""")
    cur.execute("ALTER TABLE #av ADD PRIMARY KEY (codJob, CodQuestao)")
    meta = _meta_antigo(cur, "#av")
    return {k: v for k, v in meta.items() if k not in ja}, cur


# ─────────────────────────── condicionais ────────────────────────────

def buscar_condicionais_fq(cur, fq):
    """Perguntas D que citam RU("X"), onde X (mesmo questionário) tem opção que casou o termo."""
    xs = [(v, r, q, o["cod"], o["texto"]) for (v, r, q), m in fq.items() if "resposta" in m["casou_por"]
          for o in m["opcoes"] if o["casou"]]
    if not xs:
        return {}
    cur.execute("CREATE TABLE #cx (fq_version TINYINT, repositorio VARCHAR(128), CodQuestao INT, Opcao INT, "
                "txt NVARCHAR(400), h VARBINARY(32))")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO #cx (fq_version, repositorio, CodQuestao, Opcao, txt) VALUES (?, ?, ?, ?, ?)",
                    [(int(v), r, int(q), int(c), (t or "")[:400]) for v, r, q, c, t in xs])
    cur.execute("UPDATE #cx SET h = HASHBYTES('SHA2_256', CAST(CAST(Opcao AS NVARCHAR(20)) AS NVARCHAR(MAX)))")
    cur.execute("""SELECT DISTINCT x.fq_version, x.repositorio, x.CodQuestionario, x.CodQuestao, x.nrQuestao,
                          x.DescQuestaoPOR_sem_html INTO #cxq
                   FROM fq_questao x JOIN (SELECT DISTINCT fq_version, repositorio, CodQuestao FROM #cx) c
                     ON c.fq_version=x.fq_version AND c.repositorio=x.repositorio AND c.CodQuestao=x.CodQuestao
                   WHERE LEN(x.nrQuestao) > 0""")
    # D: texto próprio ou da mãe cita RU("<nrQuestao de X>")
    cur.execute("""SELECT d.fq_version, d.repositorio, d.CodQuestao dq, x.CodQuestao xq, x.nrQuestao,
                          x.DescQuestaoPOR_sem_html xtxt INTO #cd
                   FROM fq_questao d
                   LEFT JOIN fq_questao dm ON dm.fq_version=d.fq_version AND dm.repositorio=d.repositorio
                                          AND dm.CodQuestao=d.CodQuestaoPrincipal
                   JOIN #cxq x ON x.fq_version=d.fq_version AND x.repositorio=d.repositorio
                              AND x.CodQuestionario=d.CodQuestionario AND x.CodQuestao<>d.CodQuestao
                   WHERE (d.DescQuestaoPOR_sem_html LIKE '%RU("%' OR dm.DescQuestaoPOR_sem_html LIKE '%RU("%')
                     AND (CHARINDEX('RU("' + x.nrQuestao + '")', d.DescQuestaoPOR_sem_html) > 0
                          OR CHARINDEX('RU("' + x.nrQuestao + '")', ISNULL(dm.DescQuestaoPOR_sem_html, '')) > 0)""")
    pares = cur.execute("SELECT fq_version, repositorio, dq, xq, nrQuestao, xtxt FROM #cd").fetchall()
    if not pares:
        return {}
    etapa(f"condicionais fq_: {len(pares)} pares pergunta->referida")
    # volume condicionado: quem respondeu D e marcou a opção do termo em X
    cur.execute("""SELECT d.fq_version, d.repositorio, d.dq, c.Opcao, COUNT(DISTINCT rd.CodCliente)
                   FROM #cd d JOIN #cx c ON c.fq_version=d.fq_version AND c.repositorio=d.repositorio AND c.CodQuestao=d.xq
                   JOIN fq_resposta rx ON rx.fq_version=c.fq_version AND rx.repositorio=c.repositorio
                                      AND rx.CodQuestao=c.CodQuestao AND rx.ParteHash=c.h
                   JOIN fq_resposta rd ON rd.fq_version=d.fq_version AND rd.repositorio=d.repositorio
                                      AND rd.CodQuestao=d.dq AND rd.CodCliente=rx.CodCliente
                   GROUP BY d.fq_version, d.repositorio, d.dq, c.Opcao""")
    vol = {(v, r, q, int(o)): int(n) for v, r, q, o, n in cur.fetchall()}
    dkeys = {(v, r, dq) for v, r, dq, *_ in pares}
    det = buscar_fq_detalhes(cur, dkeys, None, "#dc2")
    xops = {}
    for v, r, q, c, t in xs:
        xops.setdefault((v, r, q), []).append((c, t))
    out = {}
    for v, r, dq, xq, nr, xtxt in pares:
        m = det.get((v, r, dq))
        if not m:
            continue
        for cod, t in xops.get((v, r, xq), []):
            n = vol.get((v, r, dq, int(cod)), 0)
            if not n:
                continue
            rot = rotulo_opcao(t)
            out[(v, r, dq, xq, int(cod))] = dict(
                m, pergunta=resolver_ru(m["pergunta"], nr, rot), mae=resolver_ru(m["mae"], nr, rot),
                volume=n, casou_por=["condicao"],
                cond={"q": xq, "cods": [int(cod)], "nr": nr, "pergunta": xtxt or "", "resposta": rot})
    return out


def buscar_condicionais_antigo(cur, antigo):
    xs = [(j, q, o["rid"], o["texto"]) for (j, q), m in antigo.items() if "resposta" in m["casou_por"]
          for o in m["opcoes"] if o["casou"] and not o["aberta"]]
    if not xs:
        return {}
    cur.execute("CREATE TABLE #ox (codJob INT, CodQuestao INT, RespostaID BIGINT)")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO #ox VALUES (?, ?, ?)", [(int(j), int(q), int(rid)) for j, q, rid, _ in xs])
    # só nos jobs que têm pergunta referida, e só perguntas que citam RU(" — o CHARINDEX por par é caro
    cur.execute("""SELECT d.codJob, d.CodQuestao,
                          CAST(d.TextoPergunta AS NVARCHAR(MAX)) + N' ' + CAST(ISNULL(dm.TextoPergunta, '') AS NVARCHAR(MAX)) t
                   INTO #oru
                   FROM perguntas d
                   LEFT JOIN perguntas dm ON dm.codJob=d.codJob AND dm.CodQuestao=d.CodQuestaoPrincipal
                   WHERE d.codJob IN (SELECT DISTINCT codJob FROM #ox)
                     AND (d.TextoPergunta LIKE '%RU("%' OR dm.TextoPergunta LIKE '%RU("%')""")
    cur.execute("""SELECT d.codJob, d.CodQuestao dq, x.CodQuestao xq, x.nrQuestao,
                          CAST(x.TextoPergunta AS NVARCHAR(4000)) xtxt INTO #od
                   FROM #oru d
                   JOIN perguntas x ON x.codJob=d.codJob AND x.CodQuestao<>d.CodQuestao AND LEN(x.nrQuestao) > 0
                   JOIN (SELECT DISTINCT codJob, CodQuestao FROM #ox) o ON o.codJob=x.codJob AND o.CodQuestao=x.CodQuestao
                   WHERE CHARINDEX('RU("' + x.nrQuestao + '")', d.t) > 0""")
    pares = cur.execute("SELECT codJob, dq, xq, nrQuestao, xtxt FROM #od").fetchall()
    if not pares:
        return {}
    etapa(f"condicionais antigo: {len(pares)} pares pergunta->referida")
    cur.execute("""SELECT d.codJob, d.dq, o.RespostaID, COUNT(DISTINCT rd.PainelistaID)
                   FROM #od d JOIN #ox o ON o.codJob=d.codJob AND o.CodQuestao=d.xq
                   JOIN respondentes rx ON rx.codJob=o.codJob AND rx.CodQuestao=o.CodQuestao AND rx.RespostaID=o.RespostaID
                   JOIN respondentes rd ON rd.codJob=d.codJob AND rd.CodQuestao=d.dq AND rd.CodCliente=rx.CodCliente
                   GROUP BY d.codJob, d.dq, o.RespostaID""")
    vol = {(j, q, int(rid)): int(n) for j, q, rid, n in cur.fetchall()}
    cur.execute("CREATE TABLE #odk (codJob INT, CodQuestao INT, PRIMARY KEY (codJob, CodQuestao))")
    cur.executemany("INSERT INTO #odk VALUES (?, ?)", sorted({(int(j), int(dq)) for j, dq, *_ in pares}))
    meta, ops = _meta_antigo(cur, "#odk"), _opcoes_antigo(cur, "#odk", None)
    xops = {}
    for j, q, rid, t in xs:
        xops.setdefault((j, q), []).append((rid, t))
    out = {}
    for j, dq, xq, nr, xtxt in pares:
        m = meta.get((j, dq))
        if not m:
            continue
        for rid, t in xops.get((j, xq), []):
            n = vol.get((j, dq, int(rid)), 0)
            if not n:
                continue
            rot = rotulo_opcao(t)
            out[(j, dq, xq, int(rid))] = dict(
                m, pergunta=resolver_ru(m["pergunta"], nr, rot), mae=resolver_ru(m["mae"], nr, rot),
                volume=n, opcoes=[o for o in ops.get((j, dq), []) if not o["aberta"]], casou_por=["condicao"],
                cond={"q": xq, "rids": [int(rid)], "nr": nr, "pergunta": xtxt or "", "resposta": rot})
    return out


# ───────────────────────────── padrões ──────────────────────────────

def _chave(m):
    ctx = m["contexto"] if _usa_contexto(m["pergunta"], m["mae"], m["filha"]) else ""
    return chave_grupo(m["pergunta"], m["mae"], ctx), ctx


def _chave_cond(m):
    """Padrão condicional: o texto resolvido + a pergunta referida + a opção escolhida nela."""
    gid, ctx = _chave(m)
    base = gid + "|cond|" + norm_q(m["cond"]["pergunta"]) + "=" + norm_o(m["cond"]["resposta"])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16], ctx


def montar(term, fq, antigo, sem_texto, cur, pat, max_respostas, max_text, incluir_abertas,
           cond_fq=None, cond_antigo=None):
    grupos, descartados = {}, 0

    def novo(gid, m, ctx):
        g = grupos.setdefault(gid, {
            "grupo": gid, "tipo": m["tipo"], "pergunta": m["pergunta"], "mae": m["mae"],
            "contexto": ctx, "casou_por": set(), "fontes": set(), "respondentes": 0,
            "n_perguntas": 0, "_membros": []})
        if m.get("cond") and "condicao" not in g:
            g["condicao"] = {"pergunta": m["cond"]["pergunta"], "resposta": m["cond"]["resposta"]}
        return g

    for (v, r, q), m in fq.items():
        gid, ctx = _chave(m)
        g = novo(gid, m, ctx)
        g["casou_por"] |= set(m["casou_por"]); g["fontes"].add("fq_")
        g["respondentes"] += m["volume"]; g["n_perguntas"] += 1
        g["_membros"].append({"fonte": "fq_", "fq_version": v, "repositorio": r, "CodQuestao": q,
                              "volume": m["volume"], "opcoes": m["opcoes"]})

    for (j, q), m in antigo.items():
        casadas = [o for o in m["opcoes"] if o["casou"]]
        # Posse vem de opção fechada; termo só em texto livre é quase sempre recall.
        if casadas and all(o["aberta"] for o in casadas) and not incluir_abertas \
                and not ({"pergunta", "mae"} & set(m["casou_por"])):
            descartados += 1
            continue
        gid, ctx = _chave(m)
        g = novo(gid, m, ctx)
        g["casou_por"] |= set(m["casou_por"]); g["fontes"].add("antigo")
        g["respondentes"] += m["volume"]; g["n_perguntas"] += 1
        g["_membros"].append({"fonte": "antigo", "codJob": j, "CodQuestao": q,
                              "volume": m["volume"], "opcoes": [o for o in m["opcoes"] if not o["aberta"]] + casadas_abertas(m)})

    # transferência: antigas sem texto de opção que têm o MESMO enunciado de um padrão fq_
    transf = {}
    for k, m in sem_texto.items():
        gid, _ = _chave(m)
        if gid in grupos and "fq_" in grupos[gid]["fontes"]:
            transf[k] = gid
    if transf:
        cur.execute("CREATE TABLE #at (codJob INT, CodQuestao INT, PRIMARY KEY (codJob, CodQuestao))")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #at VALUES (?, ?)", [(int(j), int(q)) for j, q in transf])
        ops, vol = _opcoes_antigo(cur, "#at", pat), _volume_antigo(cur, "#at")
        for (j, q), gid in transf.items():
            g = grupos[gid]
            g["fontes"].add("antigo"); g["respondentes"] += vol.get((j, q), 0); g["n_perguntas"] += 1
            g["_membros"].append({"fonte": "antigo", "codJob": j, "CodQuestao": q, "transferido": True,
                                  "volume": vol.get((j, q), 0),
                                  "opcoes": [o for o in ops.get((j, q), []) if not o["aberta"]]})

    # condicionais: membro = pergunta D + condição (opção do termo na pergunta referida X)
    for (v, r, dq, xq, cod), m in (cond_fq or {}).items():
        gid, ctx = _chave_cond(m)
        g = novo(gid, m, ctx)
        g["casou_por"].add("condicao"); g["fontes"].add("fq_")
        g["respondentes"] += m["volume"]; g["n_perguntas"] += 1
        g["_membros"].append({"fonte": "fq_", "fq_version": v, "repositorio": r, "CodQuestao": dq,
                              "volume": m["volume"], "opcoes": m["opcoes"],
                              "cond": {"q": xq, "cods": m["cond"]["cods"]}})
    for (j, dq, xq, rid), m in (cond_antigo or {}).items():
        gid, ctx = _chave_cond(m)
        g = novo(gid, m, ctx)
        g["casou_por"].add("condicao"); g["fontes"].add("antigo")
        g["respondentes"] += m["volume"]; g["n_perguntas"] += 1
        g["_membros"].append({"fonte": "antigo", "codJob": j, "CodQuestao": dq,
                              "volume": m["volume"], "opcoes": m["opcoes"],
                              "cond": {"q": xq, "rids": m["cond"]["rids"]}})

    seed_c, mapa = [], {}
    for g in sorted(grupos.values(), key=lambda x: x["respondentes"], reverse=True):
        locais = opcoes_locais(g["_membros"])
        casadas = [o for o in locais if o["casou"]]
        outras = [o for o in locais if not o["casou"]]
        seed_c.append({
            "grupo": g["grupo"], "tipo": g["tipo"],
            "pergunta": g["pergunta"][:max_text], "mae": g["mae"][:max_text],
            "contexto": g["contexto"][:max_text],
            "casou_por": sorted(g["casou_por"]), "fontes": sorted(g["fontes"]),
            "respondentes": g["respondentes"], "n_perguntas": g["n_perguntas"],
            "respostas_match": [_res(o) for o in sorted(casadas, key=lambda o: -o["freq"])[:max_respostas]],
            "respostas_amostra": [_res(o) for o in sorted(outras, key=lambda o: -o["freq"])[:max_respostas]],
        })
        if g.get("condicao"):
            seed_c[-1]["condicao"] = {"pergunta": g["condicao"]["pergunta"][:max_text],
                                      "resposta": g["condicao"]["resposta"][:120]}
        mapa[g["grupo"]] = {
            "opcoes": {str(o["id"]): {"t": o["t"], "cods": sorted(o["cods"]), "casou": o["casou"]}
                       for o in locais},
            "membros": [_membro_compacto(mb) for mb in g["_membros"]],
            # textos, só para o relatório por padrão do resolve (_padroes.csv)
            "pergunta": g["pergunta"][:300], "mae": g["mae"][:200], "contexto": g["contexto"][:200],
            "condicao": g.get("condicao"),
        }
    seed = {"termo": term, "total": len(seed_c), "descartados_so_texto_aberto": descartados,
            "candidatos": seed_c}
    return seed, mapa, len(transf)


def casadas_abertas(m):
    return [o for o in m["opcoes"] if o["aberta"] and o["casou"]]


def opcoes_locais(membros):
    """Une as opções de todos os membros por texto normalizado e dá a cada uma um id local.
    Opção antiga de texto vazio junta-se à opção de mesmo código vinda do fq_."""
    por_texto, por_cod, lst = {}, {}, []
    pend = []
    for mb in membros:
        for o in mb["opcoes"]:
            t = norm_o(o["texto"])
            if not t:
                pend.append(o)
                continue
            loc = por_texto.get(t)
            if not loc:
                loc = {"id": len(lst) + 1, "t": t, "texto": o["texto"], "cods": set(), "freq": 0,
                       "casou": False, "excl": False, "aberta": False}
                por_texto[t] = loc; lst.append(loc)
            if o.get("cod") is not None:
                loc["cods"].add(o["cod"]); por_cod.setdefault(o["cod"], loc)
            loc["freq"] += o["freq"]; loc["casou"] |= o["casou"]
            loc["excl"] |= o["excl"]; loc["aberta"] |= o.get("aberta", False)
    for o in pend:
        loc = por_cod.get(o.get("cod"))
        if not loc:
            t = f"(sem texto, codigo {o.get('cod')})"
            loc = por_texto.get(t)
            if not loc:
                loc = {"id": len(lst) + 1, "t": t, "texto": t, "cods": set(), "freq": 0,
                       "casou": False, "excl": False, "aberta": False}
                por_texto[t] = loc; lst.append(loc)
                if o.get("cod") is not None:
                    loc["cods"].add(o["cod"])
        loc["freq"] += o["freq"]
    return lst


def _membro_compacto(mb):
    if mb["fonte"] == "fq_":
        d = {"fonte": "fq_", "v": mb["fq_version"], "repo": mb["repositorio"], "q": mb["CodQuestao"],
             "ops": [[o["cod"], norm_o(o["texto"]), int(o["casou"])] for o in mb["opcoes"]]}
    else:
        d = {"fonte": "antigo", "job": mb["codJob"], "q": mb["CodQuestao"],
             "ops": [[o["rid"], o["cod"], norm_o(o["texto"]), int(o["casou"])] for o in mb["opcoes"]]}
    if mb.get("cond"):
        d["cond"] = mb["cond"]     # fq_: {"q", "cods"}; antigo: {"q", "rids"}
    return d


def _res(o):
    r = {"RespostaID": o["id"], "texto": o["texto"][:200], "freq": o["freq"]}
    if o["excl"]:
        r["exclusiva"] = 1
    if o["aberta"]:
        r["aberta"] = 1
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termo", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--grupos", default=DEFAULT_GRUPOS)
    ap.add_argument("--max-respostas", type=int, default=25)
    ap.add_argument("--max-text", type=int, default=400)
    ap.add_argument("--incluir-abertas", action="store_true",
                    help="Antigo: inclui padrões cujo termo aparece só em texto livre (verbatim).")
    a = ap.parse_args()

    pat = like_pattern(a.termo)
    conn = make_connection()
    try:
        cur = conn.cursor()
        etapa("fq_: buscando")
        fq = buscar_fq(cur, pat)
        etapa(f"fq_: {len(fq)} perguntas; antigo: buscando")
        antigo = buscar_antigo(cur, pat)
        if not fq and not antigo:
            print(f"[VAZIO] Nenhuma pergunta/resposta casou com '{a.termo}'.")
            return
        etapa(f"antigo: {len(antigo)} perguntas; antigas sem texto de opcao")
        sem_texto, cur = antigos_sem_texto(cur, pat, set(antigo))
        etapa(f"{len(sem_texto)} antigas sem texto; condicionais")
        cond_fq = buscar_condicionais_fq(cur, fq)
        cond_antigo = buscar_condicionais_antigo(cur, antigo)
        etapa(f"condicionais: {len(cond_fq)} fq_, {len(cond_antigo)} antigo; montando padroes")
        seed, mapa, n_transf = montar(a.termo, fq, antigo, sem_texto, cur, pat,
                                      a.max_respostas, a.max_text, a.incluir_abertas,
                                      cond_fq, cond_antigo)
    finally:
        conn.close()

    if seed["descartados_so_texto_aberto"]:
        print(f"[INFO] {seed['descartados_so_texto_aberto']} perguntas antigas descartadas por casarem "
              f"só em texto livre (verbatim). Use --incluir-abertas para trazê-las.")
    for caminho, dados in ((a.out, seed), (a.grupos, mapa)):
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
    print(f"[OK] {seed['total']} PADRÕES em {a.out} — perguntas: {len(fq)} fq_, {len(antigo)} antigo, "
          f"{n_transf} antigo transferidas por código, {len(cond_fq) + len(cond_antigo)} condicionais")
    print(f"     membros de cada padrão em {a.grupos}")


if __name__ == "__main__":
    main()
