---
description: Descobre quantos respondentes/painelistas da base se encaixam num conceito (ex.: clientes Nubank) e gera CSV.
argument-hint: "<o que você quer buscar, em linguagem natural — ex.: pessoas que são clientes do Nubank>"
---

Pedido do usuário: **$ARGUMENTS**

Você vai descobrir quantos respondentes da base representam o conceito pedido, quantos são
painelistas Fala.e (têm PainelistaID/GUID) e, se o usuário quiser, gerar um CSV.

**Requisitos:** ambiente Python ativado + dependências instaladas + `.env` preenchido +
acesso ao SQL Server (VPN/rede conforme o `.env`). Veja o README se algo falhar.

O foco é sempre **puxar a PERGUNTA certa** (posse/uso real, não opinião/lembrança de propaganda).

## Passo 0 — Entender o pedido
Se **$ARGUMENTS** estiver vazio, pergunte ao usuário: *"O que você quer buscar? (ex.: pessoas que
assinam Netflix, clientes do Nubank)"* e aguarde a resposta.
Depois identifique:
- o **termo lexical** principal para o LIKE (ex.: "clientes do Nubank" → `Nubank`);
- a **intenção completa** (possui/usa hoje? não é ex-cliente? não é só avaliação/lembrança?).

## Passo 1 — Seed (busca candidatos no SQL)
```
python scripts/seed.py --termo "<TERMO>"
```
Repasse ao usuário a linha `[OK]` (quantos InfoIDs candidatos). **Não** leia o conteúdo do
`dados_tmp/seed.json` no seu contexto.
- Se vier `[VAZIO]`, avise que nada casou e sugira outro termo. Pare.
- Se vier `[AVISO]` de truncamento, **rode de novo com um teto maior** para cobrir todos:
  `python scripts/seed.py --termo "<TERMO>" --max-infoids <total_bruto+50>`.

## Passo 2 — Filtro semântico (subagente)
Dispare o subagente `painelista-filter` (Agent tool, subagent_type: "painelista-filter") passando:
o termo, a **intenção completa** do Passo 0, o caminho de entrada `dados_tmp/seed.json` e o de
saída `dados_tmp/validado.json`. Ele julga **pela pergunta** (não pelo label), captura os
`respostaIds`/`allResponses` **e os `codJobs`** das perguntas aprovadas, e retorna só um resumo.
**Não** carregue o seed JSON você mesmo. No retorno, confira que `total_avaliados == total_candidatos`;
se for menor, avise que a cobertura foi parcial antes de seguir.

## Passo 3 — Contagem (puxar o número)
```
python scripts/resolve.py --validated dados_tmp/validado.json
```
Isso imprime `respondentes_totais=<N> | com_painelistaid=<M>`. **Reporte ao usuário nesse formato:**
- **Respondentes totais:** N
- **Com PainelistaID (painelistas Fala.e):** M
- (sem PainelistaID: N − M)

E um resumo curto de quais InfoIDs o subagente aceitou/rejeitou (do retorno do Passo 2).

## Passo 4 — Oferecer CSV
Pergunte ao usuário: *"Quer o CSV com o resultado? (s/n)"*. Se **sim**:
```
python scripts/resolve.py --validated dados_tmp/validado.json --out resultado_<termo>.csv
```
Informe o caminho do CSV e que as colunas são `id, painelistaid, codjob, infoid`
(uma linha por respondente × tema × pesquisa; `painelistaid` fica vazio quando o respondente
não é painelista Fala.e).
