#!/usr/bin/env python3
"""Instalador do Agente Painelista — funciona em macOS, Windows e Linux.

Uso:
    python instalar.py
    (ou dois cliques em  instalar.command  no Mac  /  instalar.bat  no Windows)

Ele instala as bibliotecas Python, confere o Driver ODBC e valida o .env,
e no final mostra o que está pronto e o que ainda falta.
"""
import os
import sys
import subprocess

AQUI = os.path.dirname(os.path.abspath(__file__))
OK, X, AV = "[OK]", "[FALTA]", "[!]"


def titulo(t):
    print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)


def instala_dependencias():
    titulo("1/3  Instalando bibliotecas Python (pyodbc, python-dotenv)")
    req = os.path.join(AQUI, "requirements.txt")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", req], check=False)
    except Exception as e:
        print(AV, "pip retornou um aviso (vou checar se instalou mesmo assim):", e)
    faltou = []
    for mod in ("pyodbc", "dotenv"):
        try:
            __import__(mod)
        except ImportError:
            faltou.append(mod)
    if faltou:
        print(X, "Não consegui instalar:", ", ".join(faltou))
        return False
    print(OK, "Bibliotecas Python instaladas.")
    return True


def confere_driver():
    titulo("2/3  Conferindo o Driver ODBC do SQL Server")
    try:
        import pyodbc
    except ImportError:
        print(X, "pyodbc não instalou — resolva o passo 1 primeiro.")
        return False
    achou = [d for d in pyodbc.drivers() if "ODBC Driver 1" in d and "SQL Server" in d]
    if achou:
        print(OK, "Driver encontrado:", ", ".join(achou))
        return True
    print(X, "Nenhum 'ODBC Driver 18/17 for SQL Server' encontrado. Instale conforme seu sistema:")
    if sys.platform == "darwin":
        print("   macOS (com Homebrew):")
        print("     brew tap microsoft/mssql-release https://github.com/microsoft/homebrew-mssql-release")
        print("     HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18")
    elif sys.platform.startswith("win"):
        print("   Windows: baixe 'ODBC Driver 18 for SQL Server' no site da Microsoft e instale.")
    else:
        print("   Linux: siga o guia oficial 'msodbcsql18' da Microsoft para a sua distribuição.")
    return False


def confere_env():
    titulo("3/3  Conferindo o arquivo .env")
    env = os.path.join(AQUI, ".env")
    if not os.path.exists(env):
        print(X, "Arquivo .env não encontrado nesta pasta.")
        print("   Peça o arquivo de credenciais para quem te passou a ferramenta,")
        print("   cole-o nesta pasta e renomeie para exatamente  .env  (com ponto na frente).")
        return False
    chaves = {}
    with open(env, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            chaves[k.strip()] = v.split("#")[0].strip()
    faltou = [k for k in ("DB_SERVER", "DB_USER", "DB_PASSWORD", "DB_DATABASE") if not chaves.get(k)]
    if faltou:
        print(X, "O .env existe mas faltam valores:", ", ".join(faltou))
        return False
    print(OK, ".env encontrado e preenchido.")
    return True


def main():
    print("Instalador do Agente Painelista")
    print("Python:", sys.version.split()[0], "|", sys.executable)
    r1 = instala_dependencias()
    r2 = confere_driver()
    r3 = confere_env()
    titulo("Resumo")
    print(f"{OK if r1 else X} Bibliotecas Python")
    print(f"{OK if r2 else X} Driver ODBC")
    print(f"{OK if r3 else X} Arquivo .env")
    if r1 and r2 and r3:
        print("\nTudo pronto! Ligue a VPN, abra esta pasta no Claude Code e peça em português,")
        print("por exemplo: 'quantas pessoas assinam Netflix?'")
    else:
        print("\nResolva os itens marcados com [FALTA] acima e rode de novo:  python instalar.py")


if __name__ == "__main__":
    main()
