# 🔎 Agente Painelista

Ferramenta para descobrir **quantas pessoas da base representam um conceito** — por exemplo
"clientes do Nubank" ou "quem assina Netflix" — e gerar uma planilha (CSV) com o resultado.

Você faz uma pergunta em português. O agente busca na base, separa **quem realmente possui/usa**
o item (e não quem só opinou ou viu propaganda) e te responde:

- **quantos painelistas** do Fala.e se encaixam;
- e um **CSV** com essas pessoas.

> 🚀 **É sua primeira vez e não é da área técnica?** Siga o **[GUIA-RÁPIDO](GUIA-RAPIDO.md)** —
> passo a passo com textos prontos para copiar e colar.

---

## ⚠️ Antes de começar (leia isto)

Esta ferramenta **roda no seu computador** (é ele que está na VPN e alcança o banco). Por isso ela
funciona pelo **Claude Code** — o app do Claude instalado no computador, que consegue executar as
buscas na sua máquina.

- ✅ **Claude Code** (app no computador): funciona.
- ❌ **Chat do Claude no navegador (claude.ai):** *não* funciona — ele roda na nuvem, não no seu
  computador, e não enxerga o banco interno da empresa.

Então: **instale o Claude Code** (uma vez) antes de seguir. O resto abaixo você pode até pedir pro
próprio Claude Code fazer, conversando.

---

## Passo a passo (faça uma vez)

### 1. Baixe o projeto
Duas formas — escolha a mais fácil pra você:
- **Pelo GitHub (mais simples):** na página do repositório, clique em **Code → Download ZIP**,
  e descompacte numa pasta.
- **Ou peça ao Claude Code:** *"clone o repositório https://github.com/HSR-Data/agente-painelista"*.

> 🧩 **Já usa o Claude Code e só quer a skill?** Tudo o que ela precisa (scripts, prompt do
> julgador, `requirements.txt`) está dentro da pasta `.claude/skills/buscar-painelistas`. Dá para
> instalar só ela, sem clonar o projeto:
>
> ```
> npx skills add HSR-Data/agente-painelista
> ```
>
> ou copie a pasta para `~/.claude/skills/buscar-painelistas`. Nesse modo, o `.env` fica na pasta
> em que você abrir o Claude Code (ou aponte a variável `PAINELISTA_ENV_FILE` para ele), e os
> arquivos de trabalho (`dados_tmp/`, CSVs) são gravados nessa mesma pasta.

### 2. Coloque o arquivo `.env` na pasta
Peça o arquivo com as credenciais para quem te indicou a ferramenta e **cole-o dentro da pasta
`agente-painelista`**. Você vai receber um arquivo chamado **`env.txt`** (ou já **`.env`**).

- **Renomeie o arquivo para `.env`** (com ponto na frente, sem o `.txt` no final).
- O nome final tem que ser exatamente **`.env`**, dentro da pasta do projeto.

> ⚠️ Sem esse arquivo a ferramenta **não funciona** — ela avisa e para. As credenciais não vêm no
> download por segurança; são enviadas separadamente.
>
> 💡 No macOS, para ver/renomear arquivos que começam com ponto, aperte `Cmd + Shift + .` no Finder.

### 3. Instale o que precisa (um instalador cuida disso)
Tem um instalador que confere tudo pra você. Escolha uma:
- **Dois cliques:** `instalar.command` (macOS) ou `instalar.bat` (Windows).
- **Ou peça ao Claude Code:** *"rode o instalar.py"*.
- **Ou no Terminal, dentro da pasta:** `python instalar.py`

Ele instala as bibliotecas, confere o **Driver ODBC** e valida o `.env`, e no final diz o que está
pronto e o que falta. Se faltar o **Driver ODBC 18 da Microsoft**, ele mostra o comando certo para o
seu sistema (é o único item que às vezes precisa ser instalado à parte, uma vez só).

---

## Como usar

1. **Conecte a VPN** da empresa (sem ela não alcança o banco).
2. Abra esta pasta no **Claude Code**.
3. Chame com o comando **`/buscar-painelistas`** seguido do que você quer buscar:

   ```
   /buscar-painelistas quem assina Netflix
   /buscar-painelistas pessoas que são clientes do Nubank
   /buscar-painelistas possuidores de seguro de vida
   /buscar-painelistas clientes do Itaú
   ```

   Também funciona pedindo em português normal (ex.: *"quantas pessoas assinam Netflix?"*) — o Claude
   ativa a skill **buscar-painelistas** sozinho. Se você não disser o que buscar, o agente pergunta.

---

## O que você recebe

A resposta traz o número de pessoas do painel:

```
Encontrei 53.278 painelistas que são clientes do Nubank.
```

E um **CSV** (`resultado_<termo>.csv`), com **uma linha por pessoa**:

| Coluna | O que é |
|---|---|
| `painelistaid` | identificador da pessoa no painel Fala.e |
| `data_resposta` | data da **resposta mais recente** dela sobre o tema |

> Se a pessoa respondeu em várias pesquisas, fica a data mais recente — é a evidência mais
> atual de que ela se encaixa no perfil. (Não é a data em que virou cliente.)

Se você também precisar saber **de qual pesquisa** veio a resposta, peça: existe uma versão
`resultado_<termo>_detalhado.csv` com as colunas `codjob` e `codquestao`, já pronta.

### Por que o número é de painelistas, e não de respondentes
Uma pessoa recebe um **código de respondente diferente a cada pesquisa** que participa. Só o
`painelistaid` (vinculado a um CPF único) identifica a pessoa. Contar códigos de respondente
inflaria o resultado várias vezes — por isso o número reportado é sempre o de painelistas.

## Se algo der errado

| O que aparece | O que fazer |
|---|---|
| Aviso pedindo o arquivo `.env` | Coloque o `.env` na pasta (passo 2) |
| `Login timeout expired` | Conecte/reconecte a VPN e tente de novo |
| `Nenhum ODBC Driver ... encontrado` | Instale o Driver ODBC 18 (passo 3) |
| "Nenhum resultado encontrado" | Tente outra palavra (ex.: o nome da marca) |
