"""Configuração do Agente Painelista — lê tudo do arquivo .env."""
import os
import sys
from dotenv import load_dotenv

# Carrega variáveis do .env (mesma pasta)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Correção de OpenSSL no macOS (permite conexão TLS com SQL Server antigo).
if sys.platform == "darwin":
    _ssl_conf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_openssl.cnf")
    if os.path.exists(_ssl_conf):
        os.environ["OPENSSL_CONF"] = _ssl_conf


class DatabaseConfig:
    """Endereço e credenciais do SQL Server — TUDO vem do arquivo .env (nada fica no código)."""
    SERVER = os.getenv("DB_SERVER", "")
    PORT = os.getenv("DB_PORT", "1433")   # 1433 é a porta padrão do SQL Server (não é segredo)
    USER = os.getenv("DB_USER", "")
    PASSWORD = os.getenv("DB_PASSWORD", "")
    DATABASE = os.getenv("DB_DATABASE", "")
