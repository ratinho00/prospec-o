"""Modelos de dados do Prospec."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

STATUS = ["novo", "qualificado", "contatado", "respondeu", "reuniao", "proposta",
          "fechado", "perdido", "nao_contatar"]


class Lead(BaseModel):
    place_id: str
    nome: str
    categoria: str = ""
    tipos: list[str] = Field(default_factory=list)
    endereco: str = ""
    cidade: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    telefone: str = ""            # como o Google devolve (nacional)
    telefone_e164: str = ""       # só dígitos com DDI, ex.: 5519999999999
    celular: bool = False         # provável WhatsApp
    site: str = ""
    maps_url: str = ""
    nota: Optional[float] = None
    avaliacoes: int = 0
    faixa_preco: str = ""
    status_negocio: str = ""      # OPERATIONAL, CLOSED_TEMPORARILY...
    horario: list[str] = Field(default_factory=list)
    # enriquecimento do site
    emails: list[str] = Field(default_factory=list)
    telefones_site: list[str] = Field(default_factory=list)
    redes: dict[str, str] = Field(default_factory=dict)  # instagram, facebook, linkedin, whatsapp...
    tecnologias: list[str] = Field(default_factory=list)
    site_https: Optional[bool] = None
    site_ok: Optional[bool] = None
    site_tempo_ms: Optional[int] = None
    site_titulo: str = ""
    enriquecido_em: Optional[str] = None
    # qualificação e CRM
    score: int = 0
    temperatura: str = ""         # quente / morno / frio
    motivos: list[str] = Field(default_factory=list)
    status: str = "novo"
    tags: list[str] = Field(default_factory=list)
    notas: str = ""
    campanha: str = ""
    consulta: str = ""
    proximo_followup: Optional[str] = None
    etapa_cadencia: int = 0
    criado_em: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    atualizado_em: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def whatsapp(self) -> str:
        """Número para wa.me: o do site (se houver) ou o celular do Maps."""
        wa = self.redes.get("whatsapp", "")
        if wa:
            return wa
        return self.telefone_e164 if self.celular else ""


class MensagemIA(BaseModel):
    """Saída estruturada da personalização com Claude."""
    gancho: str = Field(description="Observação específica sobre o negócio que abre a conversa")
    whatsapp: str = Field(description="Mensagem curta de WhatsApp, até 500 caracteres, tom humano")
    email_assunto: str
    email_corpo: str
    roteiro_ligacao: str = Field(description="Roteiro de ligação em tópicos curtos")
