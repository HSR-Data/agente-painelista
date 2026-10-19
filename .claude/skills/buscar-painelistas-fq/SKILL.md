---
name: buscar-painelistas-fq
description: Descobre quantos painelistas da Falai possuem/usam algo (ex.: clientes de banda larga da Vivo, quem assina Netflix, clientes do Nubank) e gera um CSV com eles. Busca primeiro nas tabelas fq_ (cópia fiel e atual do FastQuest) e depois no arquivo antigo (perguntas/respostas/respondentes), que guarda as ondas que o FastQuest já apagou. Também faz cortes e combinações entre produtos (só banda larga, banda larga + TV + pós). Use quando o usuário quiser o tamanho de um público na base, segmentar clientes por produto ou exportar esses painelistas.
---

# Buscar Painelistas (fq_ + arquivo antigo)

Descobre **quantas pessoas do painel** representam o conceito pedido e gera um **CSV** com elas.
O foco é **posse/uso real** — nunca opinião, lembrança de propaganda ou conhecimento de marca.

Mesmo fluxo da skill `buscar-painelistas` (seed → lotes → julgamento em paralelo → junção →
resolve), com duas fontes no banco `Falai_Painelista_Data`:

| Fonte | Tabelas | O que tem |
|---|---|---|
| **fq_** (principal) | `fq_questao`, `fq_questao_opcao`, `fq_resposta`, `fq_cliente` | Cópia fiel do FastQuest hoje. Só painelistas (`CodClienteCAWI` = `PainelistaID`). Texto preservado, inclusive `$FUNCAO_MIDIA(VIVO)` |
| **antigo** (arquivo) | `perguntas`, `respostas`, `respondentes` | Ondas que o FastQuest **já apagou** (ele apaga clientes e respostas de ondas antigas). O limpador antigo apagou os `$FUNCAO_MIDIA(...)` — muitas opções de marca ficaram com texto vazio |

As duas fontes viram **um** conjunto de padrões (mesmo enunciado normalizado = mesmo padrão), e a
contagem final é de `PainelistaID` distintos na **união**. Medido para "banda larga da Vivo":
5.677 no fq_, 6.859 no antigo, 3.350 nas duas → **9.186**.

**Padrões condicionais.** Muitas perguntas não citam a marca: citam a resposta de outra
(`{RU("P8").Selecionada().Descricao()}` — "Nesta sua linha da ___, qual o tipo de plano?"). O seed
acha a pergunta referida no mesmo questionário; se ela tem opção que casa o termo, cria um padrão
com o placeholder trocado ("Nesta sua linha da VIVO…") e o resolve só conta quem marcou "VIVO" na
referida. Foi o que trouxe o plano (pré/pós/controle) de 107 mil linhas Vivo e a banda larga de
quem avaliou a Vivo — antes, só cruzando à mão.

Medido em 19/10/2026 (termo "Vivo", 6 conceitos num julgamento só, 6 lotes): banda larga 9.879,
TV 27.658, móvel 127.088 — pré 53.438, pós 37.735, controle 29.375 (iguais ao cruzamento manual);
15.294 com os três produtos conhecidos para as combinações.

## Ambiente

`SKILL` = o *base directory* informado quando esta skill foi carregada. Os comandos rodam **no
diretório de trabalho do usuário** (lá ficam `dados_tmp/` e o CSV final).

Antes do primeiro uso, confira (uma vez):
- `python -c "import pyodbc, dotenv"` — se falhar: `pip install -r "$SKILL/requirements.txt"`.
- **Driver ODBC 17/18 for SQL Server** instalado.
- **`.env`** com `DB_SERVER`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` e **`DB_DATABASE=Falai_Painelista_Data`**
  (lido do diretório atual ou de `PAINELISTA_ENV_FILE`; modelo em `$SKILL/.env.example`). Não invente valores.
- **VPN ligada.** `Login timeout expired` = VPN. `08001 / 10054` logo ao conectar = TLS: o
  `config.py` aplica `custom_openssl.cnf` no import; não importe `hashlib`/`ssl` antes dele.

---

## Passo 0 — Entender o pedido
Pegue o conceito. Se não veio, pergunte *"O que você quer buscar?"* e aguarde. Identifique:
- o **termo lexical** (ex.: "clientes de banda larga da Vivo" → `Vivo`);
- a **intenção completa** (possui hoje? de quê exatamente? pessoa física, não a empresa?).

Use o termo da **marca/produto**, não do serviço: "banda larga" sozinho traz centenas de padrões
de avaliação; o serviço é decidido no julgamento lendo o enunciado.

## Passo 1 — Seed
```
python "$SKILL/scripts/seed.py" --termo "<TERMO>"
```
Busca o termo nas opções, nas perguntas e na mãe dos grids, nas **duas fontes**, agrupa em padrões
e acrescenta os **condicionais** (perguntas que citam `RU("X")` de uma pergunta X cuja opção casou o termo).
Faz também a **transferência por código**: perguntas antigas com opção de texto vazio (mídia apagada)
que têm o mesmo enunciado de um padrão fq_ entram nele, ligadas pelo código da opção
(`respostas.CodResposta` = `fq_questao_opcao.Opcao`). Sem isso, o P10C "VIVO" (código 4012) das
ondas apagadas nunca aparece. Demora alguns minutos para termos frequentes.

- `[VAZIO]` → avise que nada casou, sugira outro termo e **pare**.
- **Não leia** `dados_tmp/seed.json` nem `grupos.json` — são grandes.

## Passo 2 — Filtrar e dividir
```
python "$SKILL/scripts/dividir_seed.py" --lotes 4
```
4 lotes até ~1.200 padrões após o filtro; +1 a cada 250 extras, máximo 6. Mais lotes **encarece**
(custo fixo ~50k por subagente) e deixa o julgamento mais agressivo.

## Passo 3 — Julgar os lotes EM PARALELO
Um subagente por lote, **todos na mesma mensagem**: `painelista-filter` se existir no projeto;
senão `general-purpose` com `model: opus`, colando `$SKILL/references/painelista-filter.md`
como instruções (só `Read` e `Write`). Em cada prompt: termo, intenção completa, entrada
`dados_tmp/lote_<i>.json`, saída `dados_tmp/validado_<i>.json`, avaliar **todos** os padrões, e:

> Leia `contexto` + `mae` + `pergunta` + resposta como **uma frase única**. Em grid, a mãe (ou,
> quando a mãe é vazia, o `contexto` — a pergunta anterior do questionário) traz o verbo
> ("possui", "qual a principal") e a filha traz o produto. `$FUNCAO_MIDIA(VIVO)` é o logo da marca:
> a opção **é** "Vivo". Os `RespostaID` são ids locais do padrão — devolva-os como vieram.
> Padrão com `condicao`: só conta quem deu aquela resposta na pergunta referida (o placeholder já
> foi trocado por ela).

**Vários produtos de uma vez (segmentação).** Para cortes como "só banda larga" ou "banda larga +
TV + pós", rode o seed **uma vez** com o termo da marca e julgue **uma vez** com a lista de
conceitos rotulados no prompt (ex.: `BL` banda larga fixa da Vivo; `TV` TV por assinatura da
Vivo; `MOV` linha de celular Vivo, qualquer plano; `PRE`/`POS`/`CTRL` plano da linha Vivo). Cada
aceite volta com `"conceito"`; o mesmo padrão pode servir a vários. É bem mais barato que um
julgamento por conceito.

## Passo 4 — Juntar
```
python "$SKILL/scripts/check_coverage.py" && python "$SKILL/scripts/juntar_validados.py"
```
`Coverage blocked: ...` → rode de novo **só o lote faltante**. `[AVISO] cobertura parcial` → avise
o usuário (número subestimado).

## Passo 5 — Contar e exportar
```
python "$SKILL/scripts/resolve.py" --validated dados_tmp/validado.json --out resultado_<termo>.csv
```
Imprime o total e a divisão fq_ / antigo / nas duas. Grava também `resultado_<termo>_padroes.csv`:
um padrão aceito por linha, com quantos painelistas ele traz. **Confira-o** antes de reportar
um número grande ou inesperado (ex.: 111 mil de móvel vinham de uma pergunta só, "De quais
operadoras de celular você é cliente atualmente?" — real, mas tem que ser visto).

Multi-conceito: uma chamada por rótulo, com `--conceito <ROTULO>`. Para cortes e combinações
acrescente `--com-base`: grava `_base.csv` com **toda** resposta aos padrões aceitos, `sim=1`
(afirma) ou `sim=0` (respondeu e marcou outra coisa) — é o "não" que um "só X" exige.

## Passo 5b — Cortes e combinações (só se pedirem segmentação)
```
python "$SKILL/scripts/combinar.py" \
    --conceito BL="Banda Larga"=resultado_vivo_bl_base.csv --conceito TV=TV=resultado_vivo_tv_base.csv \
    --conceito MOV="Móvel"=resultado_vivo_mov_base.csv --conceito PRE="Pré"=resultado_vivo_pre_base.csv \
    --conceito POS="Pós"=resultado_vivo_pos_base.csv --conceito CTRL=Controle=resultado_vivo_ctrl_base.csv \
    --detalhe MOV=PRE,POS,CTRL --out combinacoes_vivo.csv
```
Imprime 4 camadas: (1) alguma vez por produto; (2) detalhe (plano); (3) combinações de produtos;
(4) combinações com detalhe. Nas camadas 3–4 vale a **última** onda em que a pessoa respondeu
cada produto, e só entra quem tem **todos** os produtos conhecidos — quem nunca foi perguntado
sobre banda larga não pode ser "só móvel". Reporte também quantos ficaram fora por produto
desconhecido (costuma ser a maioria).

## Passo 6 — Reportar (CURTO)

> Encontrei **9.186 painelistas** com banda larga da Vivo (5.677 nas tabelas fq_; 3.509 só no
> arquivo antigo, de ondas que o FastQuest já apagou).
>
> CSV: `resultado_vivo.csv` — `painelistaid`, `data_resposta` (mais recente) e `fonte` (fq_/antigo/ambos).

Mencione `resultado_<termo>_detalhado.csv` (origem: repositório/job/questão) só se pedirem.

## Limites conhecidos — diga se forem relevantes
- **Painéis externos não contam.** Pesquisas como o BC Claro têm milhares de respondentes de
  Offerwise, SSI/Dynata, Toluna, Opinaia, TAP: o `CodClienteCAWI` deles é id do painel externo
  (hash, token, `PRODW…`, ou um GUID que não está em `Painelista`). Não são painelistas da Falai.
  Um SAV com "milhares de clientes Vivo" tem só uma fração do painel Falaí.
- **Ondas apagadas antes do pipeline antigo existir** (ex.: BC Claro 2024) não estão em lugar
  nenhum do banco. Só o SAV as tem.
- **`PainelistaID` do arquivo antigo** veio do lookup `Painelista_Resultado` do pipeline antigo
  (não do `CodClienteCAWI`). O resolve só aceita os que existem em `falai.dbo.Painelista`.
- **Referências dinâmicas fora de `RU("X")`**: `{DM.OpAtual...}`, `{VL("X").Resposta()}` e
  expressões com `var`/`if` sobre várias perguntas não viram condicional — continuam rejeitadas.
  No arquivo antigo, a pergunta referida só vale se a opção do termo ainda tem texto (o limpador
  apagou os `$FUNCAO_MIDIA`; aí a condição não é achada).
- **Plano só da linha principal**: as perguntas de plano (PF5/PF7) perguntam pela operadora
  principal/avaliada. Quem tem Vivo como segunda linha fica com plano desconhecido.
- **Texto livre do fq_ não é buscado** (varrer `fq_resposta.Parte` é caro); o antigo busca
  verbatins só com `--incluir-abertas`.
- **Posse da empresa** ("Qual banda larga a sua empresa possui?") não é posse da pessoa: o
  pré-filtro já descarta enunciados com "sua/da empresa", "seu negócio", "CNPJ" (por frase — "Qual
  a empresa da sua internet" é da pessoa e passa). Reportar à parte se pedirem.
- **Domicílio**: "na sua residência, você ou alguém…" vale para banda larga/TV, não para celular
  ou banco.
