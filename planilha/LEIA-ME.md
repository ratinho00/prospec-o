# Prospecção no Google Planilhas (sem instalar nada)

Você **não precisa** de chave do Google nem de cartão. Escolha uma das três formas de trazer empresas:

| Forma | Precisa de quê | Qualidade dos dados |
|---|---|---|
| **Busca grátis (OpenStreetMap)** | nada | cobre menos empresas que o Google e não tem nota/avaliações |
| **Importar lista pronta** (Apify, Outscraper) | conta grátis no site da ferramenta | dados do Google Maps completos (nota, avaliações, telefone, site) |
| Google Maps direto | chave do Google Cloud + cartão | a mais completa e automática |

> **Só empresas SEM site:** esse é o padrão. Empresas com site são ignoradas na busca e na importação.
> Para mudar, troque para "não" a linha *Só empresas SEM site?* na aba **Config**.
> Se já houver empresas com site na lista, use 📍 Prospecção → *Remover da lista empresas que têm site*.

## 1. Montar a planilha (5 min)
1. Abra https://sheets.new (uma planilha nova).
2. Menu **Extensões → Apps Script**.
3. Apague o conteúdo que aparecer, cole todo o arquivo `Prospeccao.gs` e clique no 💾 (Salvar).
4. Volte para a planilha e **recarregue a página (F5)**. Aparece o menu **📍 Prospecção**.
5. Clique em **📍 Prospecção → 1. Configurar**. Na primeira vez o Google pede autorização:
   *Continuar → escolha sua conta → Avançado → Acessar (não seguro) → Permitir*.
   (O aviso aparece porque o script é seu e não foi publicado.)
6. Na aba **Config**, preencha seu nome, empresa e o benefício que você oferece.

## 2. Trazer empresas

### Opção A — Busca grátis (nenhum cadastro)
📍 Prospecção → **Buscar empresas GRÁTIS** → digite o que buscar (`dentista, salão de beleza`) e a
cidade (`Campinas, SP`). Pronto.

### Opção B — Importar lista do Google Maps pelo Apify (mais empresas, com nota e avaliações)
1. Crie uma conta grátis em https://apify.com (dá para entrar com a conta do Google; o plano grátis
   tem um crédito mensal que dá para algumas centenas de empresas).
2. Abra a ferramenta **Google Maps Scraper** (https://apify.com/compass/crawler-google-places) e clique em **Try for free**.
3. Em *Search term(s)* escreva `dentista`; em *Location* escreva `Campinas, SP`; em *Number of places* coloque 100. Clique em **Start**.
4. Quando terminar, clique em **Export → CSV** (ou Excel) e baixe.
5. Abra o arquivo, selecione tudo (Ctrl+A), copie (Ctrl+C), vá na planilha, menu
   📍 Prospecção → **Importar lista pronta** (cria a aba *Importar*), clique em A1 e cole (Ctrl+V).
6. Rode de novo 📍 Prospecção → **Importar lista pronta**. As empresas vão para a aba **Leads** com score e mensagem.

Funciona igual com o Outscraper (https://outscraper.com) ou com qualquer planilha que tenha cabeçalho
(nome, telefone, site...).

## 3. Usar no dia a dia
- **Analisar sites (opcional):** 📍 Prospecção → *Analisar sites* — encontra e-mail, Instagram, WhatsApp
  e se o site tem pixel/Analytics. Se tiver muitos sites, rode mais de uma vez.
- **Abordar:** na aba **Leads**, os melhores ficam no topo. Clique em **💬** na coluna *WhatsApp*:
  abre a conversa com a mensagem pronta. Revise e envie.
- **Marcar o envio:** marque **Enviei?**. A planilha muda o status para *contatado*, agenda o follow-up
  (3 e depois 7 dias — ajustável em Config) e já troca a mensagem pela próxima.
- **Follow-ups do dia:** aba **Follow-ups**.
- **Funil:** mude a coluna *Status* e acompanhe na aba **Funil**.
- A coluna **Google Maps** abre o perfil da empresa no Google (útil para ver a nota nos leads do OpenStreetMap).

No celular (app do Google Planilhas) dá para clicar no WhatsApp, marcar *Enviei?* e mudar o status.
O menu 📍 Prospecção só aparece no computador.

## Problemas comuns
| Mensagem | Solução |
|---|---|
| "OpenStreetMap está ocupado" | espere alguns minutos e tente de novo |
| Poucas empresas na busca grátis | normal em algumas cidades — use a Opção B |
| "Não achei a coluna com o nome" | a primeira linha da aba *Importar* precisa ser o cabeçalho |
| Menu não aparece | recarregue a planilha; confira se salvou o script |
