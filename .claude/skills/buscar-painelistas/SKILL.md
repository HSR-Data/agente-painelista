---
name: buscar-painelistas
description: Descobre quantos painelistas do Fala.e possuem/usam algo (ex.: clientes do Nubank, quem assina Netflix, possuidores de seguro) e gera um CSV com essas pessoas. Use quando o usuário quiser o tamanho de um público na base ou exportar esses painelistas.
---

# Buscar Painelistas

Descobre **quantas pessoas do painel** representam o conceito pedido e gera um **CSV** com elas.

O foco é **posse/uso real** — nunca opinião, lembrança de propaganda ou conhecimento de marca.

## Ambiente

Todos os comandos rodam a partir do projeto:

```
PROJ="${PROJ:-$HOME/Developer/agente-painelista}"   # a pasta onde este repositório foi clonado
cd "$PROJ" && source .venv/bin/activate             # sem venv: python3 -m venv .venv && pip install -r requirements.txt
```

Se a pasta não existir, pergunte ao usuário onde ele clonou o repositório — não tente adivinhar.

Requer **VPN ligada** (o banco é interno) e o arquivo `.env` na raiz do projeto.
Se der `Login timeout expired`, é VPN — peça para o usuário reconectar e tente de novo.

---

## Passo 0 — Entender o pedido
Pegue o conceito da mensagem. Se não veio nenhum, pergunte *"O que você quer buscar?"* e aguarde.
Depois identifique:
- o **termo lexical** para a busca (ex.: "clientes do Nubank" → `Nubank`);
- a **intenção completa** (possui/usa hoje? não é ex-cliente? não é só avaliação?).

## Passo 1 — Seed
```
python scripts/seed.py --termo "<TERMO>"
```
Busca o termo nas **respostas**, nas **perguntas** e no enunciado da **mãe** dos grids — os três são
necessários: "Você é usuário Netflix?" com respostas "Sim/Não" só aparece pela pergunta.
Agrupa perguntas idênticas em **padrões**, então uma decisão vale para todas as pesquisas que a repetem.

- `[VAZIO]` → avise que nada casou, sugira outro termo e **pare**.
- **Não leia** `dados_tmp/seed.json` — é grande e encheria seu contexto.

## Passo 2 — Filtrar e dividir
```
python scripts/dividir_seed.py --lotes 4
```
**Use 4 lotes** para qualquer volume até ~1.200 padrões após o filtro. Acima disso, some 1 lote a
cada 250 padrões extras, até o máximo de 6.

O script já vem com payload enxuto e pré-filtro determinístico ligados; ele imprime quantos
padrões descartou por regra. Se aparecer um descarte grande e inesperado, confira antes de seguir.

> **Não aumente o número de lotes achando que barateia — encarece.** Medido: os mesmos 992
> padrões custaram 451k tokens em 4 lotes e 567k em 8, porque cada subagente tem ~50k de custo
> fixo. E lotes pequenos deixam o julgamento mais agressivo: a rodada de 8 rejeitou 39 padrões
> legítimos de posse e perdeu 1.291 painelistas.

> O que **não** fazer: gravar o lote indentado. O arquivo passa de 20.000 linhas, o subagente
> lê em 20 pedaços, o custo cresce ao quadrado e ele pula padrões no meio. Esse defeito sozinho
> respondia por 4x o custo da busca.

## Passo 3 — Julgar os lotes EM PARALELO
Dispare **um subagente `painelista-filter` por lote**, todos **na mesma mensagem**. Em cada prompt
passe: termo, intenção completa, entrada (`dados_tmp/lote_<i>.json`) e saída
(`dados_tmp/validado_<i>.json`), mandando avaliar **todos** os padrões do lote.

Inclua sempre este alerta, que corrige o erro mais comum:
> Leia `mae` + `pergunta` + resposta como **uma frase única**. Em grid, a mãe traz o verbo
> ("possui", "qual a principal") e a filha traz o produto — só a leitura conjunta permite decidir.

## Passo 4 — Juntar
```
python scripts/juntar_validados.py
```
Se aparecer `[AVISO] cobertura parcial`, **avise o usuário**: o número sairá subestimado.

## Passo 5 — Contar e exportar
```
python scripts/resolve.py --validated dados_tmp/validado.json --out resultado_<termo>.csv
```

## Passo 6 — Reportar (CURTO)

Diga **quantos painelistas** e ofereça o CSV. Sem tabelas, sem detalhar massa/respondentes, sem
listar perguntas aceitas — a não ser que peçam.

> Encontrei **53.278 painelistas** que são clientes do Nubank.
>
> CSV: `resultado_nubank.csv` — uma linha por painelista, com `painelistaid` e `data_resposta`
> (data da resposta mais recente de cada pessoa).

**Só mencione o CSV detalhado se pedirem** `codjob`/`codquestao` ou "de qual pesquisa veio": já
existe `resultado_<termo>_detalhado.csv`, entrega imediata. A maioria só precisa do id e da data.

Se perguntarem da massa total, explique: `respondentes` inclui não-painelistas, que **não são
pessoas contáveis** — sem PainelistaID não há como saber quantos indivíduos distintos são, porque
a mesma pessoa recebe um código novo a cada pesquisa.
