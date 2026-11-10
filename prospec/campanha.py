"""Campanhas: o pipeline completo descrito num YAML, pronto para rodar no cron.

buscar no Maps → filtrar → enriquecer site → pontuar → salvar no CRM →
gerar mensagens dos melhores → exportar planilha → avisar webhook.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import yaml
from pydantic import BaseModel, Field

from .db import Banco
from .enriquecer import enriquecer_varios
from .exportar import enviar_webhook, exportar
from .maps import GoogleMaps, MapsMock, buscar, estimar_chamadas
from .mensagens import Redator, mensagem_modelo
from .models import Lead
from .pontuacao import passa_filtros, pontuar


class Campanha(BaseModel):
    nome: str
    consultas: list[str]
    locais: list[str] = Field(default_factory=list)
    grade: int = 1                      # 1 = busca simples; 3 = divide cada local em 3×3 células
    max_por_busca: int = 60
    nota_minima_api: Optional[float] = None
    filtros: dict = Field(default_factory=dict)
    pesos: dict = Field(default_factory=dict)
    enriquecer: bool = True
    perfil: dict = Field(default_factory=dict)   # meu_nome, minha_empresa, beneficio, oferta...
    modelos: dict = Field(default_factory=dict)  # sobrescreve modelos de mensagem
    mensagens_top: int = 20
    usar_ia: bool = False
    cadencia_dias: list[int] = Field(default_factory=lambda: [3, 7])
    webhook: str = ""
    pasta_saida: str = "saidas"

    @classmethod
    def carregar(cls, caminho: str | Path) -> "Campanha":
        return cls.model_validate(yaml.safe_load(Path(caminho).read_text(encoding="utf-8")))


def executar(c: Campanha, banco: Banco, mock: bool = False, sem_ia: bool = False,
             log: Callable[[str], None] = print) -> dict:
    est = estimar_chamadas(len(c.consultas), len(c.locais), c.grade, c.max_por_busca)
    log(f"🚀 Campanha '{c.nome}': até ~{est} chamadas à Places API")
    cliente = MapsMock() if mock else GoogleMaps()

    encontrados = buscar(cliente, c.consultas, c.locais, c.grade, c.max_por_busca,
                         c.nota_minima_api, log=log)
    ja_existiam = {l.place_id for l in encontrados if banco.obter(l.place_id)}
    novos = [l for l in encontrados if l.place_id not in ja_existiam]
    log(f"📍 {len(encontrados)} empresas encontradas, {len(novos)} inéditas")

    candidatos = [l for l in novos if passa_filtros(l, {k: v for k, v in c.filtros.items() if k != "score_min"})]
    if c.enriquecer and candidatos:
        candidatos = enriquecer_varios(candidatos, mock=mock, log=log)
    candidatos = [pontuar(l, c.pesos) for l in candidatos]
    candidatos = [l for l in candidatos if passa_filtros(l, c.filtros)]
    for l in candidatos:
        if l.status == "novo" and l.temperatura == "quente":
            l.status = "qualificado"
    n_novos, _ = banco.salvar(candidatos, campanha=c.nome)
    banco.registrar_busca(c.nome, " | ".join(c.consultas), len(encontrados), n_novos)
    log(f"💾 {n_novos} leads novos salvos no CRM (filtrados: {len(novos) - len(candidatos)})")

    saida = Path(c.pasta_saida) / f"{c.nome}-{datetime.now():%Y%m%d-%H%M}"
    saida.mkdir(parents=True, exist_ok=True)
    top = sorted((l for l in candidatos if l.status != "nao_contatar"), key=lambda l: -l.score)[:c.mensagens_top]
    caminho_msgs = gerar_mensagens(top, c.perfil, saida / "mensagens.md", usar_ia=c.usar_ia and not sem_ia,
                                   mock=mock, modelos=c.modelos, log=log)
    planilha = exportar(candidatos, saida / "leads.xlsx")
    log(f"📊 Planilha: {planilha}")
    if c.webhook and candidatos:
        log(f"🔗 Webhook: {enviar_webhook(c.webhook, candidatos)} leads enviados")
    return {"encontrados": len(encontrados), "novos": n_novos, "qualificados": len(top),
            "pasta": str(saida), "mensagens": str(caminho_msgs), "planilha": str(planilha)}


def gerar_mensagens(leads: list[Lead], perfil: dict, arquivo: Path, usar_ia: bool = False,
                    mock: bool = False, modelos: Optional[dict] = None,
                    log: Callable[[str], None] = print) -> Path:
    redator = Redator() if usar_ia and not mock else None
    partes = [f"# Mensagens de abordagem — {datetime.now():%d/%m/%Y %H:%M}\n"]
    for l in leads:
        etapa = l.etapa_cadencia
        if redator:
            try:
                m = redator.escrever(l, perfil, etapa)
            except Exception as e:  # noqa: BLE001 — cai para o modelo fixo
                log(f"⚠️ IA falhou para {l.nome}: {e}")
                m = mensagem_modelo(l, perfil, etapa, modelos)
        else:
            m = mensagem_modelo(l, perfil, etapa, modelos)
        partes.append(
            f"## {l.nome} — score {l.score} ({l.temperatura})\n"
            f"- {l.categoria} · {l.cidade} · ⭐ {l.nota} ({l.avaliacoes}) · {l.maps_url}\n"
            f"- Oportunidades: {'; '.join(l.motivos)}\n"
            f"- place_id: `{l.place_id}`\n\n"
            + (f"**WhatsApp** ([abrir conversa]({m['link_whatsapp']})):\n\n> {m['whatsapp']}\n\n"
               if m["link_whatsapp"] else f"**WhatsApp:** sem número de celular\n\n")
            + (f"**E-mail** para {', '.join(l.emails)} — *{m['email_assunto']}*\n\n```\n{m['email_corpo']}\n```\n\n"
               if l.emails else "")
            + (f"**Roteiro de ligação** ({l.telefone}):\n\n{m['roteiro_ligacao']}\n\n" if m.get("roteiro_ligacao") else "")
        )
    arquivo.write_text("\n".join(partes), encoding="utf-8")
    log(f"✉️  {len(leads)} mensagens em {arquivo}" + (f" ({redator.chamadas} chamadas à IA)" if redator else ""))
    return arquivo
