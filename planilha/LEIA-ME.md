# Prospecção no Google Planilhas (sem instalar nada)

## 1. Criar a chave do Google Maps (uma vez só, ~10 min)
1. Acesse https://console.cloud.google.com/ → crie um projeto.
2. Menu ☰ → **Faturamento** → vincule um cartão (necessário mesmo para a cota gratuita).
   Dica: em *Orçamentos e alertas*, crie um alerta de gasto.
3. Menu ☰ → **APIs e serviços → Biblioteca** → ative **Places API (New)** e **Geocoding API**.
4. **APIs e serviços → Credenciais → Criar credenciais → Chave de API** → copie a chave (`AIza...`).
   Em *Editar chave → Restrições de API*, deixe só as duas APIs acima.

## 2. Montar a planilha (5 min)
1. Abra https://sheets.new (uma planilha nova).
2. Menu **Extensões → Apps Script**.
3. Apague o conteúdo que aparecer, cole todo o arquivo `Prospeccao.gs` e clique no 💾 (Salvar).
4. Volte para a planilha e **recarregue a página (F5)**. Aparece o menu **📍 Prospecção**.
5. Clique em **📍 Prospecção → 1. Configurar**. Na primeira vez o Google pede autorização:
   *Continuar → escolha sua conta → Avançado → Acessar (não seguro) → Permitir*.
   (O aviso aparece porque o script é seu e não foi publicado; ele só acessa esta planilha e o Google Maps.)
6. Cole a chave do Google quando pedir.
7. Na aba **Config**, preencha seu nome, empresa e o benefício que você oferece.

## 3. Usar
- **Buscar:** 📍 Prospecção → *Buscar empresas* → digite o que buscar (`dentista, clínica odontológica`),
  onde (`Campinas, SP; Valinhos, SP`) e a cobertura (1 normal; 2 ou 3 para cidade grande).
- **Analisar sites (opcional):** 📍 Prospecção → *Analisar sites* — encontra e-mail, Instagram, WhatsApp
  e se o site tem pixel/Analytics, e recalcula o score. Se tiver muitos sites, rode mais de uma vez.
- **Abordar:** na aba **Leads**, os melhores ficam no topo (coluna *Score*). Clique em **💬** na coluna
  *WhatsApp*: abre a conversa com a mensagem pronta. Revise e envie.
- **Marcar o envio:** marque a caixa **Enviei?**. A planilha muda o status para *contatado*, agenda o
  follow-up (3 e depois 7 dias — ajustável em Config) e já troca a mensagem pela próxima da sequência.
- **Follow-ups do dia:** aba **Follow-ups** (atualiza sozinha).
- **Funil:** mude a coluna *Status* (respondeu, reuniao, proposta, fechado, perdido, nao_contatar) e
  acompanhe na aba **Funil**.

No celular (app do Google Planilhas) dá para clicar no WhatsApp, marcar *Enviei?* e mudar o status.
O menu 📍 Prospecção (busca) só aparece no computador.

## Problemas comuns
| Mensagem | Solução |
|---|---|
| `Google Maps respondeu 403` | ative a **Places API (New)** e o faturamento; confira as restrições da chave |
| `Não achei "..." (Geocoding...)` | ative a **Geocoding API** ou use cobertura 1 |
| Menu não aparece | recarregue a planilha; confira se salvou o script |
| Trocar a chave | 📍 Prospecção → *Trocar chave do Google* |
