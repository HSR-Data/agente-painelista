# 🔎 Agente Painelista

Ferramenta para descobrir **quantas pessoas da base representam um conceito** — por exemplo
"clientes do Nubank" ou "quem assina Netflix" — e gerar uma planilha (CSV) com o resultado.

Você faz uma pergunta em português. O agente busca na base, separa **quem realmente possui/usa**
o item (e não quem só opinou ou viu propaganda) e te responde:

- **Respondentes totais** que se encaixam;
- Quantos são **painelistas Fala.e** (têm PainelistaID);
- E, se você quiser, um **CSV** com o resultado.

---

## Passo a passo (faça uma vez)

### 1. Baixe o projeto
```bash
git clone https://github.com/HSR-Data/agente-painelista.git
cd agente-painelista
```

### 2. Coloque o arquivo `.env` na pasta
Peça o arquivo com as credenciais para quem te indicou a ferramenta e **cole-o dentro da pasta
`agente-painelista`**. Você vai receber um arquivo chamado **`env.txt`** (ou já **`.env`**).

- **Renomeie o arquivo para `.env`** (com ponto na frente, sem o `.txt` no final).
- O nome final tem que ser exatamente **`.env`**, dentro da pasta do projeto.

> ⚠️ Sem esse arquivo a ferramenta **não funciona** — ela avisa e para. As credenciais não vêm no
> download por segurança; são enviadas separadamente.
>
> 💡 No macOS, para ver/renomear arquivos que começam com ponto, aperte `Cmd + Shift + .` no Finder.

### 3. Instale o que precisa
Abra o Terminal **dentro da pasta** e rode:
```bash
python3 -m venv .venv
source .venv/bin/activate          # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Você também precisa, **uma vez só**, do **Driver ODBC 18 da Microsoft**:
- **macOS:** `brew install msodbcsql18` (após `brew tap microsoft/mssql-release https://github.com/microsoft/homebrew-mssql-release`)
- **Windows:** baixe *"ODBC Driver 18 for SQL Server"* no site da Microsoft.

---

## Como usar

1. **Conecte a VPN** da empresa (sem ela não alcança o banco).
2. No Terminal, ative o ambiente: `source .venv/bin/activate`.
3. Abra esta pasta no **Claude Code**.
4. **Peça em português** o que você quer buscar — o Claude ativa sozinho a skill
   **buscar-painelistas**. Exemplos:

   ```
   quantas pessoas são clientes do Nubank?
   quem assina Netflix
   quero os possuidores de seguro de vida
   clientes do Itaú
   ```

   Se preferir, pode chamar a skill pelo nome: **"use a skill buscar-painelistas"**.
   Se você não disser o que buscar, o agente pergunta.

---

## O que você recebe

O agente responde com o número de pessoas:

```
Respondentes totais:        7.145
Com PainelistaID (Fala.e):  2.911
```

Depois ele pergunta se você quer o **CSV**. Se disser **sim**, ele salva um arquivo
`resultado_<termo>.csv` na pasta, com uma linha por pessoa e estas colunas:

| Coluna | O que é |
|---|---|
| `id` | código do respondente |
| `painelistaid` | código do painelista Fala.e (fica **vazio** se a pessoa não for painelista) |
| `codjob` | a pesquisa de onde veio |
| `infoid` | o tema da pergunta |

---

## Se algo der errado

| O que aparece | O que fazer |
|---|---|
| Aviso pedindo o arquivo `.env` | Coloque o `.env` na pasta (passo 2) |
| `Login timeout expired` | Conecte/reconecte a VPN e tente de novo |
| `Nenhum ODBC Driver ... encontrado` | Instale o Driver ODBC 18 (passo 3) |
| "Nenhum resultado encontrado" | Tente outra palavra (ex.: o nome da marca) |
