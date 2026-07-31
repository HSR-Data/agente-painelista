---
name: buscar-painelistas
description: Conta quantos respondentes/painelistas da base se encaixam num conceito de posse/uso (ex.: clientes do Nubank, quem assina Netflix, possuidores de seguro) e, se o usuário quiser, gera um CSV. Use quando o usuário quiser saber o tamanho de um público na base ou exportar esses respondentes.
---

# Buscar Painelistas

Descubra **quantos respondentes da base representam o conceito pedido**, quantos são painelistas
Fala.e (têm PainelistaID/GUID) e, se o usuário quiser, gere um **CSV**.

**Requisitos:** rodar a partir da raiz do projeto, com ambiente Python ativado, dependências
instaladas, o arquivo `.env` na pasta e acesso ao SQL Server (VPN/rede conforme o `.env`).
Se algo falhar, veja o `README.md`.

O foco é sempre **puxar a PERGUNTA certa** — posse/uso real, **não** opinião nem lembrança de
propaganda.

## Passo 0 — Entender o pedido
Pegue o conceito da mensagem do usuário. Se não veio nenhum conceito, pergunte: *"O que você quer
buscar? (ex.: pessoas que assinam Netflix, clientes do Nubank)"* e aguarde a resposta.
Depois identifique:
- o **termo lexical** principal para o LIKE (ex.: "clientes do Nubank" → `Nubank`);
- a **intenção completa** (possui/usa hoje? não é ex-cliente? não é só avaliação/lembrança?).

## Passo 1 — Seed (busca candidatos no SQL)
```
python scripts/seed.py --termo "<TERMO>"
```
Repasse ao usuário a linha `[OK]` (quantos InfoIDs candidatos). **Não** leia o conteúdo do
`dados_tmp/seed.json` no seu contexto — ele é grande.
- Se vier `[VAZIO]`, avise que nada casou e sugira outro termo. Pare.
- Se vier `[AVISO]` de truncamento, **rode de novo com um teto maior** para cobrir todos:
  `python scripts/seed.py --termo "<TERMO>" --max-infoids <total_bruto+50>`.

## Passo 2 — Filtro semântico (subagente com o prompt inline)
O seed pode ter milhares de linhas — **não o leia você mesmo** (encheria seu contexto). Dispare um
subagente (Agent/Task tool, `subagent_type: "general-purpose"`) passando **exatamente o prompt
abaixo**, com `<TERMO>` e `<INTENÇÃO COMPLETA>` preenchidos com o que você identificou no Passo 0.
O subagente lê `dados_tmp/seed.json`, grava `dados_tmp/validado.json` e devolve só um resumo.

Prompt para o subagente (copie o bloco inteiro):

````text
Você é um analista de pesquisa de mercado. Sua tarefa é decidir, entre questões candidatas, quais
realmente permitem inferir POSSE/USO ATUAL do conceito buscado.

Termo: <TERMO>
Intenção completa: <INTENÇÃO COMPLETA>
Entrada (candidatos): dados_tmp/seed.json
Saída (validados): dados_tmp/validado.json

## Como ler a entrada
Leia dados_tmp/seed.json com a ferramenta Read passando `limit: 20000` — o arquivo costuma ter
milhares de linhas e o padrão (2000) truncaria. O topo traz `total` (= nº de candidatos): esse é o
`total_candidatos` e você PRECISA julgar TODOS. Se `len(candidatos)` for menor que `total`, releia
em páginas com `offset`/`limit` até cobrir o arquivo inteiro.

Cada candidato tem: `InfoID`, `Label`, `casou_por` (resposta/pergunta/label), `perguntas` (lista de
`{texto, codJobs}` — o texto real da pergunta e os jobs onde aparece), `respostas_match` (respostas
que casaram o termo — cada uma com `RespostaID`, `Valor`; é DESTAS que você escolhe os `respostaIds`
de posse) e, quando existe, `respostas_amostra` (algumas respostas que NÃO casaram, só pra entender
a escala e decidir `allResponses`). Textos longos vêm cortados com `…` — julgue pelo sentido. Se
aparecer `respostas_match_total` maior que a lista, havia muitas respostas casadas (geralmente
abertas/recall) e só as mais frequentes vieram — julgue PELA PERGUNTA: se for recall/propaganda,
rejeite sem se preocupar com as omitidas.

## Sinal decisivo: a PERGUNTA, não o Label
Quando `casou_por` inclui "resposta", NÃO decida pelo Label — a resposta "Netflix" pode vir de
"Quais streamings você assina?" (posse) ou de "Qual propaganda você lembra?" (recall). Use o `texto`
de cada `perguntas` para decidir: aceite o(s) `RespostaID` casado(s) somente se ao menos uma
pergunta associada realmente implicar POSSUIR/USAR o conceito. Se todas forem
recall/propaganda/imagem/atributo/cancelamento, REJEITE mesmo que a resposta seja o termo.

## Ancoragem por job (`codJobs`)
O mesmo InfoID pode estar ligado a perguntas de jobs diferentes (contaminação). Ao aceitar um
InfoID, inclua em `codJobs` a união dos `codJobs` das perguntas que você aprovou (só delas). Se
aprovar TODAS as perguntas do InfoID, pode omitir `codJobs`.

## Regras de julgamento
- ACEITAR com `respostaIds`: liste só os `RespostaID` cujas respostas indicam posse/uso (ex.: opção
  "Netflix" em "Quais streamings você assina?", ou "Sim" em "Você assina Netflix?").
- ACEITAR com `allResponses: true`: somente quando a pergunta INTEIRA é triada ao conceito (ex.:
  "Há quanto tempo você assina Netflix?"). NUNCA em múltipla escolha de marcas onde o conceito é só
  uma opção — aí use `respostaIds` com só a opção do conceito. Na dúvida, trate como multi-opção.
- REJEITAR quando responder NÃO implica posse: recall/descrição de propaganda, imagem/NPS/atributos
  de marca, cancelamento/ex-cliente, artefatos de template (`$FUNCAO_MIDIA(...)`).

Na dúvida entre aceitar e rejeitar, REJEITE (precisão > recall).

COBERTURA OBRIGATÓRIA: avalie TODOS os InfoIDs. NÃO liste os rejeitados item a item — resuma-os.

## Saída
Grave EXATAMENTE este formato em dados_tmp/validado.json com a ferramenta Write:

```json
{
  "termo": "<termo>",
  "total_candidatos": 135,
  "total_avaliados": 135,
  "validados": [
    {"InfoID": 10389, "respostaIds": [12345], "codJobs": [20874], "motivo": "opção de posse direta"},
    {"InfoID": 22222, "allResponses": true, "codJobs": [19001], "motivo": "pergunta triada"}
  ],
  "rejeitados_resumo": {"total": 130, "padroes": ["recall de propaganda", "atributos de marca", "ex-cliente"]}
}
```

`total_candidatos` = nº de candidatos na entrada; `total_avaliados` = aceitos + rejeitados — DEVEM
ser iguais. Sua mensagem final é só um resumo curto (quantos aceitos, quantos rejeitados, caminho
gravado). NÃO repita o JSON inteiro na resposta.
````

No retorno do subagente, confira que `total_avaliados == total_candidatos`; se for menor, avise que
a cobertura foi parcial antes de seguir.

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
Informe o caminho do CSV e que as colunas são `id, painelistaid, codjob, infoid` (uma linha por
respondente × tema × pesquisa; `painelistaid` fica vazio quando o respondente não é painelista
Fala.e).
