"""Busca de empresas no Google Maps pela API oficial (Places API New + Geocoding).

Por que a API e não raspagem: raspar o site do Maps viola os termos do Google, quebra
com frequência e leva a bloqueio de IP. A API é estável e tem cota gratuita mensal.

Limite importante: cada Text Search devolve no máximo 60 resultados (3 páginas de 20).
Para cobrir uma cidade inteira, o modo "grade" divide a área em células e busca em cada
uma, e o modo "bairros" repete a busca por bairro. Os resultados são deduplicados por place_id.
"""
from __future__ import annotations

import hashlib
import os
import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import requests

from .models import Lead
from .telefone import eh_celular, para_e164

URL_BUSCA = "https://places.googleapis.com/v1/places:searchText"
URL_DETALHE = "https://places.googleapis.com/v1/places/{id}"
URL_GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"

CAMPOS = ",".join(f"places.{c}" for c in [
    "id", "displayName", "formattedAddress", "addressComponents", "location",
    "nationalPhoneNumber", "internationalPhoneNumber", "websiteUri", "googleMapsUri",
    "rating", "userRatingCount", "priceLevel", "businessStatus", "types", "primaryType",
    "primaryTypeDisplayName", "regularOpeningHours.weekdayDescriptions",
]) + ",nextPageToken"

PRECO = {"PRICE_LEVEL_FREE": "grátis", "PRICE_LEVEL_INEXPENSIVE": "$",
         "PRICE_LEVEL_MODERATE": "$$", "PRICE_LEVEL_EXPENSIVE": "$$$",
         "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$"}


class ErroMaps(RuntimeError):
    pass


@dataclass
class Retangulo:
    sul: float
    oeste: float
    norte: float
    leste: float

    def dividir(self, n: int) -> list["Retangulo"]:
        dlat = (self.norte - self.sul) / n
        dlng = (self.leste - self.oeste) / n
        return [Retangulo(self.sul + i * dlat, self.oeste + j * dlng,
                          self.sul + (i + 1) * dlat, self.oeste + (j + 1) * dlng)
                for i in range(n) for j in range(n)]

    def api(self) -> dict:
        return {"rectangle": {"low": {"latitude": self.sul, "longitude": self.oeste},
                              "high": {"latitude": self.norte, "longitude": self.leste}}}


def _cidade(componentes: list[dict]) -> str:
    cidade = uf = ""
    for c in componentes or []:
        tipos = c.get("types", [])
        if "administrative_area_level_2" in tipos or ("locality" in tipos and not cidade):
            cidade = c.get("longText", "")
        if "administrative_area_level_1" in tipos:
            uf = c.get("shortText", "")
    return f"{cidade}/{uf}" if cidade and uf else cidade


def place_para_lead(p: dict, consulta: str = "") -> Lead:
    tel = p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber") or ""
    e164 = para_e164(tel)
    loc = p.get("location") or {}
    return Lead(
        place_id=p["id"],
        nome=(p.get("displayName") or {}).get("text", ""),
        categoria=(p.get("primaryTypeDisplayName") or {}).get("text", "") or p.get("primaryType", ""),
        tipos=p.get("types", []),
        endereco=p.get("formattedAddress", ""),
        cidade=_cidade(p.get("addressComponents", [])),
        lat=loc.get("latitude"), lng=loc.get("longitude"),
        telefone=p.get("nationalPhoneNumber", ""),
        telefone_e164=e164, celular=eh_celular(e164),
        site=p.get("websiteUri", ""),
        maps_url=p.get("googleMapsUri", ""),
        nota=p.get("rating"), avaliacoes=p.get("userRatingCount", 0) or 0,
        faixa_preco=PRECO.get(p.get("priceLevel", ""), ""),
        status_negocio=p.get("businessStatus", ""),
        horario=(p.get("regularOpeningHours") or {}).get("weekdayDescriptions", []),
        consulta=consulta,
    )


class GoogleMaps:
    def __init__(self, chave: Optional[str] = None, idioma: str = "pt-BR", regiao: str = "BR"):
        self.chave = chave or os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not self.chave:
            raise ErroMaps("Defina GOOGLE_MAPS_API_KEY (ou use --mock para testar sem API).")
        self.idioma, self.regiao = idioma, regiao
        self.s = requests.Session()
        self.chamadas = 0

    def _post(self, corpo: dict) -> dict:
        for tentativa in range(4):
            r = self.s.post(URL_BUSCA, json=corpo, timeout=30, headers={
                "X-Goog-Api-Key": self.chave, "X-Goog-FieldMask": CAMPOS})
            self.chamadas += 1
            if r.status_code in (429, 500, 503):
                time.sleep(2 ** tentativa)
                continue
            if r.status_code != 200:
                raise ErroMaps(f"Places API {r.status_code}: {r.text[:300]}")
            return r.json()
        raise ErroMaps("Places API indisponível após várias tentativas")

    def area(self, local: str) -> Retangulo:
        """Retângulo (viewport) de uma cidade/bairro via Geocoding API."""
        r = self.s.get(URL_GEOCODE, params={"address": local, "key": self.chave,
                                            "language": self.idioma, "region": self.regiao.lower()},
                       timeout=30)
        self.chamadas += 1
        dados = r.json()
        if dados.get("status") != "OK":
            raise ErroMaps(f"Geocoding falhou para '{local}': {dados.get('status')} "
                           f"{dados.get('error_message', '')}")
        vp = dados["results"][0]["geometry"]["viewport"]
        return Retangulo(vp["southwest"]["lat"], vp["southwest"]["lng"],
                         vp["northeast"]["lat"], vp["northeast"]["lng"])

    def buscar_texto(self, consulta: str, max_resultados: int = 60,
                     restricao: Optional[Retangulo] = None, nota_minima: Optional[float] = None) -> list[dict]:
        corpo = {"textQuery": consulta, "languageCode": self.idioma, "regionCode": self.regiao,
                 "pageSize": 20}
        if restricao:
            corpo["locationRestriction"] = restricao.api()
        if nota_minima:
            corpo["minRating"] = nota_minima
        lugares: list[dict] = []
        while len(lugares) < max_resultados:
            dados = self._post(corpo)
            lugares += dados.get("places", [])
            token = dados.get("nextPageToken")
            if not token:
                break
            corpo["pageToken"] = token
            time.sleep(1.5)  # o token demora um instante para ficar válido
        return lugares[:max_resultados]


class MapsMock:
    """Gera empresas fictícias (determinísticas) para testar sem gastar API."""

    chamadas = 0

    def area(self, local: str) -> Retangulo:
        return Retangulo(-22.95, -47.15, -22.85, -47.0)

    def buscar_texto(self, consulta: str, max_resultados: int = 60,
                     restricao: Optional[Retangulo] = None, nota_minima: Optional[float] = None) -> list[dict]:
        self.chamadas += 1
        semente = consulta + (str(round(restricao.sul, 3)) if restricao else "")
        rnd = random.Random(hashlib.md5(semente.encode()).hexdigest())
        termo = consulta.split(" em ")[0].strip().title() or "Empresa"
        prefixos = ["Clínica", "Studio", "Centro", "Espaço", "Casa", "Grupo", "Instituto", "Ponto"]
        sufixos = ["Vida", "Sorriso", "Bem Estar", "Prime", "Central", "do Bairro", "Popular", "Premium"]
        out = []
        for i in range(min(max_resultados, rnd.randint(8, 25))):
            nome = f"{rnd.choice(prefixos)} {termo} {rnd.choice(sufixos)}"
            pid = "mock_" + hashlib.md5(f"{nome}{i}{semente}".encode()).hexdigest()[:16]
            cel = rnd.random() < 0.6
            num = f"+55 19 9{rnd.randint(8000, 9999)}-{rnd.randint(1000, 9999)}" if cel else \
                  f"+55 19 3{rnd.randint(200, 999)}-{rnd.randint(1000, 9999)}"
            tem_site = rnd.random() < 0.55
            nota = round(rnd.uniform(3.2, 5.0), 1)
            if nota_minima and nota < nota_minima:
                continue
            out.append({
                "id": pid, "displayName": {"text": nome},
                "formattedAddress": f"Rua {rnd.randint(1, 900)} de Exemplo, {rnd.randint(10, 2000)} - Campinas - SP",
                "addressComponents": [{"longText": "Campinas", "types": ["administrative_area_level_2"]},
                                      {"shortText": "SP", "types": ["administrative_area_level_1"]}],
                "location": {"latitude": -22.9 + rnd.uniform(-0.05, 0.05),
                             "longitude": -47.06 + rnd.uniform(-0.05, 0.05)},
                "internationalPhoneNumber": num, "nationalPhoneNumber": num.replace("+55 ", ""),
                "websiteUri": f"https://{pid[5:13]}.exemplo.com.br" if tem_site else "",
                "googleMapsUri": f"https://maps.google.com/?cid={rnd.randint(10**15, 10**16)}",
                "rating": nota, "userRatingCount": rnd.choice([3, 8, 15, 27, 60, 140, 420]),
                "businessStatus": "OPERATIONAL" if rnd.random() > 0.05 else "CLOSED_TEMPORARILY",
                "types": ["establishment"], "primaryTypeDisplayName": {"text": termo},
            })
        return out


def buscar(cliente, consultas: Iterable[str], locais: Iterable[str], grade: int = 1,
           max_por_busca: int = 60, nota_minima: Optional[float] = None,
           log: Callable[[str], None] = print) -> list[Lead]:
    """Executa consultas × locais (× células da grade) e devolve leads sem duplicatas."""
    vistos: dict[str, Lead] = {}
    for consulta in consultas:
        for local in (list(locais) or [""]):
            texto = f"{consulta} em {local}" if local else consulta
            if grade > 1 and local:
                celulas = cliente.area(local).dividir(grade)
            else:
                celulas = [None]
            antes = len(vistos)
            for cel in celulas:
                for p in cliente.buscar_texto(texto, max_por_busca, cel, nota_minima):
                    if p["id"] not in vistos:
                        vistos[p["id"]] = place_para_lead(p, consulta=texto)
            log(f"🔎 {texto}: {len(vistos) - antes} novos ({len(celulas)} célula(s))")
    return list(vistos.values())


def estimar_chamadas(consultas: int, locais: int, grade: int, max_por_busca: int) -> int:
    paginas = max(1, -(-max_por_busca // 20))
    return consultas * max(1, locais) * (grade * grade) * paginas
