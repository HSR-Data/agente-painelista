# ⚡ Guia Rápido — Agente Painelista

Para usar **sem complicação**. É só seguir os passos e **colar os textos em azul** no Claude Code.
Você faz a instalação **uma vez**; depois é só usar.

---

## 0. Instale o Claude Code (uma vez só)

O Claude Code é o app do Claude que roda no seu computador (é ele que consegue fazer a busca).
Baixe em: **https://claude.com/claude-code** e instale como qualquer programa.

> ❗ Não dá para usar pelo chat do Claude no navegador — a busca precisa rodar **no seu computador**,
> que é o que está na VPN da empresa.

---

## 1. Baixe o projeto

Na página do repositório **https://github.com/HSR-Data/agente-painelista**, clique no botão verde
**`Code`** → **`Download ZIP`**. Descompacte numa pasta fácil de achar (ex.: a Área de Trabalho).

---

## 2. Coloque o arquivo de credenciais

Você vai receber um arquivo chamado **`env.txt`** (por mensagem/cofre de senhas).

1. Cole o `env.txt` **dentro da pasta** `agente-painelista`.
2. **Renomeie** para **`.env`** (com ponto na frente, sem o `.txt` no final).

> 💡 No Mac, para ver arquivos que começam com ponto, aperte `Cmd + Shift + .` no Finder.

---

## 3. Instale o que falta (uma vez)

Abra a pasta no Claude Code e **cole este prompt**:

> Entre nesta pasta e rode `python instalar.py`. Depois me diga, em português, o que ficou pronto e
> o que ainda falta instalar.

O instalador confere tudo sozinho. Se ele disser que falta o **Driver ODBC**, cole:

> Falta o Driver ODBC. Me mostre o passo a passo para instalar no meu sistema e, se possível, faça
> para mim.

*(Alternativa sem prompt: dê dois cliques em `instalar.command` no Mac ou `instalar.bat` no Windows.)*

---

## 4. Usar (sempre que precisar)

1. **Ligue a VPN** da empresa.
2. Abra a pasta no Claude Code.
3. Digite o comando com o que você quer buscar:

```
/buscar-painelistas quem assina Netflix
```

Outros exemplos:
```
/buscar-painelistas pessoas que são clientes do Nubank
/buscar-painelistas possuidores de seguro de vida
/buscar-painelistas clientes do Itaú
```

> Também funciona pedindo em português normal, ex.: *"quantas pessoas assinam Netflix?"*

O agente responde com os números e pergunta se você quer o **CSV** (uma planilha com o resultado).

---

## Deu algum erro?

| O que aparece | O que fazer |
|---|---|
| Pediu o arquivo `.env` | Confira que o arquivo na pasta se chama exatamente `.env` (passo 2) |
| `Login timeout` | Ligue/religue a **VPN** e tente de novo |
| Falou de **Driver ODBC** | Volte ao passo 3 e instale o driver |
| Não achou nada | Tente outra palavra (ex.: o nome da marca) |

Precisa de mais detalhes? Veja o **[README.md](README.md)**.
