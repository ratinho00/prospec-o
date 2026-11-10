"""Exportação para CSV/Excel e envio de leads para webhooks (n8n, Make, Zapier, CRM)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from .models import Lead
from .telefone import formatar


def tabela(leads: list[Lead]) -> pd.DataFrame:
    return pd.DataFrame([{
        "score": l.score, "temperatura": l.temperatura, "status": l.status, "nome": l.nome,
        "categoria": l.categoria, "cidade": l.cidade, "telefone": formatar(l.telefone_e164) or l.telefone,
        "whatsapp": l.whatsapp, "email": ", ".join(l.emails), "site": l.site,
        "instagram": l.redes.get("instagram", ""), "facebook": l.redes.get("facebook", ""),
        "linkedin": l.redes.get("linkedin", ""), "nota": l.nota, "avaliacoes": l.avaliacoes,
        "oportunidades": "; ".join(l.motivos), "tecnologias": ", ".join(l.tecnologias),
        "endereco": l.endereco, "maps": l.maps_url, "campanha": l.campanha,
        "proximo_followup": l.proximo_followup or "", "tags": ", ".join(l.tags),
        "notas": l.notas, "place_id": l.place_id, "lat": l.lat, "lng": l.lng,
    } for l in leads])


def exportar(leads: list[Lead], arquivo: str | Path) -> Path:
    arquivo = Path(arquivo)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    df = tabela(leads)
    if arquivo.suffix.lower() in (".xlsx", ".xls"):
        with pd.ExcelWriter(arquivo, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Leads")
            ws = w.sheets["Leads"]
            ws.auto_filter.ref = ws.dimensions
            ws.freeze_panes = "A2"
            for col in ws.columns:
                largura = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, largura + 2), 60)
    else:
        df.to_csv(arquivo, index=False, encoding="utf-8-sig", sep=";")
    return arquivo


def enviar_webhook(url: str, leads: list[Lead], lote: int = 50) -> int:
    """POSTa os leads em JSON ({"leads": [...]}) em lotes. Devolve quantos foram enviados."""
    enviados = 0
    for i in range(0, len(leads), lote):
        parte = [l.model_dump() | {"whatsapp": l.whatsapp} for l in leads[i:i + lote]]
        r = requests.post(url, json={"leads": parte}, timeout=30)
        r.raise_for_status()
        enviados += len(parte)
    return enviados
