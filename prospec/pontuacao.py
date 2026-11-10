"""Qualificação de leads: pontua de 0 a 100 com regras configuráveis.

As regras padrão pensam num prestador de serviços digitais (site, tráfego, social media,
automação): quanto mais "buracos" digitais e mais fácil de contatar, mais quente o lead.
Ajuste os pesos no YAML da campanha (chave `pesos`) para o seu tipo de oferta.
"""
from __future__ import annotations

from .models import Lead

PESOS_PADRAO = {
    "sem_site": 25,
    "site_fora_do_ar": 20,
    "sem_https": 8,
    "site_lento": 6,           # > 4 s
    "sem_pixel": 8,
    "sem_analytics": 5,
    "sem_instagram": 8,
    "poucas_avaliacoes": 12,   # < 20 avaliações
    "nota_baixa": 8,           # nota < 4.2
    "tem_whatsapp": 12,
    "tem_email": 5,
    "negocio_estabelecido": 6,  # >= 50 avaliações (tem caixa para investir)
}

FAIXAS = {"quente": 55, "morno": 30}


def pontuar(lead: Lead, pesos: dict | None = None) -> Lead:
    p = {**PESOS_PADRAO, **(pesos or {})}
    pontos, motivos = 0, []

    def add(chave: str, motivo: str):
        nonlocal pontos
        if p.get(chave):
            pontos += p[chave]
            motivos.append(motivo)

    if lead.status_negocio and lead.status_negocio != "OPERATIONAL":
        lead.score, lead.temperatura = 0, "descartado"
        lead.motivos = [f"Negócio com status {lead.status_negocio}"]
        return lead

    enriquecido = lead.enriquecido_em is not None
    if not lead.site:
        add("sem_site", "Não tem site")
    elif lead.site_ok is False:
        add("site_fora_do_ar", "Site fora do ar ou com erro")
    elif enriquecido:
        if lead.site_https is False:
            add("sem_https", "Site sem HTTPS (aparece como 'não seguro')")
        if (lead.site_tempo_ms or 0) > 4000:
            add("site_lento", f"Site lento ({(lead.site_tempo_ms or 0) / 1000:.1f}s)")
        if "Meta Pixel" not in lead.tecnologias:
            add("sem_pixel", "Sem Pixel da Meta (não faz remarketing)")
        if not {"Google Analytics", "Google Tag Manager"} & set(lead.tecnologias):
            add("sem_analytics", "Sem Google Analytics/GTM")
    if enriquecido and "instagram" not in lead.redes:
        add("sem_instagram", "Instagram não encontrado")
    if lead.avaliacoes < 20:
        add("poucas_avaliacoes", f"Poucas avaliações no Google ({lead.avaliacoes})")
    if lead.nota is not None and lead.nota < 4.2:
        add("nota_baixa", f"Nota baixa no Google ({lead.nota})")
    if lead.whatsapp:
        add("tem_whatsapp", "Tem WhatsApp para contato direto")
    if lead.emails:
        add("tem_email", "Tem e-mail")
    if lead.avaliacoes >= 50:
        add("negocio_estabelecido", f"Negócio estabelecido ({lead.avaliacoes} avaliações)")

    lead.score = max(0, min(100, pontos))
    lead.temperatura = ("quente" if lead.score >= FAIXAS["quente"]
                        else "morno" if lead.score >= FAIXAS["morno"] else "frio")
    lead.motivos = motivos
    return lead


def passa_filtros(lead: Lead, f: dict | None) -> bool:
    """Filtros da campanha: nota_min, nota_max, avaliacoes_min, avaliacoes_max,
    so_sem_site, so_com_site, so_com_whatsapp, excluir_palavras, score_min."""
    f = f or {}
    if f.get("nota_min") is not None and (lead.nota or 0) < f["nota_min"]:
        return False
    if f.get("nota_max") is not None and lead.nota is not None and lead.nota > f["nota_max"]:
        return False
    if f.get("avaliacoes_min") is not None and lead.avaliacoes < f["avaliacoes_min"]:
        return False
    if f.get("avaliacoes_max") is not None and lead.avaliacoes > f["avaliacoes_max"]:
        return False
    if f.get("so_sem_site") and lead.site:
        return False
    if f.get("so_com_site") and not lead.site:
        return False
    if f.get("so_com_whatsapp") and not lead.whatsapp:
        return False
    nome = lead.nome.lower()
    if any(p.lower() in nome for p in f.get("excluir_palavras", [])):
        return False
    if f.get("score_min") is not None and lead.score < f["score_min"]:
        return False
    return True
