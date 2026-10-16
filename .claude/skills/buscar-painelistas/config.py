"""Configuração do banco — nada é lido no import; só quando a conexão é pedida.

Ordem de precedência das credenciais (DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, DB_DATABASE):
  1. variáveis de ambiente já definidas;
  2. o arquivo apontado por PAINELISTA_ENV_FILE;
  3. um arquivo .env no diretório de trabalho atual (a pasta do projeto do usuário).

A skill pode ser instalada em ~/.claude/skills e atualizada por cima — por isso o .env
nunca fica dentro dela.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))


class DatabaseConfig:
    """Endereço e credenciais do SQL Server — tudo vem do ambiente/.env (nada fica no código)."""
    SERVER = ""
    PORT = "1433"   # 1433 é a porta padrão do SQL Server (não é segredo)
    USER = ""
    PASSWORD = ""
    DATABASE = ""


def env_file_path():
    """Qual .env será usado (ou None). Só para mensagens de erro e diagnóstico."""
    path = os.environ.get("PAINELISTA_ENV_FILE")
    if path:
        return path
    local = os.path.join(os.getcwd(), ".env")
    return local if os.path.exists(local) else None


def load_database_config():
    path = env_file_path()
    if path:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)   # ambiente já definido tem prioridade

    # Correção de OpenSSL no macOS (permite TLS com SQL Server antigo). Precisa estar
    # definido ANTES do primeiro `import pyodbc`, que é feito em make_connection().
    if sys.platform == "darwin":
        _ssl_conf = os.path.join(_AQUI, "custom_openssl.cnf")
        if os.path.exists(_ssl_conf):
            os.environ.setdefault("OPENSSL_CONF", _ssl_conf)

    for attr, variable, default in (
        ("SERVER", "DB_SERVER", ""), ("PORT", "DB_PORT", "1433"),
        ("USER", "DB_USER", ""), ("PASSWORD", "DB_PASSWORD", ""),
        ("DATABASE", "DB_DATABASE", ""),
    ):
        setattr(DatabaseConfig, attr, os.getenv(variable, default))
    return DatabaseConfig
