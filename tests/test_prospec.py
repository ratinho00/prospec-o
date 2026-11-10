from datetime import date, timedelta

from prospec.campanha import Campanha, executar
from prospec.db import Banco
from prospec.enriquecer import analisar_html
from prospec.maps import MapsMock, Retangulo, buscar, place_para_lead
from prospec.mensagens import link_whatsapp, mensagem_modelo
from prospec.models import Lead
from prospec.pontuacao import passa_filtros, pontuar
from prospec.telefone import eh_celular, para_e164


def lead(**kw):
    base = dict(place_id="p1", nome="Clínica Teste", categoria="Dentista", cidade="Campinas/SP")
    return Lead(**(base | kw))


def test_telefone():
    assert para_e164("(19) 99876-5432") == "5519998765432"
    assert para_e164("+55 19 3232-1234") == "551932321234"
    assert eh_celular("5519998765432") and not eh_celular("551932321234")
    assert para_e164("123") == ""


def test_place_para_lead():
    p = {"id": "x", "displayName": {"text": "Loja"}, "internationalPhoneNumber": "+55 11 91234-5678",
         "addressComponents": [{"longText": "São Paulo", "types": ["administrative_area_level_2"]},
                               {"shortText": "SP", "types": ["administrative_area_level_1"]}],
         "rating": 4.5, "userRatingCount": 10}
    l = place_para_lead(p)
    assert l.celular and l.whatsapp == "5511912345678" and l.cidade == "São Paulo/SP"


def test_grade():
    cel = Retangulo(0, 0, 1, 1).dividir(3)
    assert len(cel) == 9 and cel[-1].norte == 1


def test_busca_deduplica():
    c = MapsMock()
    a = buscar(c, ["dentista"], ["Campinas"], grade=1, log=lambda *_: None)
    b = buscar(c, ["dentista", "dentista"], ["Campinas"], grade=1, log=lambda *_: None)
    assert len(a) == len(b) > 0


def test_analisar_html():
    l = lead(site="https://x.com")
    html = """<title>Clínica X</title><meta name="viewport"> contato@clinicax.com.br logo@2x.png
    <a href="https://www.instagram.com/clinicax/">ig</a> <a href="https://wa.me/5519998765432">wa</a>
    <script>fbq('init')</script> Tel: (19) 3232-1234"""
    analisar_html(html, l)
    assert l.emails == ["contato@clinicax.com.br"]
    assert l.redes["instagram"].endswith("clinicax")
    assert l.redes["whatsapp"] == "5519998765432"
    assert "Meta Pixel" in l.tecnologias and "Responsivo" in l.tecnologias
    assert "551932321234" in l.telefones_site and l.site_titulo == "Clínica X"


def test_pontuacao():
    sem_site = pontuar(lead(telefone_e164="5519998765432", celular=True, avaliacoes=5, nota=4.0))
    estruturado = pontuar(lead(site="https://a.com", enriquecido_em="x", site_ok=True, site_https=True,
                               tecnologias=["Meta Pixel", "Google Analytics"], redes={"instagram": "i"},
                               avaliacoes=80, nota=4.8))
    assert sem_site.score > estruturado.score
    assert sem_site.temperatura == "quente"
    fechado = pontuar(lead(status_negocio="CLOSED_PERMANENTLY"))
    assert fechado.score == 0 and fechado.temperatura == "descartado"
    assert not passa_filtros(lead(nome="Rede OdontoCompany"), {"excluir_palavras": ["odontocompany"]})


def test_mensagem_e_link():
    l = pontuar(lead(telefone_e164="5519998765432", celular=True))
    m = mensagem_modelo(l, {"meu_nome": "Ana", "minha_empresa": "ACME"})
    assert "Clínica Teste" in m["whatsapp"] and "Ana" in m["whatsapp"]
    assert m["link_whatsapp"].startswith("https://wa.me/5519998765432?text=")
    assert link_whatsapp("", "oi") == ""


def test_crm(tmp_path):
    db = Banco(tmp_path / "t.db")
    l = lead(telefone_e164="5519998765432", celular=True)
    assert db.salvar([l]) == (1, 0)
    db.mudar_status("p1", "qualificado", "bom lead")
    # nova busca não apaga o que foi editado
    assert db.salvar([lead(telefone_e164="5519998765432", celular=True)]) == (0, 1)
    assert db.obter("p1").status == "qualificado"
    l = db.marcar_contato("p1", "whatsapp", "oi", [3, 7])
    assert l.status == "contatado" and l.proximo_followup == (date.today() + timedelta(days=3)).isoformat()
    assert db.followups_vencidos(date.today() + timedelta(days=3))[0].place_id == "p1"
    db.bloquear("5519998765432")
    assert db.obter("p1").status == "nao_contatar"
    db.salvar([lead(place_id="p2", telefone_e164="5519998765432")])
    assert db.obter("p2").status == "nao_contatar"
    assert db.funil()["nao_contatar"] == 2


def test_campanha_mock(tmp_path):
    c = Campanha(nome="t", consultas=["dentista"], locais=["Campinas, SP"], grade=2,
                 pasta_saida=str(tmp_path), perfil={"meu_nome": "Ana"})
    db = Banco(tmp_path / "c.db")
    r = executar(c, db, mock=True, log=lambda *_: None)
    assert r["novos"] > 0
    assert executar(c, db, mock=True, log=lambda *_: None)["novos"] == 0  # rodar de novo não duplica
    assert (tmp_path / r["planilha"].split(str(tmp_path) + "/")[1]).exists()
