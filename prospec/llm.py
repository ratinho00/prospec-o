"""Utilitário de schema para structured outputs do Claude."""
from __future__ import annotations

import copy
from typing import Type

from pydantic import BaseModel


def schema_estrito(model: Type[BaseModel]) -> dict:
    """Converte o schema do Pydantic para o formato aceito por structured outputs:
    refs resolvidas, todos os campos obrigatórios e additionalProperties=false."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def resolver(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolver(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            if "anyOf" in node:  # Optional[X] -> X (o modelo sempre preenche)
                opcoes = [o for o in node["anyOf"] if o.get("type") != "null"]
                if len(opcoes) == 1:
                    return resolver(opcoes[0])
            out = {k: resolver(v) for k, v in node.items() if k not in ("title", "default")}
            if out.get("type") == "object":
                if "properties" in out:
                    out["required"] = list(out["properties"].keys())
                    out["additionalProperties"] = False
                else:  # dict livre -> não usado nas saídas do modelo
                    out["additionalProperties"] = False
                    out["properties"] = {}
                    out["required"] = []
            return out
        if isinstance(node, list):
            return [resolver(n) for n in node]
        return node

    return resolver(raw)
