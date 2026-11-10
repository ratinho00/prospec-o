"""Linha de comando: python -m prospec <comando> --help"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

from .campanha import Campanha, executar, gerar_mensagens
from .db import CAMINHO_PADRAO, Banco
from .enriquecer import enriquecer_varios
from .exportar import enviar_webhook, exportar
from .maps import GoogleMaps, MapsMock, buscar, estimar_chamadas
from .mensagens import EnviadorEmail, mensagem_modelo
from .models import STATUS
from .pontuacao import pontuar
from .telefone import formatar


def _perfil(caminho: str | None) -> dict:
    if caminho and Path(caminho).exists():
        dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
        return dados.get("perfil", dados)
    return {}


def cmd_buscar(a, db: Banco):
    est = estimar_chamadas(len(a.consulta), len(a.local), a.grade, a.max)
    print(f"Estimativa: até {est} chamadas à Places API")
    cliente = MapsMock() if a.mock else GoogleMaps()
    leads = buscar(cliente, a.consulta, a.local, a.grade, a.max, a.nota_min)
    if not a.incluir_com_site:
        leads = [l for l in leads if not l.site]
    if a.enriquecer:
        leads = enriquecer_varios(leads, mock=a.mock)
    leads = [pontuar(l) for l in leads]
    novos, atual = db.salvar(leads, campanha=a.campanha)
    print(f"✅ {len(leads)} encontrados · {novos} novos · {atual} atualizados · "
          f"{cliente.chamadas} chamadas à API")


def cmd_enriquecer(a, db: Banco):
    leads = db.listar(campanha=a.campanha)
    if not a.todos:
        leads = [l for l in leads if not l.enriquecido_em]
    leads = [pontuar(l) for l in enriquecer_varios(leads, paralelismo=a.paralelismo, mock=a.mock)]
    db.salvar(leads)
    print(f"✅ {len(leads)} leads enriquecidos e repontuados")


def cmd_pontuar(a, db: Banco):
    pesos = Campanha.carregar(a.campanha_yaml).pesos if a.campanha_yaml else None
    leads = [pontuar(l, pesos) for l in db.listar()]
    db.salvar(leads)
    print(f"✅ {len(leads)} leads repontuados")


def cmd_leads(a, db: Banco):
    leads = db.listar(status=a.status, score_min=a.score_min, campanha=a.campanha,
                      cidade=a.cidade, texto=a.busca, temperatura=a.temperatura, limite=a.limite)
    for l in leads:
        contato = "📱" if l.whatsapp else ("☎️ " if l.telefone else "  ")
        mail = "✉️ " if l.emails else "  "
        print(f"{l.score:>3} {l.temperatura[:6]:<6} {l.status:<12} {contato}{mail} {l.nome[:40]:<40} "
              f"{formatar(l.telefone_e164):<16} {l.cidade:<18} {l.place_id}")
    print(f"\n{len(leads)} leads")


def cmd_ver(a, db: Banco):
    l = db.obter(a.place_id)
    if not l:
        sys.exit("Lead não encontrado")
    print(yaml.safe_dump(l.model_dump(), allow_unicode=True, sort_keys=False))
    for h in db.historico(a.place_id):
        print(f"{h['data']} [{h['canal']}/{h['tipo']}] {h['texto'][:100]}")


def cmd_status(a, db: Banco):
    l = db.mudar_status(a.place_id, a.status, a.nota or "")
    if a.followup:
        l.proximo_followup = a.followup
        db.atualizar(l)
    print(f"✅ {l.nome}: {l.status}")


def cmd_mensagens(a, db: Banco):
    leads = db.listar(status=a.status or ["novo", "qualificado"], score_min=a.score_min,
                      campanha=a.campanha, limite=a.top)
    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    gerar_mensagens(leads, _perfil(a.perfil), saida, usar_ia=a.ia)


def cmd_contatei(a, db: Banco):
    cadencia = [int(x) for x in a.cadencia.split(",")]
    l = db.marcar_contato(a.place_id, a.canal, a.texto or "", cadencia)
    print(f"✅ {l.nome}: contato registrado. Próximo follow-up: {l.proximo_followup or '—'}")


def cmd_followups(a, db: Banco):
    perfil = _perfil(a.perfil)
    leads = db.followups_vencidos()
    if not leads:
        print("Nenhum follow-up vencido hoje 🎉")
    for l in leads:
        m = mensagem_modelo(l, perfil, l.etapa_cadencia)
        print(f"⏰ {l.proximo_followup} · {l.nome} ({l.status}, etapa {l.etapa_cadencia})")
        if m["link_whatsapp"]:
            print(f"   {m['link_whatsapp']}")
        print(f"   depois: python -m prospec contatei {l.place_id}")


def cmd_email(a, db: Banco):
    perfil = _perfil(a.perfil)
    leads = [l for l in db.listar(status=["novo", "qualificado"], score_min=a.score_min,
                                  campanha=a.campanha) if l.emails][:a.limite]
    print(f"{len(leads)} leads com e-mail selecionados")
    if not a.confirmar:
        for l in leads:
            print(f" - {l.nome} <{l.emails[0]}>")
        print("Prévia apenas. Rode novamente com --confirmar para enviar.")
        return
    env = EnviadorEmail(limite=a.limite)
    cadencia = [int(x) for x in a.cadencia.split(",")]
    for l in leads:
        m = mensagem_modelo(l, perfil, l.etapa_cadencia)
        if env.enviar(l.emails[0], m["email_assunto"], m["email_corpo"]):
            db.marcar_contato(l.place_id, "email", m["email_corpo"], cadencia)
            print(f"✉️  {l.nome} <{l.emails[0]}>")
    print(f"✅ {env.enviados} e-mails enviados")


def cmd_exportar(a, db: Banco):
    leads = db.listar(status=a.status, score_min=a.score_min, campanha=a.campanha)
    if a.webhook:
        print(f"🔗 {enviar_webhook(a.webhook, leads)} leads enviados ao webhook")
    print(f"✅ {len(leads)} leads em {exportar(leads, a.arquivo)}")


def cmd_campanha(a, db: Banco):
    r = executar(Campanha.carregar(a.arquivo), db, mock=a.mock, sem_ia=a.sem_ia)
    print(f"\n✅ Concluído: {r['novos']} novos de {r['encontrados']} · arquivos em {r['pasta']}")


def cmd_bloquear(a, db: Banco):
    db.bloquear(a.chave, a.motivo)
    print(f"🚫 {a.chave} bloqueado")


def cmd_funil(a, db: Banco):
    f = db.funil(a.campanha)
    total = sum(f.values()) or 1
    for s, n in f.items():
        print(f"{s:<13} {n:>5}  {'█' * round(40 * n / total)}")
    print(f"Follow-ups vencidos hoje ({date.today()}): {len(db.followups_vencidos())}")


def cmd_painel(a, db: Banco):
    app = Path(__file__).resolve().parent.parent / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app)], check=False)


def main(argv=None):
    p = argparse.ArgumentParser(prog="prospec", description="Prospecção de empresas no Google Maps")
    p.add_argument("--db", default=CAMINHO_PADRAO, help="arquivo SQLite do CRM")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("buscar", help="busca empresas no Google Maps")
    s.add_argument("consulta", nargs="+", help='ex.: "dentista" "clínica de estética"')
    s.add_argument("-l", "--local", action="append", default=[], help='ex.: "Campinas, SP" (repita)')
    s.add_argument("--grade", type=int, default=1, help="divide cada local em N×N células (mais cobertura)")
    s.add_argument("--max", type=int, default=60, help="máximo por busca/célula (até 60)")
    s.add_argument("--nota-min", type=float)
    s.add_argument("--campanha", default="")
    s.add_argument("--enriquecer", action="store_true", help="já visita os sites")
    s.add_argument("--incluir-com-site", action="store_true", help="por padrão só entram empresas sem site")
    s.add_argument("--mock", action="store_true")
    s.set_defaults(f=cmd_buscar)

    s = sub.add_parser("enriquecer", help="visita sites e extrai e-mails, redes, WhatsApp, tecnologias")
    s.add_argument("--todos", action="store_true", help="refaz também os já enriquecidos")
    s.add_argument("--campanha", default="")
    s.add_argument("--paralelismo", type=int, default=8)
    s.add_argument("--mock", action="store_true")
    s.set_defaults(f=cmd_enriquecer)

    s = sub.add_parser("pontuar", help="recalcula score de todos os leads")
    s.add_argument("--campanha-yaml", help="usa os pesos deste YAML")
    s.set_defaults(f=cmd_pontuar)

    s = sub.add_parser("leads", help="lista leads do CRM")
    s.add_argument("--status", action="append", choices=STATUS)
    s.add_argument("--score-min", type=int, default=0)
    s.add_argument("--temperatura", choices=["quente", "morno", "frio", "descartado"], default="")
    s.add_argument("--campanha", default="")
    s.add_argument("--cidade", default="")
    s.add_argument("--busca", default="", help="texto no nome/categoria")
    s.add_argument("--limite", type=int, default=50)
    s.set_defaults(f=cmd_leads)

    s = sub.add_parser("ver", help="detalhes e histórico de um lead")
    s.add_argument("place_id")
    s.set_defaults(f=cmd_ver)

    s = sub.add_parser("status", help="muda a etapa do funil")
    s.add_argument("place_id")
    s.add_argument("status", choices=STATUS)
    s.add_argument("--nota")
    s.add_argument("--followup", help="AAAA-MM-DD")
    s.set_defaults(f=cmd_status)

    s = sub.add_parser("mensagens", help="gera mensagens (WhatsApp/e-mail) para os melhores leads")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--score-min", type=int, default=0)
    s.add_argument("--status", action="append", choices=STATUS)
    s.add_argument("--campanha", default="")
    s.add_argument("--perfil", default="examples/campanha_exemplo.yaml", help="YAML com seu perfil")
    s.add_argument("--ia", action="store_true", help="personaliza cada mensagem com Claude")
    s.add_argument("--saida", default="saidas/mensagens.md")
    s.set_defaults(f=cmd_mensagens)

    s = sub.add_parser("contatei", help="registra que você contatou o lead e agenda o follow-up")
    s.add_argument("place_id")
    s.add_argument("--canal", default="whatsapp", choices=["whatsapp", "email", "ligacao", "visita", "instagram"])
    s.add_argument("--texto")
    s.add_argument("--cadencia", default="3,7", help="dias até cada follow-up")
    s.set_defaults(f=cmd_contatei)

    s = sub.add_parser("followups", help="lista follow-ups vencidos com link pronto")
    s.add_argument("--perfil", default="examples/campanha_exemplo.yaml")
    s.set_defaults(f=cmd_followups)

    s = sub.add_parser("email", help="envia e-mails de primeiro contato via SMTP (com limite)")
    s.add_argument("--limite", type=int, default=20)
    s.add_argument("--score-min", type=int, default=40)
    s.add_argument("--campanha", default="")
    s.add_argument("--perfil", default="examples/campanha_exemplo.yaml")
    s.add_argument("--cadencia", default="3,7")
    s.add_argument("--confirmar", action="store_true")
    s.set_defaults(f=cmd_email)

    s = sub.add_parser("exportar", help="exporta para .xlsx ou .csv (e opcionalmente webhook)")
    s.add_argument("arquivo")
    s.add_argument("--status", action="append", choices=STATUS)
    s.add_argument("--score-min", type=int, default=0)
    s.add_argument("--campanha", default="")
    s.add_argument("--webhook", default="")
    s.set_defaults(f=cmd_exportar)

    s = sub.add_parser("campanha", help="roda o pipeline completo de um YAML (ideal para cron)")
    s.add_argument("arquivo")
    s.add_argument("--mock", action="store_true")
    s.add_argument("--sem-ia", action="store_true")
    s.set_defaults(f=cmd_campanha)

    s = sub.add_parser("bloquear", help="lista de não contatar (place_id, telefone ou e-mail)")
    s.add_argument("chave")
    s.add_argument("--motivo", default="pediu para não ser contatado")
    s.set_defaults(f=cmd_bloquear)

    s = sub.add_parser("funil", help="resumo do funil de vendas")
    s.add_argument("--campanha", default="")
    s.set_defaults(f=cmd_funil)

    s = sub.add_parser("painel", help="abre a interface web (Streamlit)")
    s.set_defaults(f=cmd_painel)

    a = p.parse_args(argv)
    a.f(a, Banco(a.db))


if __name__ == "__main__":
    main()
