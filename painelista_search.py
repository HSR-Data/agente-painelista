"""Lógica pura + conexão para a busca semântica de painelistas (standalone)."""
import os
import sys

import pyodbc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DatabaseConfig

# Collation case- e accent-insensitive para os LIKE (dispensa lower/strip manual).
COLLATE = "Latin1_General_CI_AI"


def escape_like(term: str) -> str:
    """Escapa curingas de LIKE para casar o termo literalmente. Usar com ESCAPE '\\'."""
    return (term.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                .replace("[", "\\["))


def like_pattern(term: str) -> str:
    """Padrão `%termo%` já escapado, para `col COLLATE ... LIKE ? ESCAPE '\\'`."""
    return "%" + escape_like(term.strip()) + "%"


def pick_driver(available) -> str:
    """Prefere ODBC Driver 18, cai para 17. Erro claro se nenhum existir."""
    for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if d in available:
            return d
    raise RuntimeError(
        "Nenhum ODBC Driver 17/18 para SQL Server encontrado. "
        "Instale o msodbcsql18 (veja o README). Drivers disponiveis: " + str(available))


def make_connection():
    """Conexão pyodbc ao banco Falai_Painelista_Data (endereço/credenciais do .env)."""
    faltando = [nome for nome, val in (
        ("DB_SERVER", DatabaseConfig.SERVER), ("DB_USER", DatabaseConfig.USER),
        ("DB_PASSWORD", DatabaseConfig.PASSWORD), ("DB_DATABASE", DatabaseConfig.DATABASE),
    ) if not val]
    if faltando:
        raise RuntimeError(
            "Configuração do banco incompleta (faltando: " + ", ".join(faltando) + "). "
            "Coloque o arquivo .env preenchido nesta pasta antes de rodar. "
            "Peça o .env para quem te passou a ferramenta.")
    driver = pick_driver(pyodbc.drivers())
    cs = (
        f"DRIVER={{{driver}}};SERVER={DatabaseConfig.SERVER},{DatabaseConfig.PORT};"
        f"DATABASE={DatabaseConfig.DATABASE};UID={DatabaseConfig.USER};PWD={DatabaseConfig.PASSWORD};"
        f"TrustServerCertificate=yes;Encrypt=no;Connection Timeout=30;"
    )
    return pyodbc.connect(cs)


# ── Montagem do "seed" (candidatos) que o subagente vai julgar ────────
def _clip(s, n):
    """Encurta texto longo (o subagente só precisa do sentido pra julgar)."""
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def build_seed_bundle(term, matched_responses, question_infoids, label_infoids,
                      info_meta, questions_by_info, responses_by_info, freq,
                      max_infoids=300, max_responses_per_infoid=5,
                      sample_questions=2, max_questions_matched=10,
                      max_matched_per_infoid=30, max_text=400):
    matched_by_info = {}
    for r in matched_responses:
        matched_by_info.setdefault(int(r["InfoID"]), []).append(r)

    candidate_ids = set(matched_by_info) | set(question_infoids) | set(label_infoids)
    ordered = sorted(candidate_ids)
    dropped = max(0, len(ordered) - max_infoids)
    kept = ordered[:max_infoids]

    candidatos = []
    for iid in kept:
        casou_por = []
        if iid in matched_by_info:
            casou_por.append("resposta")
        if iid in question_infoids:
            casou_por.append("pergunta")
        if iid in label_infoids:
            casou_por.append("label")

        # respostas que casaram o termo (o subagente escolhe destas os RespostaID de posse).
        # Ordena por frequência e limita: respostas ABERTAS (recall) chegam a centenas e são
        # julgadas PELA PERGUNTA — não precisa despejar todas.
        seen, matched_ranked = set(), []
        for r in matched_by_info.get(iid, []):
            rid = int(r["RespostaID"])
            if rid in seen:
                continue
            seen.add(rid)
            matched_ranked.append(r)
        matched_ranked.sort(key=lambda r: freq.get((iid, int(r["RespostaID"])), 0), reverse=True)
        respostas_match = [{"RespostaID": int(r["RespostaID"]), "Valor": _clip(r["Valor"], max_text)}
                           for r in matched_ranked[:max_matched_per_infoid]]

        # amostra de respostas NÃO casadas: só pra dar noção da escala (decisão de allResponses).
        nm = responses_by_info.get(iid, [])
        nm_ranked = sorted(nm, key=lambda r: freq.get((iid, int(r["RespostaID"])), 0), reverse=True)
        respostas_amostra = [{"RespostaID": int(r["RespostaID"]), "Valor": _clip(r["Valor"], max_text)}
                             for r in nm_ranked[:max_responses_per_infoid]]

        q_cap = max_questions_matched if iid in matched_by_info else sample_questions
        all_questions = questions_by_info.get(iid, [])
        perguntas = [{"texto": _clip(q["texto"], max_text), "codJobs": q["codJobs"]}
                     for q in all_questions[:q_cap]]

        meta = info_meta.get(iid, {})
        cand = {
            "InfoID": iid,
            "Label": _clip(meta.get("Label", ""), max_text),
            "casou_por": casou_por,
            "perguntas": perguntas,
        }
        if respostas_match:
            cand["respostas_match"] = respostas_match
            if len(matched_ranked) > max_matched_per_infoid:
                cand["respostas_match_total"] = len(matched_ranked)
        if respostas_amostra:
            cand["respostas_amostra"] = respostas_amostra
        candidatos.append(cand)

    return {
        "termo": term,
        "total": len(candidatos),
        "limites": {"max_infoids": max_infoids,
                    "max_responses_per_infoid": max_responses_per_infoid,
                    "max_matched_per_infoid": max_matched_per_infoid,
                    "sample_questions": sample_questions,
                    "max_questions_matched": max_questions_matched},
        "truncado": {"infoids_dropados": dropped},
        "candidatos": candidatos,
    }


def parse_validated(data):
    """Normaliza bp_validated.json → lista de {InfoID, respostaIds|None, allResponses, codJobs|None}.

    `codJobs` = jobs das perguntas aprovadas pelo subagente; restringe os respondentes à
    pergunta certa. Ausente/vazio → None (sem restrição de job)."""
    out = []
    for v in data.get("validados", []):
        iid = int(v["InfoID"])
        jobs = [int(j) for j in (v.get("codJobs") or [])] or None
        if v.get("allResponses"):
            out.append({"InfoID": iid, "respostaIds": None, "allResponses": True, "codJobs": jobs})
            continue
        rids = [int(x) for x in v.get("respostaIds", [])]
        if not rids:
            continue
        out.append({"InfoID": iid, "respostaIds": rids, "allResponses": False, "codJobs": jobs})
    return out
