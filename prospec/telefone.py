"""Normalização de telefones brasileiros."""
from __future__ import annotations

import re


def digitos(txt: str) -> str:
    return re.sub(r"\D", "", txt or "")


def para_e164(numero: str, ddi: str = "55") -> str:
    """'(19) 99876-5432' -> '5519998765432'. Devolve '' se não parecer válido."""
    d = digitos(numero)
    if not d:
        return ""
    d = d.lstrip("0")
    if d.startswith(ddi) and len(d) in (12, 13):
        return d
    if len(d) in (10, 11):
        return ddi + d
    return ""


def eh_celular(e164: str) -> bool:
    """Celular BR: DDI 55 + DDD (2) + 9 dígitos começando com 9."""
    return len(e164) == 13 and e164.startswith("55") and e164[4] == "9"


def formatar(e164: str) -> str:
    if len(e164) == 13:
        return f"({e164[2:4]}) {e164[4:9]}-{e164[9:]}"
    if len(e164) == 12:
        return f"({e164[2:4]}) {e164[4:8]}-{e164[8:]}"
    return e164
