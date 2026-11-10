/**
 * PROSPEC PARA GOOGLE PLANILHAS
 * Busca empresas no Google Maps, pontua os leads, gera mensagens com link do WhatsApp
 * e controla funil e follow-ups — tudo dentro da planilha.
 *
 * Instalação: Extensões → Apps Script → apague o que estiver lá → cole este arquivo →
 * salve (ícone de disquete) → volte à planilha e recarregue a página.
 * Aparece o menu "📍 Prospecção". Comece por "1. Configurar".
 */

// ======================= colunas da aba Leads =======================
const COLUNAS = [
  'Score', 'Temperatura', 'Status', 'Enviei?', 'Nome', 'Categoria', 'Cidade', 'Telefone',
  'WhatsApp', 'E-mail', 'Instagram', 'Site', 'Nota', 'Avaliações', 'Oportunidades', 'Mensagem',
  'Próximo follow-up', 'Etapa', 'Notas', 'Google Maps', 'Adicionado em',
  'Link WhatsApp', 'Celular', 'Enriquecido', 'Place ID', 'Busca',
];
const C = {};
COLUNAS.forEach((n, i) => (C[n] = i + 1));
const OCULTAS = ['Link WhatsApp', 'Celular', 'Enriquecido', 'Place ID', 'Busca'];
const STATUS = ['novo', 'qualificado', 'contatado', 'respondeu', 'reuniao', 'proposta', 'fechado', 'perdido', 'nao_contatar'];
const ABA_LEADS = 'Leads';
const ABA_CONFIG = 'Config';

const CAMPOS_MAPS = [
  'id', 'displayName', 'formattedAddress', 'addressComponents', 'nationalPhoneNumber',
  'internationalPhoneNumber', 'websiteUri', 'googleMapsUri', 'rating', 'userRatingCount',
  'businessStatus', 'primaryTypeDisplayName',
].map(c => 'places.' + c).join(',') + ',nextPageToken';

// ======================= menu =======================
function onOpen() {
  SpreadsheetApp.getUi().createMenu('📍 Prospecção')
    .addItem('1. Configurar', 'configurar')
    .addItem('2. Buscar empresas no Google Maps', 'buscarEmpresas')
    .addItem('3. Analisar sites (e-mail, Instagram, pixel...)', 'analisarSites')
    .addSeparator()
    .addItem('Ordenar por score', 'ordenarPorScore')
    .addItem('Refazer scores e mensagens', 'refazerTudo')
    .addItem('Trocar chave do Google', 'trocarChave')
    .addToUi();
}

// ======================= configuração =======================
function configurar() {
  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();

  let cfg = ss.getSheetByName(ABA_CONFIG);
  if (!cfg) {
    cfg = ss.insertSheet(ABA_CONFIG);
    cfg.getRange(1, 1, 9, 2).setValues([
      ['Configuração', 'Valor (edite a coluna B)'],
      ['Seu nome', 'Seu Nome'],
      ['Sua empresa', 'Sua Empresa'],
      ['Benefício (complete: ajudamos negócios como o de vocês a...)', 'atrair mais clientes pela internet'],
      ['Público no plural (ex.: clínicas odontológicas)', ''],
      ['Dias até cada follow-up (separe por vírgula)', '3, 7'],
      ['Ignorar empresas com estas palavras no nome', 'franquia, shopping'],
      ['Ignorar empresas com mais de X avaliações (0 = não ignorar)', 300],
      ['Ignorar empresas com nota abaixo de', 0],
    ]);
    cfg.getRange('A1:B1').setFontWeight('bold').setBackground('#1a73e8').setFontColor('white');
    cfg.setColumnWidth(1, 430);
    cfg.setColumnWidth(2, 380);
  }

  let leads = ss.getSheetByName(ABA_LEADS);
  if (!leads) {
    leads = ss.insertSheet(ABA_LEADS, 0);
    leads.getRange(1, 1, 1, COLUNAS.length).setValues([COLUNAS])
      .setFontWeight('bold').setBackground('#1a73e8').setFontColor('white').setWrap(true);
    leads.setFrozenRows(1);
    leads.setFrozenColumns(5);
    const n = leads.getMaxRows() - 1;
    leads.getRange(2, C['Status'], n).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(STATUS, true).build());
    leads.getRange(2, C['Enviei?'], n).insertCheckboxes();
    leads.getRange(2, C['Próximo follow-up'], n).setNumberFormat('dd/mm/yyyy');
    leads.getRange(2, C['Adicionado em'], n).setNumberFormat('dd/mm/yyyy');
    const larguras = { 'Score': 55, 'Temperatura': 85, 'Status': 105, 'Enviei?': 60, 'Nome': 230,
      'Oportunidades': 300, 'Mensagem': 360, 'Notas': 220, 'WhatsApp': 130 };
    Object.keys(larguras).forEach(k => leads.setColumnWidth(C[k], larguras[k]));
    OCULTAS.forEach(k => leads.hideColumns(C[k]));
    // cores da temperatura
    const faixa = leads.getRange(2, C['Temperatura'], n);
    const cores = { quente: '#f4c7c3', morno: '#fce8b2', frio: '#c9daf8' };
    leads.setConditionalFormatRules(Object.keys(cores).map(t =>
      SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo(t).setBackground(cores[t]).setRanges([faixa]).build()));
    const sobra = ss.getSheetByName('Página1') || ss.getSheetByName('Sheet1');
    if (sobra && sobra.getLastRow() === 0) ss.deleteSheet(sobra);
  }

  criarAbasDeApoio_(ss);

  if (!PropertiesService.getDocumentProperties().getProperty('CHAVE')) trocarChave();
  ui.alert('Pronto!',
    '1) Preencha seus dados na aba "Config".\n' +
    '2) Use o menu 📍 Prospecção → "Buscar empresas no Google Maps".\n\n' +
    'Depois de mandar uma mensagem, marque a caixa "Enviei?" do lead: a planilha muda o status, ' +
    'agenda o follow-up e já prepara a próxima mensagem.', ui.ButtonSet.OK);
}

function criarAbasDeApoio_(ss) {
  const L = c => letra_(C[c]);
  if (!ss.getSheetByName('Follow-ups')) {
    const f = ss.insertSheet('Follow-ups');
    f.getRange('A1').setValue('Follow-ups para hoje (atualiza sozinho). Envie pelo link e marque "Enviei?" na aba Leads.')
      .setFontWeight('bold');
    f.getRange('A3').setFormula(
      `=IFERROR(QUERY(Leads!A2:${L('Busca')}, "select ${L('Nome')}, ${L('Status')}, ${L('Próximo follow-up')}, ` +
      `${L('Etapa')}, ${L('Link WhatsApp')}, ${L('Telefone')} where ${L('Próximo follow-up')} is not null and ` +
      `${L('Próximo follow-up')} <= date '"&TEXT(TODAY(),"yyyy-mm-dd")&"' and ${L('Status')} matches ` +
      `'contatado|respondeu|reuniao|proposta' order by ${L('Próximo follow-up')} label ${L('Nome')} 'Nome', ` +
      `${L('Status')} 'Status', ${L('Próximo follow-up')} 'Vence em', ${L('Etapa')} 'Etapa', ` +
      `${L('Link WhatsApp')} 'Link WhatsApp', ${L('Telefone')} 'Telefone'", 0), "Nenhum follow-up para hoje 🎉")`);
    f.setColumnWidth(1, 260);
    f.setColumnWidth(5, 320);
  }
  if (!ss.getSheetByName('Funil')) {
    const f = ss.insertSheet('Funil');
    f.getRange('A1').setValue('Funil de vendas').setFontWeight('bold');
    f.getRange('A3').setFormula(
      `=QUERY({Leads!${L('Status')}2:${L('Status')}}, "select Col1, count(Col1) where Col1 is not null ` +
      `group by Col1 label Col1 'Etapa', count(Col1) 'Leads'", 0)`);
    f.getRange('D3').setValue('Leads quentes');
    f.getRange('E3').setFormula(`=COUNTIF(Leads!${L('Temperatura')}:${L('Temperatura')}, "quente")`);
    f.getRange('D4').setValue('Contatados até hoje');
    f.getRange('E4').setFormula(`=COUNTIF(Leads!${L('Etapa')}2:${L('Etapa')}, ">0")`);
    f.getRange('D5').setValue('Responderam ou avançaram');
    f.getRange('E5').setFormula(`=COUNTIFS(Leads!${L('Status')}:${L('Status')}, "respondeu")+COUNTIF(Leads!${L('Status')}:${L('Status')}, "reuniao")+COUNTIF(Leads!${L('Status')}:${L('Status')}, "proposta")+COUNTIF(Leads!${L('Status')}:${L('Status')}, "fechado")`);
    f.getRange('D6').setValue('Taxa de resposta');
    f.getRange('E6').setFormula('=IFERROR(E5/E4, 0)').setNumberFormat('0%');
    f.getRange('D7').setValue('Fechados');
    f.getRange('E7').setFormula(`=COUNTIF(Leads!${L('Status')}:${L('Status')}, "fechado")`);
    f.setColumnWidth(4, 220);
  }
}

function trocarChave() {
  const ui = SpreadsheetApp.getUi();
  const r = ui.prompt('Chave do Google Maps',
    'Cole sua chave de API (começa com AIza...). Ela fica guardada só nesta planilha, fora das células.',
    ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() === ui.Button.OK && r.getResponseText().trim()) {
    PropertiesService.getDocumentProperties().setProperty('CHAVE', r.getResponseText().trim());
    ui.alert('Chave salva ✅');
  }
}

function lerConfig_() {
  const aba = SpreadsheetApp.getActive().getSheetByName(ABA_CONFIG);
  const v = aba ? aba.getRange(2, 2, 8, 1).getValues().map(r => r[0]) : [];
  return {
    nome: v[0] || '[seu nome]', empresa: v[1] || '[sua empresa]',
    beneficio: v[2] || 'atrair mais clientes pela internet', publico: v[3] || '',
    cadencia: String(v[4] || '3,7').split(',').map(x => parseInt(x, 10)).filter(x => x > 0),
    excluir: String(v[5] || '').split(',').map(x => x.trim().toLowerCase()).filter(String),
    maxAvaliacoes: Number(v[6]) || 0, notaMin: Number(v[7]) || 0,
  };
}

// ======================= busca no Google Maps =======================
function buscarEmpresas() {
  const ui = SpreadsheetApp.getUi();
  const chave = PropertiesService.getDocumentProperties().getProperty('CHAVE');
  if (!chave) return configurar();
  const aba = SpreadsheetApp.getActive().getSheetByName(ABA_LEADS);
  if (!aba) return configurar();

  const r1 = ui.prompt('O que buscar?', 'Separe por vírgula. Ex.: dentista, clínica odontológica', ui.ButtonSet.OK_CANCEL);
  if (r1.getSelectedButton() !== ui.Button.OK) return;
  const r2 = ui.prompt('Onde?', 'Separe por ponto e vírgula. Ex.: Campinas, SP; Valinhos, SP', ui.ButtonSet.OK_CANCEL);
  if (r2.getSelectedButton() !== ui.Button.OK) return;
  const r3 = ui.prompt('Cobertura',
    '1 = normal (até 60 empresas por busca)\n2 ou 3 = cidade grande (divide a cidade em 4 ou 9 áreas, gasta mais)',
    ui.ButtonSet.OK_CANCEL);
  if (r3.getSelectedButton() !== ui.Button.OK) return;

  const consultas = r1.getResponseText().split(',').map(s => s.trim()).filter(String);
  const locais = r2.getResponseText().split(';').map(s => s.trim()).filter(String);
  const grade = Math.min(4, Math.max(1, parseInt(r3.getResponseText(), 10) || 1));
  if (!consultas.length) return;
  const estimativa = consultas.length * Math.max(1, locais.length) * grade * grade * 3;
  if (ui.alert('Confirmar', `Serão feitas até ${estimativa} chamadas à API do Google Maps. Continuar?`,
    ui.ButtonSet.YES_NO) !== ui.Button.YES) return;

  const cfg = lerConfig_();
  const existentes = new Set(aba.getLastRow() > 1
    ? aba.getRange(2, C['Place ID'], aba.getLastRow() - 1).getValues().map(r => r[0]) : []);
  const novos = [];
  let total = 0;
  const inicio = Date.now();

  for (const q of consultas) {
    for (const local of (locais.length ? locais : [''])) {
      const texto = local ? `${q} em ${local}` : q;
      const areas = grade > 1 && local ? dividir_(areaDe_(local, chave), grade) : [null];
      for (const area of areas) {
        if (Date.now() - inicio > 300000) break; // limite de 6 min do Apps Script
        for (const p of buscarTexto_(texto, area, chave)) {
          total++;
          if (existentes.has(p.id)) continue;
          existentes.add(p.id);
          const lead = deLugar_(p, texto);
          if (!passaFiltros_(lead, cfg, p.businessStatus)) continue;
          novos.push(lead);
        }
      }
    }
  }

  novos.forEach(l => preparar_(l, cfg));
  gravar_(aba, novos);
  ordenarPorScore();
  ui.alert('Busca concluída',
    `${total} empresas encontradas, ${novos.length} novas adicionadas.\n\n` +
    'Próximo passo (opcional): menu → "Analisar sites" para achar e-mails, Instagram e pixel.',
    ui.ButtonSet.OK);
}

function buscarTexto_(texto, area, chave) {
  const corpo = { textQuery: texto, languageCode: 'pt-BR', regionCode: 'BR', pageSize: 20 };
  if (area) corpo.locationRestriction = { rectangle: area };
  const lugares = [];
  for (let pagina = 0; pagina < 3; pagina++) {
    const resp = UrlFetchApp.fetch('https://places.googleapis.com/v1/places:searchText', {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { 'X-Goog-Api-Key': chave, 'X-Goog-FieldMask': CAMPOS_MAPS },
      payload: JSON.stringify(corpo),
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error('Google Maps respondeu ' + resp.getResponseCode() + ': ' + resp.getContentText().slice(0, 300) +
        '\n\nConfira se a "Places API (New)" está ativada e se o faturamento está ligado.');
    }
    const dados = JSON.parse(resp.getContentText());
    (dados.places || []).forEach(p => lugares.push(p));
    if (!dados.nextPageToken) break;
    corpo.pageToken = dados.nextPageToken;
    Utilities.sleep(1500);
  }
  return lugares;
}

function areaDe_(local, chave) {
  const url = 'https://maps.googleapis.com/maps/api/geocode/json?language=pt-BR&region=br&address=' +
    encodeURIComponent(local) + '&key=' + encodeURIComponent(chave);
  const d = JSON.parse(UrlFetchApp.fetch(url, { muteHttpExceptions: true }).getContentText());
  if (d.status !== 'OK') throw new Error(`Não achei "${local}" (Geocoding: ${d.status}). Ative a Geocoding API ou use cobertura 1.`);
  const vp = d.results[0].geometry.viewport;
  return { low: { latitude: vp.southwest.lat, longitude: vp.southwest.lng },
           high: { latitude: vp.northeast.lat, longitude: vp.northeast.lng } };
}

function dividir_(r, n) {
  const dLat = (r.high.latitude - r.low.latitude) / n, dLng = (r.high.longitude - r.low.longitude) / n;
  const out = [];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    out.push({ low: { latitude: r.low.latitude + i * dLat, longitude: r.low.longitude + j * dLng },
               high: { latitude: r.low.latitude + (i + 1) * dLat, longitude: r.low.longitude + (j + 1) * dLng } });
  }
  return out;
}

function deLugar_(p, busca) {
  let cidade = '', uf = '';
  (p.addressComponents || []).forEach(c => {
    if (c.types.indexOf('administrative_area_level_2') >= 0) cidade = c.longText;
    if (c.types.indexOf('administrative_area_level_1') >= 0) uf = c.shortText;
  });
  const e164 = paraE164_(p.internationalPhoneNumber || p.nationalPhoneNumber || '');
  return {
    status: 'novo', etapa: 0, nome: (p.displayName || {}).text || '',
    categoria: (p.primaryTypeDisplayName || {}).text || '',
    cidade: cidade && uf ? `${cidade}/${uf}` : cidade, telefone: p.nationalPhoneNumber || '',
    celular: ehCelular_(e164) ? e164 : '', email: '', instagram: '', site: p.websiteUri || '',
    nota: p.rating || '', avaliacoes: p.userRatingCount || 0, maps: p.googleMapsUri || '',
    placeId: p.id, enriquecido: '', busca: busca, notas: '', followup: '', adicionado: new Date(),
  };
}

function passaFiltros_(l, cfg, statusNegocio) {
  if (statusNegocio && statusNegocio !== 'OPERATIONAL') return false;
  if (cfg.maxAvaliacoes && l.avaliacoes > cfg.maxAvaliacoes) return false;
  if (cfg.notaMin && l.nota && l.nota < cfg.notaMin) return false;
  const nome = l.nome.toLowerCase();
  return !cfg.excluir.some(p => nome.indexOf(p) >= 0);
}

// ======================= telefone =======================
function paraE164_(t) {
  let d = String(t).replace(/\D/g, '').replace(/^0+/, '');
  if (d.indexOf('55') === 0 && (d.length === 12 || d.length === 13)) return d;
  if (d.length === 10 || d.length === 11) return '55' + d;
  return '';
}
function ehCelular_(e) { return e.length === 13 && e.indexOf('55') === 0 && e.charAt(4) === '9'; }
function formatarTel_(e) { return e.length === 13 ? `(${e.slice(2, 4)}) ${e.slice(4, 9)}-${e.slice(9)}` : e; }

// ======================= score =======================
function pontuar_(l) {
  let pts = 0;
  const motivos = [];
  const add = (p, m) => { pts += p; motivos.push(m); };
  const enr = String(l.enriquecido || '');
  if (!l.site) add(25, 'Não tem site');
  else if (enr.indexOf('fora do ar') >= 0) add(20, 'Site fora do ar');
  else if (enr) {
    if (l.site.indexOf('https://') !== 0) add(8, 'Site sem HTTPS');
    if (enr.indexOf('pixel') < 0) add(8, 'Sem Pixel da Meta');
    if (enr.indexOf('analytics') < 0) add(5, 'Sem Google Analytics');
    if (!l.instagram) add(8, 'Instagram não encontrado');
  }
  if (Number(l.avaliacoes) < 20) add(12, `Poucas avaliações (${l.avaliacoes})`);
  if (l.nota && Number(l.nota) < 4.2) add(8, `Nota baixa (${l.nota})`);
  if (l.celular) add(12, 'Tem WhatsApp');
  if (l.email) add(5, 'Tem e-mail');
  if (Number(l.avaliacoes) >= 50) add(6, 'Negócio estabelecido');
  l.score = Math.min(100, pts);
  l.temperatura = l.score >= 55 ? 'quente' : l.score >= 30 ? 'morno' : 'frio';
  l.oportunidades = motivos.join('; ');
  return l;
}

// ======================= mensagens =======================
const GANCHOS = [
  ['Não tem site', 'vocês ainda não têm um site aparecendo no perfil do Google'],
  ['Site fora do ar', 'o site do perfil não está abrindo'],
  ['Site sem HTTPS', 'o site aparece como "não seguro" no navegador'],
  ['Poucas avaliações', 'o perfil tem poucas avaliações perto do potencial do negócio'],
  ['Nota baixa', 'algumas avaliações estão puxando a nota do perfil para baixo'],
  ['Sem Pixel', 'o site não está medindo quem visita para anunciar depois'],
  ['Instagram não encontrado', 'não achei o Instagram de vocês a partir do Google'],
];

function mensagem_(l, cfg) {
  const ops = String(l.oportunidades || '');
  const g = GANCHOS.find(x => ops.indexOf(x[0]) >= 0);
  const gancho = g ? g[1] : 'o perfil de vocês tem bastante potencial';
  const cidade = String(l.cidade || '').split('/')[0] || 'sua região';
  const cat = String(l.categoria || 'negócio').toLowerCase();
  const publico = cfg.publico || (/s$/.test(cat) ? cat : cat + 's');
  const seq = [
    `Oi, tudo bem? Aqui é ${cfg.nome}, da ${cfg.empresa}. Encontrei o perfil "${l.nome}" no Google Maps e reparei que ${gancho}. ` +
      `Ajudo ${publico} de ${cidade} a ${cfg.beneficio}. Posso te mandar uma ideia rápida de como faríamos isso para vocês?`,
    `Oi! Passando de novo por aqui 🙂 Separei 2 sugestões práticas para vocês atraírem mais clientes pelo Google. ` +
      `Quer que eu te mande por aqui mesmo?`,
    `Último contato da minha parte, prometo! Se fizer sentido conversar sobre como ${cfg.beneficio}, é só me responder. ` +
      `Se não for o momento, sem problema — muito sucesso para vocês!`,
  ];
  return seq[Math.min(Number(l.etapa) || 0, seq.length - 1)];
}

function preparar_(l, cfg) {
  pontuar_(l);
  if (l.status === 'novo' && l.temperatura === 'quente') l.status = 'qualificado';
  l.mensagem = mensagem_(l, cfg);
  l.link = l.celular ? 'https://wa.me/' + l.celular + '?text=' + encodeURIComponent(l.mensagem) : '';
  return l;
}

// ======================= leitura/gravação =======================
function paraLinha_(l) {
  const r = new Array(COLUNAS.length).fill('');
  const s = (k, v) => (r[C[k] - 1] = v);
  s('Score', l.score); s('Temperatura', l.temperatura); s('Status', l.status); s('Enviei?', false);
  s('Nome', l.nome); s('Categoria', l.categoria); s('Cidade', l.cidade); s('Telefone', l.telefone);
  s('WhatsApp', l.celular ? formatarTel_(l.celular) : ''); s('E-mail', l.email); s('Instagram', l.instagram);
  s('Site', l.site); s('Nota', l.nota); s('Avaliações', l.avaliacoes); s('Oportunidades', l.oportunidades);
  s('Mensagem', l.mensagem); s('Próximo follow-up', l.followup); s('Etapa', l.etapa); s('Notas', l.notas);
  s('Google Maps', l.maps); s('Adicionado em', l.adicionado); s('Link WhatsApp', l.link);
  s('Celular', l.celular ? "'" + l.celular : ''); s('Enriquecido', l.enriquecido); s('Place ID', l.placeId);
  s('Busca', l.busca);
  return r;
}

function deLinha_(r) {
  const g = k => r[C[k] - 1];
  return {
    score: g('Score'), temperatura: g('Temperatura'), status: g('Status'), nome: g('Nome'),
    categoria: g('Categoria'), cidade: g('Cidade'), telefone: g('Telefone'), email: g('E-mail'),
    instagram: g('Instagram'), site: g('Site'), nota: g('Nota'), avaliacoes: g('Avaliações'),
    oportunidades: g('Oportunidades'), mensagem: g('Mensagem'), followup: g('Próximo follow-up'),
    etapa: Number(g('Etapa')) || 0, notas: g('Notas'), maps: g('Google Maps'), adicionado: g('Adicionado em'),
    link: g('Link WhatsApp'), celular: String(g('Celular') || ''), enriquecido: g('Enriquecido'),
    placeId: g('Place ID'), busca: g('Busca'),
  };
}

function linkWhats_(l) {
  const texto = l.celular ? '💬 ' + formatarTel_(l.celular) : '';
  const b = SpreadsheetApp.newRichTextValue().setText(texto);
  if (l.link && texto) b.setLinkUrl(l.link);
  return b.build();
}

function gravar_(aba, leads, linhaInicial) {
  if (!leads.length) return;
  const ini = linhaInicial || aba.getLastRow() + 1;
  const falta = ini + leads.length - 1 - aba.getMaxRows();
  if (falta > 0) aba.insertRowsAfter(aba.getMaxRows(), falta + 100);
  aba.getRange(ini, 1, leads.length, COLUNAS.length).setValues(leads.map(paraLinha_));
  aba.getRange(ini, C['WhatsApp'], leads.length, 1).setRichTextValues(leads.map(l => [linkWhats_(l)]));
}

function todos_() {
  const aba = SpreadsheetApp.getActive().getSheetByName(ABA_LEADS);
  const n = aba.getLastRow() - 1;
  return { aba, leads: n > 0 ? aba.getRange(2, 1, n, COLUNAS.length).getValues().map(deLinha_) : [] };
}

function refazerTudo() {
  const { aba, leads } = todos_();
  const cfg = lerConfig_();
  leads.forEach(l => preparar_(l, cfg));
  gravar_(aba, leads, 2);
  SpreadsheetApp.getActive().toast(`${leads.length} leads atualizados`, 'Prospecção');
}

function ordenarPorScore() {
  const aba = SpreadsheetApp.getActive().getSheetByName(ABA_LEADS);
  if (aba.getLastRow() > 2) {
    aba.getRange(2, 1, aba.getLastRow() - 1, COLUNAS.length).sort({ column: C['Score'], ascending: false });
  }
}

// ======================= análise dos sites =======================
function analisarSites() {
  const { aba, leads } = todos_();
  const cfg = lerConfig_();
  const pendentes = leads.map((l, i) => ({ l, i })).filter(x => x.l.site && !x.l.enriquecido);
  if (!pendentes.length) return SpreadsheetApp.getUi().alert('Todos os sites já foram analisados ✅');
  const inicio = Date.now();
  let feitos = 0;
  for (let k = 0; k < pendentes.length; k += 10) {
    if (Date.now() - inicio > 270000) break;
    const lote = pendentes.slice(k, k + 10);
    const respostas = buscarVarios_(lote.map(x => x.l.site));
    lote.forEach((x, j) => {
      analisarHtml_(x.l, respostas[j]);
      preparar_(x.l, cfg);
      gravar_(aba, [x.l], x.i + 2);
      feitos++;
    });
  }
  const falta = pendentes.length - feitos;
  SpreadsheetApp.getUi().alert('Análise dos sites',
    `${feitos} sites analisados.` + (falta ? `\nFaltam ${falta}: rode "Analisar sites" de novo para continuar.` : ''),
    SpreadsheetApp.getUi().ButtonSet.OK);
}

function buscarVarios_(urls) {
  const pedidos = urls.map(u => ({ url: u, muteHttpExceptions: true, followRedirects: true,
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36' } }));
  try {
    return UrlFetchApp.fetchAll(pedidos).map(r => (r.getResponseCode() < 400 ? r.getContentText() : null));
  } catch (e) { // um endereço inválido derruba o lote todo: tenta um a um
    return pedidos.map(p => {
      try {
        const r = UrlFetchApp.fetch(p.url, p);
        return r.getResponseCode() < 400 ? r.getContentText() : null;
      } catch (e2) { return null; }
    });
  }
}

function analisarHtml_(l, html) {
  if (html === null || html === undefined) { l.enriquecido = 'fora do ar'; return; }
  const sinais = ['ok'];
  let texto = html;
  try { texto = decodeURIComponent(html.replace(/%(?![0-9A-Fa-f]{2})/g, '%25')); } catch (e) { /* mantém o HTML original */ }
  if (!l.email) {
    const emails = (texto.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [])
      .map(e => e.toLowerCase())
      .filter(e => !/\.(png|jpe?g|gif|webp|svg|css|js)$|@(sentry|example|exemplo|wixpress|domain)\./.test(e));
    if (emails.length) l.email = emails[0];
  }
  if (!l.instagram) {
    const m = texto.match(/https?:\/\/(?:www\.)?instagram\.com\/(?!p\/|reel\/|explore\/|share)[A-Za-z0-9_.]+/i);
    if (m) l.instagram = m[0];
  }
  if (!l.celular) {
    const wa = texto.match(/(?:wa\.me\/|api\.whatsapp\.com\/send\/?\?phone=)\+?(\d{10,13})/i);
    if (wa && paraE164_(wa[1])) l.celular = paraE164_(wa[1]);
  }
  if (/fbq\(|fbevents\.js/.test(html)) sinais.push('pixel');
  if (/gtag\(|google-analytics\.com|googletagmanager\.com/.test(html)) sinais.push('analytics');
  l.enriquecido = sinais.join(', ');
}

// ======================= automações ao editar =======================
function onEdit(e) {
  const aba = e.range.getSheet();
  if (aba.getName() !== ABA_LEADS || e.range.getRow() < 2 || e.range.getNumRows() > 1) return;
  const linha = e.range.getRow();
  const col = e.range.getColumn();

  if (col === C['Enviei?'] && e.value === 'TRUE') {
    const cfg = lerConfig_();
    const l = deLinha_(aba.getRange(linha, 1, 1, COLUNAS.length).getValues()[0]);
    const hoje = new Date();
    if (l.status === 'novo' || l.status === 'qualificado' || !l.status) l.status = 'contatado';
    const dias = cfg.cadencia[l.etapa];
    l.followup = dias ? new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() + dias) : '';
    l.notas = (l.notas ? l.notas + '\n' : '') +
      `[${Utilities.formatDate(hoje, Session.getScriptTimeZone(), 'dd/MM')}] mensagem ${l.etapa + 1} enviada`;
    l.etapa += 1;
    l.mensagem = mensagem_(l, cfg);
    l.link = l.celular ? 'https://wa.me/' + l.celular + '?text=' + encodeURIComponent(l.mensagem) : '';
    const s = (k, v) => aba.getRange(linha, C[k]).setValue(v);
    s('Status', l.status); s('Próximo follow-up', l.followup); s('Notas', l.notas); s('Etapa', l.etapa);
    s('Mensagem', l.mensagem); s('Link WhatsApp', l.link); s('Enviei?', false);
    aba.getRange(linha, C['WhatsApp']).setRichTextValue(linkWhats_(l));
    SpreadsheetApp.getActive().toast(l.followup ? 'Follow-up agendado ✅' : 'Cadência concluída ✅', l.nome);
  }

  if (col === C['Status'] && ['fechado', 'perdido', 'nao_contatar'].indexOf(e.value) >= 0) {
    aba.getRange(linha, C['Próximo follow-up']).setValue('');
  }
}

function letra_(n) {
  let s = '';
  while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
  return s;
}
