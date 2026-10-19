"""Lógica + conexão da busca de painelistas (modelo relacional V2).

Chave do modelo: (codJob, CodQuestao) identifica a pergunta; RespostaID identifica
o valor exato respondido. Não existe mais InfoID (agrupamento semântico por LLM):
a interpretação é feita pelo agente, na hora da busca, lendo o texto real.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import load_database_config

# Collation case- e accent-insensitive: 'netflix' casa 'NETFLIX', 'Nubank' casa 'nubank'.
COLLATE = "Latin1_General_CI_AI"


def escape_like(term: str) -> str:
    """Escapa curingas para casar o termo literalmente. Usar com ESCAPE '\\'."""
    return (term.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                .replace("[", "\\["))


def like_pattern(term: str) -> str:
    return "%" + escape_like(term.strip()) + "%"


def pick_driver(available) -> str:
    for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if d in available:
            return d
    raise RuntimeError(
        "Nenhum ODBC Driver 17/18 para SQL Server encontrado. "
        "Instale o msodbcsql18 (veja o README). Drivers disponiveis: " + str(available))


def make_connection():
    DatabaseConfig = load_database_config()
    faltando = [nome for nome, val in (
        ("DB_SERVER", DatabaseConfig.SERVER), ("DB_USER", DatabaseConfig.USER),
        ("DB_PASSWORD", DatabaseConfig.PASSWORD), ("DB_DATABASE", DatabaseConfig.DATABASE),
    ) if not val]
    if faltando:
        raise RuntimeError(
            "Configuração do banco incompleta (faltando: " + ", ".join(faltando) + "). "
            "Coloque o .env na pasta onde você está rodando, ou aponte PAINELISTA_ENV_FILE "
            "para ele (ou exporte as variáveis DB_*).")
    import pyodbc
    driver = pick_driver(pyodbc.drivers())
    cs = (
        f"DRIVER={{{driver}}};SERVER={DatabaseConfig.SERVER},{DatabaseConfig.PORT};"
        f"DATABASE={DatabaseConfig.DATABASE};UID={DatabaseConfig.USER};PWD={DatabaseConfig.PASSWORD};"
        f"TrustServerCertificate=yes;Encrypt=no;Connection Timeout=30;"
    )
    return pyodbc.connect(cs)


def _clip(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def build_seed_bundle(term, candidatos, max_candidatos=2000, max_text=400):
    """Monta o pacote que o subagente vai julgar.

    Cada candidato é uma PERGUNTA — (codJob, CodQuestao) — com o contexto necessário
    para decidir posse:
      • `pergunta`  texto real (sinal decisivo)
      • `mae`       enunciado da pergunta-mãe, quando é grid (a filha isolada, tipo
                    "NETFLIX", não diz nada sozinha)
      • `tipo`      CodTipoQuestao (única/múltipla/aberta/grid)
      • `casou_por` onde o termo apareceu: resposta e/ou pergunta
      • `respostas_match`   respostas que contêm o termo (candidatas a posse)
      • `respostas_amostra` demais opções, com freq e flag de exclusividade — permite
                    ver se a pergunta é triada (aí vale allResponses) ou multi-marca,
                    e identificar o "Não possuo" que EXCLUI posse
    """
    ordenados = sorted(candidatos,
                       key=lambda c: c.get("respondentes", 0), reverse=True)
    dropados = max(0, len(ordenados) - max_candidatos)
    mantidos = ordenados[:max_candidatos]

    out = []
    for c in mantidos:
        item = {
            "codJob": c["codJob"],
            "CodQuestao": c["CodQuestao"],
            "casou_por": c["casou_por"],
            "tipo": c.get("tipo"),
            "pergunta": _clip(c.get("pergunta"), max_text),
            "respondentes": c.get("respondentes", 0),
        }
        if c.get("mae"):
            item["mae"] = _clip(c["mae"], max_text)
        if c.get("respostas_match"):
            item["respostas_match"] = c["respostas_match"]
        if c.get("respostas_amostra"):
            item["respostas_amostra"] = c["respostas_amostra"]
        out.append(item)

    return {"termo": term, "total": len(out),
            "truncado": {"candidatos_dropados": dropados},
            "candidatos": out}


def parse_validated(data):
    """Normaliza o validado.json → lista de {codJob, CodQuestao, respostaIds|None, allResponses}.

    Não há mais ancoragem por job separada: a chave (codJob, CodQuestao) já é
    específica de uma pergunta em uma pesquisa — o que no modelo antigo exigia
    passar `codJobs` à parte, porque o InfoID atravessava vários jobs.
    """
    out = []
    for v in data.get("validados", []):
        job, questao = int(v["codJob"]), int(v["CodQuestao"])
        if v.get("allResponses"):
            out.append({"codJob": job, "CodQuestao": questao,
                        "respostaIds": None, "allResponses": True})
            continue
        rids = [int(x) for x in v.get("respostaIds", [])]
        if not rids:
            continue
        out.append({"codJob": job, "CodQuestao": questao,
                    "respostaIds": rids, "allResponses": False})
    return out
