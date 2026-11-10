"""CRM local em SQLite: leads, histórico de interações, buscas e lista de bloqueio."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from .models import STATUS, Lead

CAMINHO_PADRAO = os.environ.get("PROSPEC_DB", "prospec.db")

# campos do Lead gravados em colunas próprias (para filtrar/ordenar); o resto vai no JSON
COLUNAS = ["place_id", "nome", "categoria", "cidade", "telefone_e164", "site", "nota",
           "avaliacoes", "score", "temperatura", "status", "campanha", "proximo_followup",
           "criado_em", "atualizado_em"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
  place_id TEXT PRIMARY KEY, nome TEXT, categoria TEXT, cidade TEXT, telefone_e164 TEXT,
  site TEXT, nota REAL, avaliacoes INTEGER, score INTEGER, temperatura TEXT, status TEXT,
  campanha TEXT, proximo_followup TEXT, criado_em TEXT, atualizado_em TEXT, dados TEXT
);
CREATE INDEX IF NOT EXISTS ix_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS ix_leads_score ON leads(score);
CREATE TABLE IF NOT EXISTS interacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, place_id TEXT, data TEXT, canal TEXT,
  tipo TEXT, texto TEXT
);
CREATE TABLE IF NOT EXISTS buscas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, campanha TEXT, consulta TEXT,
  total INTEGER, novos INTEGER
);
CREATE TABLE IF NOT EXISTS bloqueio (chave TEXT PRIMARY KEY, motivo TEXT, data TEXT);
"""

# campos que o usuário edita no CRM e que uma nova busca não deve sobrescrever
CAMPOS_CRM = ["status", "tags", "notas", "proximo_followup", "etapa_cadencia", "campanha", "criado_em"]


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Banco:
    def __init__(self, caminho: str | Path = CAMINHO_PADRAO):
        self.caminho = str(caminho)
        self.con = sqlite3.connect(self.caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)

    # ---------- leads ----------
    def _gravar(self, lead: Lead) -> None:
        lead.atualizado_em = agora()
        d = lead.model_dump()
        self.con.execute(
            f"INSERT OR REPLACE INTO leads ({','.join(COLUNAS)}, dados) "
            f"VALUES ({','.join('?' * len(COLUNAS))}, ?)",
            [d[c] for c in COLUNAS] + [json.dumps(d, ensure_ascii=False)])

    def salvar(self, leads: Iterable[Lead], campanha: str = "") -> tuple[int, int]:
        """Insere ou atualiza; preserva o que foi editado no CRM. Devolve (novos, atualizados)."""
        novos = atualizados = 0
        for lead in leads:
            antigo = self.obter(lead.place_id)
            if antigo:
                for c in CAMPOS_CRM:
                    setattr(lead, c, getattr(antigo, c))
                if not lead.enriquecido_em and antigo.enriquecido_em:  # não perder enriquecimento
                    for c in ("emails", "telefones_site", "redes", "tecnologias", "site_https",
                              "site_ok", "site_tempo_ms", "site_titulo", "enriquecido_em"):
                        setattr(lead, c, getattr(antigo, c))
                atualizados += 1
            else:
                if campanha:
                    lead.campanha = campanha
                if self.bloqueado(lead):
                    lead.status = "nao_contatar"
                novos += 1
            self._gravar(lead)
        self.con.commit()
        return novos, atualizados

    def atualizar(self, lead: Lead) -> None:
        self._gravar(lead)
        self.con.commit()

    def obter(self, place_id: str) -> Optional[Lead]:
        r = self.con.execute("SELECT dados FROM leads WHERE place_id=?", (place_id,)).fetchone()
        return Lead.model_validate_json(r["dados"]) if r else None

    def listar(self, status: Optional[list[str]] = None, score_min: int = 0,
               campanha: str = "", cidade: str = "", texto: str = "",
               temperatura: str = "", limite: int = 0, ordem: str = "score DESC") -> list[Lead]:
        sql, args = "SELECT dados FROM leads WHERE score >= ?", [score_min]
        if status:
            sql += f" AND status IN ({','.join('?' * len(status))})"
            args += status
        if campanha:
            sql += " AND campanha = ?"
            args.append(campanha)
        if cidade:
            sql += " AND cidade LIKE ?"
            args.append(f"%{cidade}%")
        if temperatura:
            sql += " AND temperatura = ?"
            args.append(temperatura)
        if texto:
            sql += " AND (nome LIKE ? OR categoria LIKE ?)"
            args += [f"%{texto}%"] * 2
        sql += f" ORDER BY {ordem}" + (f" LIMIT {int(limite)}" if limite else "")
        return [Lead.model_validate_json(r["dados"]) for r in self.con.execute(sql, args)]

    def mudar_status(self, place_id: str, status: str, nota: str = "") -> Lead:
        if status not in STATUS:
            raise ValueError(f"Status inválido. Use um de: {', '.join(STATUS)}")
        lead = self.obter(place_id)
        if not lead:
            raise KeyError(place_id)
        anterior, lead.status = lead.status, status
        if status in ("fechado", "perdido", "nao_contatar"):
            lead.proximo_followup = None
        if nota:
            lead.notas = (lead.notas + "\n" if lead.notas else "") + f"[{date.today()}] {nota}"
        self.atualizar(lead)
        self.registrar(place_id, "crm", "status", f"{anterior} → {status}. {nota}".strip())
        return lead

    def campanhas(self) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT campanha FROM leads WHERE campanha != '' ORDER BY 1")]

    # ---------- interações e cadência ----------
    def registrar(self, place_id: str, canal: str, tipo: str, texto: str = "") -> None:
        self.con.execute("INSERT INTO interacoes (place_id, data, canal, tipo, texto) VALUES (?,?,?,?,?)",
                         (place_id, agora(), canal, tipo, texto))
        self.con.commit()

    def historico(self, place_id: str) -> list[dict]:
        return [dict(r) for r in self.con.execute(
            "SELECT data, canal, tipo, texto FROM interacoes WHERE place_id=? ORDER BY id DESC",
            (place_id,))]

    def marcar_contato(self, place_id: str, canal: str, texto: str,
                       cadencia: list[int]) -> Lead:
        """Registra um envio e agenda o próximo follow-up pela cadência (dias)."""
        lead = self.obter(place_id)
        if not lead:
            raise KeyError(place_id)
        self.registrar(place_id, canal, f"envio_{lead.etapa_cadencia}", texto)
        if lead.status in ("novo", "qualificado"):
            lead.status = "contatado"
        if lead.etapa_cadencia < len(cadencia):
            lead.proximo_followup = (date.today() + timedelta(days=cadencia[lead.etapa_cadencia])).isoformat()
        else:
            lead.proximo_followup = None
        lead.etapa_cadencia += 1
        self.atualizar(lead)
        return lead

    def followups_vencidos(self, ate: Optional[date] = None) -> list[Lead]:
        ate = (ate or date.today()).isoformat()
        rows = self.con.execute(
            "SELECT dados FROM leads WHERE proximo_followup IS NOT NULL AND proximo_followup <= ? "
            "AND status IN ('contatado','respondeu','reuniao','proposta') ORDER BY proximo_followup", (ate,))
        return [Lead.model_validate_json(r["dados"]) for r in rows]

    # ---------- bloqueio (opt-out) ----------
    def bloquear(self, chave: str, motivo: str = "pediu para não ser contatado") -> None:
        self.con.execute("INSERT OR REPLACE INTO bloqueio VALUES (?,?,?)", (chave, motivo, agora()))
        for r in self.con.execute("SELECT place_id FROM leads WHERE place_id=? OR telefone_e164=?",
                                  (chave, chave)).fetchall():
            lead = self.obter(r[0])
            lead.status, lead.proximo_followup = "nao_contatar", None
            self._gravar(lead)
        self.con.commit()

    def bloqueado(self, lead: Lead) -> bool:
        chaves = [lead.place_id, lead.telefone_e164, *lead.emails]
        chaves = [c for c in chaves if c]
        q = f"SELECT 1 FROM bloqueio WHERE chave IN ({','.join('?' * len(chaves))})"
        return bool(chaves) and self.con.execute(q, chaves).fetchone() is not None

    # ---------- buscas e métricas ----------
    def registrar_busca(self, campanha: str, consulta: str, total: int, novos: int) -> None:
        self.con.execute("INSERT INTO buscas (data, campanha, consulta, total, novos) VALUES (?,?,?,?,?)",
                         (agora(), campanha, consulta, total, novos))
        self.con.commit()

    def funil(self, campanha: str = "") -> dict[str, int]:
        sql = "SELECT status, COUNT(*) FROM leads" + (" WHERE campanha=?" if campanha else "") + " GROUP BY status"
        contagem = dict(self.con.execute(sql, (campanha,) if campanha else ()).fetchall())
        return {s: contagem.get(s, 0) for s in STATUS}
