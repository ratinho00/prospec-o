"""Mensagens de abordagem: modelos com variáveis, personalização com Claude,
links de WhatsApp (wa.me) e envio de e-mail por SMTP com limite diário."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from string import Formatter
from typing import Optional
from urllib.parse import quote

from .models import Lead, MensagemIA

MODELO_PADRAO = os.environ.get("PROSPEC_MODEL", "claude-opus-5-5")

MODELOS = {
    "whatsapp": [
        "Oi, tudo bem? Aqui é {meu_nome}, da {minha_empresa}. Encontrei o perfil \"{nome}\" no Google Maps "
        "e reparei que {gancho}. Ajudo {categoria_plural} de {cidade} a {beneficio}. "
        "Posso te mandar uma ideia rápida de como faríamos isso para vocês?",
        "Oi! Passando de novo por aqui 🙂 Consegui separar 2 sugestões práticas para vocês "
        "atrairem mais clientes pelo Google. Quer que eu te mande por aqui mesmo?",
        "Último contato da minha parte, prometo! Se fizer sentido conversar sobre {beneficio}, "
        "é só me responder. Se não for o momento, sem problema — muito sucesso para vocês!",
    ],
    "email_assunto": "Uma ideia rápida para {nome}",
    "email": (
        "Olá! Tudo bem?\n\n"
        "Meu nome é {meu_nome}, da {minha_empresa}. Estava pesquisando {categoria_plural} em {cidade} "
        "no Google Maps, encontrei o perfil \"{nome}\" e notei que {gancho}.\n\n"
        "Ajudamos negócios como o de vocês a {beneficio}. Posso enviar um diagnóstico gratuito de 5 minutos "
        "com o que eu mudaria primeiro?\n\n"
        "Abraço,\n{meu_nome}\n{minha_empresa}\n\n"
        "—\nSe preferir não receber mais mensagens, é só responder \"remover\"."
    ),
}

GANCHOS = {
    "Não tem site": "vocês ainda não têm um site aparecendo no perfil",
    "Site fora do ar ou com erro": "o site do perfil não está abrindo",
    "Site sem HTTPS": "o site aparece como \"não seguro\" no navegador",
    "Site lento": "o site está demorando para carregar no celular",
    "Sem Pixel da Meta": "o site não está medindo quem visita para anunciar depois",
    "Poucas avaliações": "o perfil tem poucas avaliações perto do potencial do negócio",
    "Nota baixa": "algumas avaliações estão puxando a nota do perfil para baixo",
    "Instagram não encontrado": "não achei o Instagram de vocês a partir do Google",
}


class _Seguro(dict):
    def __missing__(self, chave):
        return ""


def variaveis(lead: Lead, perfil: dict) -> dict:
    gancho = next((g for m in lead.motivos for k, g in GANCHOS.items() if m.startswith(k)),
                  "o perfil de vocês tem bastante potencial")
    cat = (lead.categoria or "negócio").lower()
    return _Seguro(
        nome=lead.nome, categoria=cat,
        categoria_plural=perfil.get("categoria_plural") or (cat if cat.endswith("s") else cat + "s"),
        cidade=(lead.cidade.split("/")[0] or perfil.get("cidade", "sua região")),
        nota=lead.nota or "", avaliacoes=lead.avaliacoes, site=lead.site, gancho=gancho,
        motivo_principal=lead.motivos[0] if lead.motivos else "",
        meu_nome=perfil.get("meu_nome", "[seu nome]"),
        minha_empresa=perfil.get("minha_empresa", "[sua empresa]"),
        beneficio=perfil.get("beneficio", "atrair mais clientes pela internet"),
    )


def renderizar(modelo: str, lead: Lead, perfil: dict) -> str:
    return Formatter().vformat(modelo, (), variaveis(lead, perfil)).strip()


def link_whatsapp(numero_e164: str, texto: str) -> str:
    return f"https://wa.me/{numero_e164}?text={quote(texto)}" if numero_e164 else ""


def mensagem_modelo(lead: Lead, perfil: dict, etapa: int = 0, modelos: Optional[dict] = None) -> dict:
    m = {**MODELOS, **(modelos or {})}
    seq = m["whatsapp"]
    wa = renderizar(seq[min(etapa, len(seq) - 1)], lead, perfil)
    return {"whatsapp": wa, "link_whatsapp": link_whatsapp(lead.whatsapp, wa),
            "email_assunto": renderizar(m["email_assunto"], lead, perfil),
            "email_corpo": renderizar(m["email"], lead, perfil), "roteiro_ligacao": "", "gancho": ""}


SISTEMA_IA = (
    "Você escreve mensagens de prospecção B2B em português do Brasil para pequenos negócios locais. "
    "Regras: tom humano e respeitoso, sem exageros, sem promessas de resultado, sem emojis em excesso, "
    "sem inventar fatos — use apenas os dados fornecidos. Comece por uma observação concreta sobre o "
    "negócio (o gancho), mostre um benefício claro e termine com uma pergunta simples de baixo "
    "compromisso. WhatsApp com no máximo 500 caracteres. E-mail curto (até 120 palavras) e com uma "
    "linha final de opt-out (\"responda 'remover' para não receber mais\")."
)


class Redator:
    """Personaliza mensagens com Claude (saída estruturada)."""

    def __init__(self, modelo: str = MODELO_PADRAO):
        import anthropic  # import tardio: só é necessário quando a IA é usada

        self.client = anthropic.Anthropic(max_retries=4)
        self.modelo = modelo
        self.chamadas = 0

    def escrever(self, lead: Lead, perfil: dict, etapa: int = 0) -> dict:
        from .llm import schema_estrito

        dados = {
            "nome": lead.nome, "categoria": lead.categoria, "cidade": lead.cidade,
            "nota_google": lead.nota, "avaliacoes": lead.avaliacoes, "site": lead.site or "não tem",
            "titulo_site": lead.site_titulo, "redes": list(lead.redes), "tecnologias": lead.tecnologias,
            "oportunidades_detectadas": lead.motivos,
        }
        prompt = (
            f"Quem envia: {perfil.get('meu_nome')} da {perfil.get('minha_empresa')}.\n"
            f"Oferta: {perfil.get('oferta') or perfil.get('beneficio')}\n"
            f"Etapa da cadência: {'primeiro contato' if etapa == 0 else f'follow-up nº {etapa}'}\n"
            f"Dados do lead (Google Maps + site): {dados}"
        )
        resp = self.client.beta.messages.create(
            model=self.modelo,
            max_tokens=4000,
            system=SISTEMA_IA,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": schema_estrito(MensagemIA)}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        self.chamadas += 1
        if resp.stop_reason == "refusal":
            raise RuntimeError("O modelo recusou gerar a mensagem para este lead.")
        texto = next(b.text for b in resp.content if b.type == "text")
        m = MensagemIA.model_validate_json(texto)
        return {**m.model_dump(), "link_whatsapp": link_whatsapp(lead.whatsapp, m.whatsapp)}


# ---------------- e-mail ----------------
class EnviadorEmail:
    """SMTP com limite por execução. Configure: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM."""

    def __init__(self, limite: int = 30):
        self.host = os.environ.get("SMTP_HOST", "")
        self.porta = int(os.environ.get("SMTP_PORT", "587"))
        self.usuario = os.environ.get("SMTP_USER", "")
        self.senha = os.environ.get("SMTP_PASS", "")
        self.remetente = os.environ.get("SMTP_FROM", self.usuario)
        self.limite = limite
        self.enviados = 0
        if not (self.host and self.usuario and self.senha):
            raise RuntimeError("Configure SMTP_HOST, SMTP_USER e SMTP_PASS para enviar e-mails.")

    def enviar(self, para: str, assunto: str, corpo: str) -> bool:
        if self.enviados >= self.limite:
            return False
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.remetente, para, assunto
        msg["List-Unsubscribe"] = f"<mailto:{self.remetente}?subject=remover>"
        msg.set_content(corpo)
        with smtplib.SMTP(self.host, self.porta, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(self.usuario, self.senha)
            s.send_message(msg)
        self.enviados += 1
        return True
