---
name: buscar-painelistas
description: Descobre quantos painelistas do Fala.e possuem/usam algo (ex.: clientes do Nubank, quem assina Netflix, possuidores de seguro) e gera um CSV com os PainelistaIDs. Use quando o usuário quiser o tamanho de um público na base ou exportar essas pessoas.
---

# Buscar Painelistas

Descobre **quantas pessoas do painel** representam o conceito pedido e gera um **CSV** com elas.

**Requisitos:** rodar da raiz do projeto, ambiente Python ativado, dependências instaladas, `.env`
na pasta e acesso ao SQL Server (VPN). Se algo falhar, veja o `README.md`.

O foco é sempre **posse/uso real** — nunca opinião, lembrança de propaganda ou conhecimento de marca.

---

## Passo 0 — Entender o pedido
Pegue o conceito da mensagem do usuário. Se não veio nenhum, pergunte *"O que você quer buscar?"*
e aguarde. Depois identifique:
- o **termo lexical** para a busca (ex.: "clientes do Nubank" → `Nubank`);
- a **intenção completa** (possui/usa hoje? não é ex-cliente? não é só avaliação?).

## Passo 1 — Seed
```
python scripts/seed.py --termo "<TERMO>"
```
Busca o termo nas **respostas**, nas **perguntas** e no enunciado da **mãe** dos grids — os três são
necessários: "Você é usuário Netflix?" com respostas "Sim/Não" só aparece pela pergunta.

Agrupa perguntas idênticas em **padrões** (o mesmo enunciado se repete em centenas de pesquisas),
então o julgamento vale para todas de uma vez.

- `[VAZIO]` → avise que nada casou, sugira outro termo e **pare**.
- **Não leia** `dados_tmp/seed.json` — é grande e encheria seu contexto.

## Passo 2 — Dividir em lotes
```
python scripts/dividir_seed.py --lotes <N>
```
Use **N ≈ total de padrões ÷ 250**, no mínimo 1 e no máximo 8.

> Por que dividir: um único subagente julgando mais de ~300 padrões atravessa o limite de contexto
> e passa a errar. Isso já aconteceu — 1.545 padrões numa tarefa só produziram 39 aceites, contra
> **273** quando divididos em 6 lotes, com perguntas óbvias de posse sendo rejeitadas por engano.

## Passo 3 — Julgar os lotes EM PARALELO
Dispare **um subagente `painelista-filter` por lote**, todos **na mesma mensagem** (para rodarem em
paralelo). Em cada prompt informe: o termo, a intenção completa, o arquivo de entrada
(`dados_tmp/lote_<i>.json`) e o de saída (`dados_tmp/validado_<i>.json`), e mande avaliar **todos**
os padrões do lote.

Inclua sempre este alerta, que corrige o erro mais comum:
> Leia `mae` + `pergunta` + resposta como **uma frase única**. Em grid, a mãe traz o verbo
> ("possui", "qual a principal") e a filha traz o produto — só a leitura conjunta permite decidir.

## Passo 4 — Juntar
```
python scripts/juntar_validados.py
```
Se aparecer `[AVISO] cobertura parcial`, algum lote não avaliou tudo — **avise o usuário** antes de
seguir, porque o número sairá subestimado.

## Passo 5 — Contar e exportar
```
python scripts/resolve.py --validated dados_tmp/validado.json --out resultado_<termo>.csv
```

## Passo 6 — Reportar (mantenha CURTO)

Diga **quantos painelistas** foram identificados e ofereça o CSV. Sem tabelas, sem detalhamento de
respondentes/massa, sem lista de perguntas aceitas — a menos que o usuário peça.

Formato:

> Encontrei **53.278 painelistas** que são clientes do Nubank.
>
> CSV: `resultado_nubank.csv` — uma linha por painelista, com `painelistaid` e `data_resposta`
> (a data da resposta mais recente de cada pessoa).

**Só mencione o CSV detalhado se o usuário pedir** `codjob`/`codquestao` ou "de qual pesquisa veio".
Ele já foi gerado (`resultado_<termo>_detalhado.csv`, com `+codjob,codquestao`), então é entrega
imediata — mas a maioria só precisa do id e da data, e citá-lo à toa só polui a resposta.

Se perguntarem sobre a massa total, aí sim explique: `respondentes` inclui não-painelistas, que
**não são pessoas contáveis** (sem PainelistaID não há como saber quantos indivíduos distintos são,
porque a mesma pessoa recebe um código novo a cada pesquisa).
