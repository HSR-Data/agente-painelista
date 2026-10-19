#!/usr/bin/env python3
"""Offline coverage gate. Counts are agent attestations, not proof of judgment."""
import argparse
import json
from pathlib import Path


def check(directory):
    directory = Path(directory)
    batches = sorted(directory.glob("lote_*.json"))
    if not batches:
        raise ValueError("No input batches found")
    expected = {"validado_" + p.name[5:] for p in batches}
    actual = {p.name for p in directory.glob("validado_*.json")}
    if actual != expected:
        raise ValueError("Missing or unexpected validation batches")
    seen = set()
    total = 0
    for path in batches:
        batch = json.loads(path.read_text(encoding="utf-8"))
        result = json.loads((directory / ("validado_" + path.name[5:])).read_text(encoding="utf-8"))
        groups = [c["grupo"] for c in batch["candidatos"]]
        if len(groups) != len(set(groups)) or seen.intersection(groups):
            raise ValueError("Duplicate input groups")
        seen.update(groups)
        n = len(groups)
        if batch["total"] != n or result.get("termo") != batch["termo"]:
            raise ValueError("Term or batch total mismatch")
        if result.get("total_candidatos") != n or result.get("total_avaliados") != n:
            raise ValueError("Partial coverage")
        # multi-conceito: o mesmo grupo pode ser aceito uma vez por conceito
        pairs = [(v["grupo"], v.get("conceito")) for v in result.get("validados", [])]
        accepted = {g for g, _ in pairs}
        if len(pairs) != len(set(pairs)) or not accepted.issubset(groups):
            raise ValueError("Unknown or duplicate accepted groups")
        rejected = result.get("rejeitados_resumo", {}).get("total")
        if not isinstance(rejected, int) or rejected < 0 or len(accepted) + rejected != n:
            raise ValueError("Accepted/rejected count mismatch")
        total += n
    return {"batches": len(batches), "evaluated": total, "status": "complete"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="dados_tmp")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.directory), sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Coverage blocked: {exc}\n")


if __name__ == "__main__":
    main()
