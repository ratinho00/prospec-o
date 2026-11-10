"""Painel web do Prospec: streamlit run app.py"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from prospec.campanha import Campanha, executar
from prospec.db import CAMINHO_PADRAO, Banco
from prospec.enriquecer import enriquecer_varios
from prospec.exportar import exportar, tabela
from prospec.maps import GoogleMaps, MapsMock, buscar, estimar_chamadas
from prospec.mensagens import Redator, mensagem_modelo
from prospec.models import STATUS
from prospec.pontuacao import pontuar

st.set_page_config(page_title="Prospec", page_icon="📍", layout="wide")


@st.cache_resource
def banco(caminho: str) -> Banco:
    return Banco(caminho)


EXEMPLO = Path("examples/campanha_exemplo.yaml")
perfil_padrao = (yaml.safe_load(EXEMPLO.read_text(encoding="utf-8")) or {}).get("perfil", {}) if EXEMPLO.exists() else {}

with st.sidebar:
    st.title("📍 Prospec")
    db = banco(st.text_input("Banco (SQLite)", CAMINHO_PADRAO))
    mock = st.toggle("Modo teste (sem API)", value=False,
                     help="Gera empresas fictícias — útil para conhecer o sistema sem gastar cota.")
    st.subheader("Seu perfil")
    perfil = {
        "meu_nome": st.text_input("Seu nome", perfil_padrao.get("meu_nome", "")),
        "minha_empresa": st.text_input("Empresa", perfil_padrao.get("minha_empresa", "")),
        "beneficio": st.text_input("Benefício principal", perfil_padrao.get("beneficio", "")),
        "oferta": st.text_area("Oferta (para a IA)", perfil_padrao.get("oferta", ""), height=90),
    }
    f = db.funil()
    st.metric("Leads no CRM", sum(f.values()))
    st.metric("Follow-ups vencidos", len(db.followups_vencidos()))

aba_busca, aba_leads, aba_msg, aba_follow, aba_funil, aba_camp = st.tabs(
    ["🔎 Buscar", "📋 Leads", "✉️ Mensagens", "⏰ Follow-ups", "📈 Funil", "🤖 Campanhas"])

# ---------------- Buscar ----------------
with aba_busca:
    c1, c2 = st.columns(2)
    consultas = c1.text_area("O que buscar (um por linha)", "dentista\nclínica de estética").splitlines()
    locais = c2.text_area("Onde (um por linha)", "Campinas, SP").splitlines()
    consultas = [c.strip() for c in consultas if c.strip()]
    locais = [l.strip() for l in locais if l.strip()]
    c3, c4, c5, c6 = st.columns(4)
    grade = c3.selectbox("Cobertura (grade)", [1, 2, 3, 4], help="Divide a cidade em N×N áreas")
    maximo = c4.selectbox("Máx. por busca", [20, 40, 60], index=2)
    nota_min = c5.number_input("Nota mínima", 0.0, 5.0, 0.0, 0.5)
    enriquecer = c6.checkbox("Enriquecer sites", value=True)
    campanha = st.text_input("Campanha (etiqueta)", "")
    so_sem_site = st.checkbox("Só empresas SEM site", value=True)
    st.caption(f"Estimativa: até {estimar_chamadas(len(consultas), len(locais), grade, maximo)} chamadas à Places API")
    if st.button("Buscar no Google Maps", type="primary", disabled=not consultas):
        status = st.status("Buscando...", expanded=True)
        try:
            cliente = MapsMock() if mock else GoogleMaps()
            leads = buscar(cliente, consultas, locais, grade, maximo, nota_min or None, log=status.write)
            if so_sem_site:
                leads = [l for l in leads if not l.site]
            if enriquecer:
                leads = enriquecer_varios(leads, mock=mock, log=status.write)
            leads = [pontuar(l) for l in leads]
            novos, atual = db.salvar(leads, campanha=campanha)
            status.update(label=f"{len(leads)} encontrados · {novos} novos · {atual} atualizados", state="complete")
            st.dataframe(tabela(sorted(leads, key=lambda l: -l.score))[
                ["score", "temperatura", "nome", "categoria", "whatsapp", "email", "site", "nota",
                 "avaliacoes", "oportunidades"]], hide_index=True)
            pontos = pd.DataFrame([{"lat": l.lat, "lon": l.lng} for l in leads if l.lat])
            if not pontos.empty:
                st.map(pontos)
        except Exception as e:  # noqa: BLE001
            status.update(label="Erro", state="error")
            st.error(str(e))

# ---------------- Leads (CRM) ----------------
with aba_leads:
    c1, c2, c3, c4, c5 = st.columns(5)
    f_status = c1.multiselect("Status", STATUS)
    f_temp = c2.selectbox("Temperatura", ["", "quente", "morno", "frio", "descartado"])
    f_score = c3.slider("Score mínimo", 0, 100, 0)
    f_camp = c4.selectbox("Campanha", [""] + db.campanhas())
    f_texto = c5.text_input("Buscar nome/categoria")
    leads = db.listar(status=f_status or None, score_min=f_score, campanha=f_camp,
                      temperatura=f_temp, texto=f_texto)
    df = tabela(leads)
    if df.empty:
        st.info("Nenhum lead ainda. Faça uma busca na primeira aba.")
    else:
        cols = ["place_id", "score", "temperatura", "status", "nome", "categoria", "cidade", "whatsapp",
                "email", "instagram", "site", "nota", "avaliacoes", "oportunidades", "proximo_followup",
                "notas", "maps"]
        editado = st.data_editor(
            df[cols], hide_index=True, use_container_width=True, disabled=[c for c in cols if c not in ("status", "notas")],
            column_config={"status": st.column_config.SelectboxColumn(options=STATUS),
                           "maps": st.column_config.LinkColumn(display_text="abrir"),
                           "site": st.column_config.LinkColumn(),
                           "instagram": st.column_config.LinkColumn(),
                           "score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")},
            key="editor_leads")
        if st.button("Salvar alterações"):
            mudou = 0
            for (_, novo), (_, velho) in zip(editado.iterrows(), df[cols].iterrows()):
                if novo["status"] != velho["status"]:
                    db.mudar_status(novo["place_id"], novo["status"])
                    mudou += 1
                if novo["notas"] != velho["notas"]:
                    l = db.obter(novo["place_id"])
                    l.notas = novo["notas"]
                    db.atualizar(l)
                    mudou += 1
            st.success(f"{mudou} alteração(ões) salvas")
        c1, c2 = st.columns(2)
        arq = exportar(leads, Path("saidas") / f"leads-{date.today()}.xlsx")
        c1.download_button("⬇️ Baixar Excel", arq.read_bytes(), arq.name)
        c2.download_button("⬇️ Baixar CSV", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           f"leads-{date.today()}.csv")

# ---------------- Mensagens ----------------
with aba_msg:
    c1, c2, c3 = st.columns(3)
    top = c1.number_input("Quantos leads", 1, 200, 10)
    score_min = c2.slider("Score mínimo ", 0, 100, 30)
    usar_ia = c3.checkbox("Personalizar com IA (Claude)", disabled=mock)
    alvo = db.listar(status=["novo", "qualificado"], score_min=score_min, limite=int(top))
    st.caption(f"{len(alvo)} leads novos/qualificados selecionados")
    if st.button("Gerar mensagens", type="primary", disabled=not alvo):
        redator = Redator() if usar_ia else None
        st.session_state["msgs"] = []
        barra = st.progress(0.0)
        for i, l in enumerate(alvo):
            try:
                m = redator.escrever(l, perfil, l.etapa_cadencia) if redator else mensagem_modelo(l, perfil, l.etapa_cadencia)
            except Exception as e:  # noqa: BLE001
                st.warning(f"IA falhou para {l.nome}: {e}")
                m = mensagem_modelo(l, perfil, l.etapa_cadencia)
            st.session_state["msgs"].append((l.place_id, m))
            barra.progress((i + 1) / len(alvo))
    for pid, m in st.session_state.get("msgs", []):
        l = db.obter(pid)
        with st.expander(f"{l.score} · {l.nome} · {l.status}"):
            st.caption("; ".join(l.motivos))
            texto = st.text_area("WhatsApp", m["whatsapp"], key=f"wa_{pid}")
            c1, c2, c3 = st.columns(3)
            if l.whatsapp:
                from prospec.mensagens import link_whatsapp
                c1.link_button("Abrir no WhatsApp", link_whatsapp(l.whatsapp, texto))
            if c2.button("Marquei como enviado", key=f"ok_{pid}"):
                db.marcar_contato(pid, "whatsapp", texto, [3, 7])
                st.toast(f"{l.nome}: contato registrado")
            if c3.button("Não contatar", key=f"bl_{pid}"):
                db.bloquear(pid)
                st.toast(f"{l.nome} bloqueado")
            if l.emails:
                st.text_input("Assunto", m["email_assunto"], key=f"as_{pid}")
                st.text_area(f"E-mail para {', '.join(l.emails)}", m["email_corpo"], key=f"em_{pid}", height=200)
            if m.get("roteiro_ligacao"):
                st.markdown(f"**Roteiro de ligação** ({l.telefone})\n\n{m['roteiro_ligacao']}")

# ---------------- Follow-ups ----------------
with aba_follow:
    vencidos = db.followups_vencidos()
    if not vencidos:
        st.success("Nenhum follow-up vencido hoje 🎉")
    for l in vencidos:
        m = mensagem_modelo(l, perfil, l.etapa_cadencia)
        with st.container(border=True):
            st.markdown(f"**{l.nome}** · {l.status} · etapa {l.etapa_cadencia} · venceu em {l.proximo_followup}")
            c1, c2, c3, c4 = st.columns(4)
            if m["link_whatsapp"]:
                c1.link_button("Enviar follow-up", m["link_whatsapp"])
            if c2.button("Enviado", key=f"fu_{l.place_id}"):
                db.marcar_contato(l.place_id, "whatsapp", m["whatsapp"], [3, 7])
                st.rerun()
            if c3.button("Respondeu", key=f"re_{l.place_id}"):
                db.mudar_status(l.place_id, "respondeu")
                st.rerun()
            if c4.button("Perdido", key=f"pe_{l.place_id}"):
                db.mudar_status(l.place_id, "perdido")
                st.rerun()

# ---------------- Funil ----------------
with aba_funil:
    camp = st.selectbox("Campanha ", [""] + db.campanhas())
    funil = db.funil(camp)
    dff = pd.DataFrame({"etapa": list(funil), "leads": list(funil.values())})
    st.bar_chart(dff, x="etapa", y="leads", horizontal=True)
    total = sum(funil.values()) or 1
    contatados = total - funil["novo"] - funil["qualificado"] - funil["nao_contatar"]
    responderam = sum(funil[s] for s in ("respondeu", "reuniao", "proposta", "fechado"))
    c1, c2, c3 = st.columns(3)
    c1.metric("Contatados", contatados)
    c2.metric("Taxa de resposta", f"{responderam / contatados:.0%}" if contatados else "—")
    c3.metric("Fechados", funil["fechado"])
    todos = db.listar(campanha=camp)
    if todos:
        dft = tabela(todos)
        st.subheader("Oportunidades mais comuns")
        st.bar_chart(dft["oportunidades"].str.split("; ").explode().replace("", pd.NA).dropna()
                     .str.replace(r" \(.*\)", "", regex=True).value_counts().head(10))

# ---------------- Campanhas ----------------
with aba_camp:
    st.write("Descreva uma campanha em YAML e rode o pipeline completo: busca → filtros → enriquecimento "
             "→ score → CRM → mensagens → planilha → webhook. No servidor, agende com o cron:")
    st.code("0 8 * * 1-5 cd /caminho/prospec-o && python -m prospec campanha minha_campanha.yaml", language="bash")
    texto = st.text_area("Campanha (YAML)", EXEMPLO.read_text(encoding="utf-8") if EXEMPLO.exists() else "", height=400)
    if st.button("Rodar campanha", type="primary"):
        status = st.status("Rodando...", expanded=True)
        try:
            r = executar(Campanha.model_validate(yaml.safe_load(texto)), db, mock=mock, log=status.write)
            status.update(label=f"{r['novos']} leads novos", state="complete")
            st.markdown(Path(r["mensagens"]).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            status.update(label="Erro", state="error")
            st.error(str(e))
