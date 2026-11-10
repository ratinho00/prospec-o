# 📍 Prospec — prospecção automatizada com Google Maps

Encontra empresas no **Google Maps**, descobre o que falta para elas (site, Instagram, pixel,
avaliações...), pontua quem tem mais chance de comprar, guarda tudo num **CRM** com funil e
follow-ups e escreve as **mensagens de abordagem** (WhatsApp, e-mail e ligação), inclusive
personalizadas com IA.

## O que ele faz

| Função | Como |
|---|---|
| **Busca no Google Maps** | Places API oficial. Combina várias consultas × várias cidades. O modo **grade** divide a cidade em N×N áreas para passar do limite de 60 resultados por busca. Duplicatas são removidas. |
| **Dados de cada empresa** | nome, categoria, endereço, telefone, **celular/WhatsApp detectado**, site, nota, nº de avaliações, horário, faixa de preço, link do Maps, coordenadas |
| **Enriquecimento do site** | visita o site e as páginas de contato/sobre: **e-mails**, telefones, **Instagram, Facebook, LinkedIn, TikTok, YouTube, WhatsApp**, título, HTTPS, tempo de carregamento e tecnologias (Pixel da Meta, Google Analytics/GTM, Google Ads, WordPress, Wix, Shopify, Nuvemshop, chat, agendamento online) |
| **Score 0–100 (quente/morno/frio)** | regras com pesos configuráveis: sem site, site fora do ar, sem HTTPS, site lento, sem pixel, sem Instagram, poucas avaliações, nota baixa, tem WhatsApp, tem e-mail... Cada lead mostra **por que** ganhou pontos. Empresas fechadas são descartadas. |
| **Filtros** | nota mín./máx., avaliações mín./máx., só sem site, só com WhatsApp, palavras excluídas (ex.: franquias), score mínimo |
| **CRM local (SQLite)** | funil `novo → qualificado → contatado → respondeu → reuniao → proposta → fechado/perdido`, notas, tags, histórico de interações. Novas buscas **não sobrescrevem** o que você editou. |
| **Mensagens** | modelos com variáveis (`{nome}`, `{cidade}`, `{gancho}`...) e **gancho automático** a partir da oportunidade detectada; ou personalização com **Claude** (WhatsApp + e-mail + roteiro de ligação). Gera o **link wa.me** com o texto pronto. |
| **Cadência de follow-up** | ao registrar um contato, agenda o próximo (padrão: 3 e 7 dias) e usa a mensagem da etapa seguinte. Comando/aba de follow-ups vencidos. |
| **E-mail** | envio via SMTP com limite por execução, prévia obrigatória e linha de descadastro |
| **Não contatar** | lista de bloqueio por place_id, telefone ou e-mail, respeitada nas buscas futuras |
| **Exportação e integrações** | Excel (com filtro e colunas ajustadas), CSV e **webhook** (n8n, Make, Zapier, seu CRM) |
| **Campanhas automáticas** | todo o pipeline num YAML, pronto para rodar no **cron** todo dia e pegar só as empresas novas |
| **Painel web** | Streamlit: busca com mapa, tabela editável do CRM, gerador de mensagens com botão "abrir no WhatsApp", follow-ups, funil e campanhas |

## Instalação

```bash
pip install -r requirements.txt
export GOOGLE_MAPS_API_KEY=...        # obrigatório para buscas reais
export ANTHROPIC_API_KEY=sk-ant-...   # opcional: só para mensagens com IA
```

### Chave do Google Maps

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/), crie um projeto e ative o faturamento.
2. Em **APIs e serviços → Biblioteca**, ative **Places API (New)** e **Geocoding API** (o Geocoding só é usado no modo grade).
3. Em **Credenciais**, crie uma chave de API e restrinja-a a essas duas APIs.

Custo: o Google dá uma cota mensal gratuita, e cada página de 20 resultados conta como uma chamada de
Text Search. O sistema mostra a estimativa de chamadas antes de buscar. Confira os preços atuais em
<https://developers.google.com/maps/billing-and-pricing/pricing>. Para testar sem gastar nada, use `--mock`
ou o "Modo teste" do painel.

## Uso rápido

### Painel web

```bash
streamlit run app.py
```

### Linha de comando

```bash
# 1. buscar (com cobertura 3×3 em cada cidade) e já enriquecer os sites
python -m prospec buscar "dentista" "clínica odontológica" -l "Campinas, SP" -l "Valinhos, SP" --grade 3 --enriquecer --campanha dentistas

# 2. ver os melhores
python -m prospec leads --score-min 50 --limite 30

# 3. gerar mensagens para os 20 melhores (adicione --ia para personalizar com Claude)
python -m prospec mensagens --top 20 --perfil examples/campanha_exemplo.yaml

# 4. depois de mandar a mensagem, registrar (agenda o follow-up)
python -m prospec contatei <place_id> --canal whatsapp

# 5. todo dia: o que precisa de follow-up
python -m prospec followups

# 6. avançar no funil
python -m prospec status <place_id> reuniao --nota "call quinta 10h" --followup 2026-11-20

# 7. exportar
python -m prospec exportar saidas/leads.xlsx --score-min 40
```

Outros comandos: `enriquecer`, `pontuar`, `ver <place_id>`, `email` (prévia; envia com `--confirmar`),
`bloquear <telefone|email|place_id>`, `funil`, `painel`. Use `python -m prospec <comando> --help`.

### Campanha automática (cron)

Edite `examples/campanha_exemplo.yaml` (consultas, cidades, filtros, pesos, seu perfil, webhook) e rode:

```bash
python -m prospec campanha examples/campanha_exemplo.yaml --mock   # ensaio sem API
python -m prospec campanha examples/campanha_exemplo.yaml
```

Cada execução cria `saidas/<campanha>-<data>/` com `leads.xlsx` e `mensagens.md` (com os links de
WhatsApp prontos) e só traz empresas que ainda não estavam no CRM. Para rodar todo dia útil às 8h:

```bash
crontab -e
# 0 8 * * 1-5 cd /caminho/prospec-o && GOOGLE_MAPS_API_KEY=... python -m prospec campanha minha_campanha.yaml >> prospec.log 2>&1
```

## Variáveis de ambiente

| Variável | Uso |
|---|---|
| `GOOGLE_MAPS_API_KEY` | buscas no Google Maps |
| `ANTHROPIC_API_KEY` | mensagens personalizadas com IA |
| `PROSPEC_MODEL` | modelo do Claude (padrão `claude-opus-5-5`) |
| `PROSPEC_DB` | arquivo do CRM (padrão `prospec.db`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | envio de e-mail |

## Estrutura

```
prospec/
  maps.py        # Google Places API (New): busca, paginação, grade, geocoding + mock offline
  enriquecer.py  # leitura dos sites: contatos, redes, WhatsApp, tecnologias
  pontuacao.py   # score configurável e filtros
  db.py          # CRM SQLite: leads, funil, interações, cadência, bloqueio
  mensagens.py   # modelos, gancho automático, Claude, wa.me, SMTP
  campanha.py    # pipeline completo a partir de YAML
  exportar.py    # Excel, CSV e webhook
  cli.py         # linha de comando
app.py           # painel Streamlit
```

## Boas práticas e limites

- **WhatsApp:** o sistema gera o link `wa.me` com o texto pronto, mas **você envia**. Disparo automático
  em massa por WhatsApp pessoal viola os termos do WhatsApp e derruba o número. Para volume, use a
  API oficial do WhatsApp Business.
- **LGPD:** prospecção B2B com dados públicos é possível com base em legítimo interesse, mas ofereça
  sempre saída ("responda remover") e use `bloquear` quando pedirem. Os modelos de e-mail já trazem a linha.
- **E-mail:** mantenha volumes baixos por dia (o padrão é 20) e use um domínio aquecido, com SPF/DKIM.
- **Google Maps:** a busca usa apenas a API oficial. Raspar o site do Maps viola os termos do Google.
- O score é uma heurística: ajuste os `pesos` na campanha para o que você vende.
