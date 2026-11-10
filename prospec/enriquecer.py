"""Enriquecimento: visita o site do lead e extrai e-mails, telefones, redes sociais,
WhatsApp e sinais de maturidade digital (pixel, analytics, plataforma, HTTPS)."""
from __future__ import annotations

import hashlib
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import unquote, urljoin, urlparse

import requests

from .models import Lead
from .telefone import eh_celular, para_e164

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
RE_TEL = re.compile(r"(?:\+?55\s?)?\(?\b[1-9]{2}\)?\s?9?\d{4}[-\s.]?\d{4}\b")
RE_HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
RE_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
RE_WA = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|web\.whatsapp\.com/send\?phone=)\+?(\d{10,13})", re.I)

REDES = {
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/(?!p/|reel/|explore/|share)([A-Za-z0-9_.]+)", re.I),
    "facebook": re.compile(r"https?://(?:www\.|m\.)?facebook\.com/(?!sharer|share|plugins|tr\b|dialog)([A-Za-z0-9_.\-/]+)", re.I),
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_\-%]+", re.I),
    "tiktok": re.compile(r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9_.]+", re.I),
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/(?:@|channel/|c/|user/)[A-Za-z0-9_\-]+", re.I),
}

TECNOLOGIAS = {
    "Google Analytics": [r"gtag\(", r"google-analytics\.com", r"googletagmanager\.com/gtag"],
    "Google Tag Manager": [r"googletagmanager\.com/gtm\.js", r"GTM-[A-Z0-9]+"],
    "Meta Pixel": [r"fbq\(", r"connect\.facebook\.net/.*/fbevents\.js"],
    "Google Ads": [r"AW-\d{6,}", r"googleadservices\.com"],
    "WordPress": [r"wp-content/", r"wp-includes/"],
    "Wix": [r"wix\.com", r"wixstatic\.com"],
    "Shopify": [r"cdn\.shopify\.com"],
    "Nuvemshop": [r"nuvemshop", r"tiendanube"],
    "Chat/WhatsApp widget": [r"wa\.me/", r"api\.whatsapp\.com", r"joinchat", r"tawk\.to", r"jivosite"],
    "Agendamento online": [r"calendly\.com", r"doctoralia", r"agendor", r"simplesagenda", r"booksy"],
    "Responsivo": [r"<meta[^>]+name=[\"']viewport"],
}

LIXO_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|@(sentry|example|exemplo|wixpress|domain)\.|^u00", re.I)
PAGINAS_EXTRA = re.compile(r"contato|contact|fale|sobre|about|quem-somos|atendimento", re.I)


def _baixar(s: requests.Session, url: str, timeout: float) -> Optional[requests.Response]:
    try:
        r = s.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": UA})
        if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
            return r
    except requests.RequestException:
        pass
    return None


def analisar_html(html: str, lead: Lead) -> None:
    """Extrai contatos e tecnologias de um HTML e acumula no lead."""
    texto = unquote(html)
    for e in RE_EMAIL.findall(texto):
        e = e.lower().strip(".")
        if not LIXO_EMAIL.search(e) and e not in lead.emails:
            lead.emails.append(e)
    for t in RE_TEL.findall(re.sub(r"<[^>]+>", " ", texto)):
        e164 = para_e164(t)
        if e164 and e164 not in lead.telefones_site and e164 != lead.telefone_e164:
            lead.telefones_site.append(e164)
    wa = RE_WA.search(texto)
    if wa and "whatsapp" not in lead.redes:
        n = para_e164(wa.group(1))
        if n:
            lead.redes["whatsapp"] = n
    for rede, rx in REDES.items():
        if rede not in lead.redes:
            m = rx.search(texto)
            if m:
                lead.redes[rede] = m.group(0).rstrip("/")
    for tec, padroes in TECNOLOGIAS.items():
        if tec not in lead.tecnologias and any(re.search(p, html, re.I) for p in padroes):
            lead.tecnologias.append(tec)
    if not lead.site_titulo:
        m = RE_TITULO.search(html)
        if m:
            lead.site_titulo = re.sub(r"\s+", " ", m.group(1)).strip()[:150]


def enriquecer_lead(lead: Lead, max_paginas: int = 3, timeout: float = 12) -> Lead:
    lead.enriquecido_em = datetime.now().isoformat(timespec="seconds")
    if not lead.site:
        return lead
    s = requests.Session()
    inicio = time.monotonic()
    r = _baixar(s, lead.site, timeout)
    if r is None:
        lead.site_ok = False
        return lead
    lead.site_ok = True
    lead.site_tempo_ms = int((time.monotonic() - inicio) * 1000)
    lead.site_https = r.url.startswith("https://")
    analisar_html(r.text, lead)

    base = urlparse(r.url).netloc
    extras = []
    for href in RE_HREF.findall(r.text):
        url = urljoin(r.url, href)
        if urlparse(url).netloc == base and PAGINAS_EXTRA.search(url) and url not in extras:
            extras.append(url)
    for url in extras[:max_paginas]:
        p = _baixar(s, url, timeout)
        if p is not None:
            analisar_html(p.text, lead)
    if not lead.celular:  # sem celular no Maps: tenta um celular achado no site
        cel = next((t for t in lead.telefones_site if eh_celular(t)), "")
        if cel and "whatsapp" not in lead.redes:
            lead.redes["whatsapp"] = cel
    return lead


def enriquecer_mock(lead: Lead) -> Lead:
    rnd = random.Random(hashlib.md5(lead.place_id.encode()).hexdigest())
    lead.enriquecido_em = datetime.now().isoformat(timespec="seconds")
    if not lead.site:
        if rnd.random() < 0.5:
            lead.redes["instagram"] = f"https://instagram.com/{lead.place_id[5:13]}"
        return lead
    lead.site_ok = rnd.random() > 0.1
    if not lead.site_ok:
        return lead
    lead.site_https = rnd.random() > 0.25
    lead.site_tempo_ms = rnd.randint(300, 6000)
    lead.site_titulo = lead.nome
    if rnd.random() < 0.7:
        lead.emails = [f"contato@{urlparse(lead.site).netloc}"]
    for rede in ("instagram", "facebook"):
        if rnd.random() < 0.6:
            lead.redes[rede] = f"https://{rede}.com/{lead.place_id[5:13]}"
    lead.tecnologias = [t for t in TECNOLOGIAS if rnd.random() < 0.3]
    return lead


def enriquecer_varios(leads: list[Lead], paralelismo: int = 8, mock: bool = False,
                      log: Callable[[str], None] = print) -> list[Lead]:
    fn = enriquecer_mock if mock else enriquecer_lead
    com_site = sum(1 for l in leads if l.site)
    log(f"🌐 Enriquecendo {len(leads)} leads ({com_site} com site)...")
    with ThreadPoolExecutor(paralelismo) as ex:
        return list(ex.map(fn, leads))
