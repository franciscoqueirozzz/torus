'use strict';

const $ = id => document.getElementById(id);
const state = {
  token: sessionStorage.getItem('torus_token'), user: null,
  meetings: [], customers: [], tasks: [], users: [], sellers: [], page: 'overview',
  saveEntity: null, detail: null,
};
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
const stages = { prospect: 'Negociação', active: 'Ativo', renewal: 'Renovação', inactive: 'Inativo' };
const intents = { churn_risk: 'Risco', price_objection: 'Preço', upsell_opportunity: 'Expansão', satisfaction: 'Satisfação', neutral: 'Neutro' };
const titles = { overview: 'Resumo', customers: 'Clientes', meetings: 'Reuniões', tasks: 'Tarefas', upload: 'Nova análise', team: 'Equipe', account: 'Minha conta' };
const smallScreen = window.matchMedia('(max-width: 760px)');
function updateSidebarAccess() {
  $('sidebar').inert = smallScreen.matches && !$('sidebar').classList.contains('open');
}
smallScreen.addEventListener('change', updateSidebarAccess);
updateSidebarAccess();
const points = value => `${Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} pts`;
const roleName = role => role === 'manager' ? 'Gerente' : 'Vendedor';
const riskClass = value => value >= 70 ? 'high' : value >= 40 ? 'medium' : 'low';
const riskName = value => value >= 70 ? 'Prioridade' : value >= 40 ? 'Atenção' : 'Baixo';
const today = () => new Date().toLocaleDateString('sv-SE');
const dateText = value => value ? new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value.length === 10 ? `${value}T12:00:00` : `${value.replace(' ', 'T')}Z`)) : 'Sem data';
const overdue = task => task.status === 'open' && task.due_date < today();
const badge = (text, kind = '') => `<span class="badge ${kind}">${esc(text)}</span>`;
const empty = (title, description, action = '') => `<div class="empty"><strong>${esc(title)}</strong>${esc(description)}${action ? `<div>${action}</div>` : ''}</div>`;

async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new Error('Sem conexão com o Torus.');
  }
  if (response.status === 401 && path !== '/auth/login') {
    clearSession();
    throw new Error('Sessão expirada. Entre novamente.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir.');
  }
  return options.download ? response.blob() : response.json();
}

let toastTimer;
function notify(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000);
}

function report(error) {
  const target = state.user ? $('globalError') : $('loginError');
  target.hidden = false;
  target.textContent = error.message;
}

function clearSession() {
  state.token = null;
  state.user = null;
  state.meetings = []; state.customers = []; state.tasks = []; state.users = []; state.sellers = [];
  sessionStorage.removeItem('torus_token');
  document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
  $('appView').hidden = true;
  $('loginView').hidden = false;
  $('password').value = '';
}

async function refresh() {
  const manager = state.user.role === 'manager';
  const [meetings, customers, tasks, users, sellers] = await Promise.all([
    api('/meetings'), api('/customers'), api('/tasks'),
    manager ? api('/users') : Promise.resolve([]),
    manager ? api('/users/sellers') : Promise.resolve([]),
  ]);
  Object.assign(state, { meetings, customers, tasks, users, sellers });
  $('globalError').hidden = true;
  render();
}

async function enterApp() {
  state.user = await api('/auth/me');
  await refresh();
  $('sideUserName').textContent = state.user.name;
  $('sideUserRole').textContent = roleName(state.user.role);
  $('scopeLabel').textContent = state.user.role === 'manager' ? 'CARTEIRA DA EQUIPE' : 'MINHA CARTEIRA';
  $('accountIdentity').textContent = `${state.user.name} · ${state.user.email} · ${roleName(state.user.role)}`;
  document.querySelectorAll('[data-manager]').forEach(item => { item.hidden = state.user.role !== 'manager'; });
  $('loginView').hidden = true;
  $('appView').hidden = false;
  showPage('overview');
}

function showPage(page) {
  if (!(page in titles) || (page === 'team' && state.user.role !== 'manager')) return;
  state.page = page;
  document.querySelectorAll('.page').forEach(section => { section.hidden = section.id !== `page-${page}`; });
  document.querySelectorAll('nav [data-page]').forEach(button => button.classList.toggle('active', button.dataset.page === page));
  $('pageTitle').textContent = page === 'overview' && state.user.role === 'manager' ? 'Visão da equipe' : titles[page];
  $('sidebar').classList.remove('open');
  $('mobileMenu').setAttribute('aria-expanded', 'false');
  updateSidebarAccess();
  window.scrollTo({ top: 0 });
}

function meetingTable(meetings) {
  if (!meetings.length) return empty('Nenhuma reunião', 'Envie uma transcrição ou ajuste os filtros.');
  return `<div class="table-scroll"><table><thead><tr><th>Cliente / reunião</th><th>Registrada em</th><th>Risco</th><th>Expansão</th><th>Revisão</th><th>Detalhes</th></tr></thead><tbody>${meetings.map(item => `<tr>
    <td><strong>${esc(item.customer_name)}</strong>${esc(item.title)}<small>${esc(item.seller.name)}</small></td>
    <td>${dateText(item.created_at)}</td><td class="score ${riskClass(item.summary.churn_risk_score)}">${points(item.summary.churn_risk_score)}</td><td class="score">${points(item.summary.opportunity_score)}</td>
    <td>${badge(riskName(item.summary.churn_risk_score), riskClass(item.summary.churn_risk_score))}</td><td><button data-meeting="${item.id}">Ver análise</button></td></tr>`).join('')}</tbody></table></div>`;
}

function taskRows(tasks, compact = false) {
  if (!tasks.length) return empty('Nenhuma tarefa', 'Crie uma tarefa para o próximo contato.');
  return tasks.map(task => `<div class="list-row"><div><strong>${esc(task.title)}</strong><small>${esc(task.customer_name)} · ${esc(task.seller_name)}</small><small>${dateText(task.due_date)}${task.priority === 'high' ? ' · Prioridade alta' : ''}</small></div><div class="actions">${badge(task.status === 'done' ? 'Concluída' : overdue(task) ? 'Em atraso' : 'Pendente', task.status === 'done' ? 'done' : overdue(task) ? 'high' : '')}<button data-task="${task.id}">${compact ? 'Abrir' : 'Editar tarefa'}</button></div></div>`).join('');
}

function sellerStats() {
  const avg = list => list.length ? list.reduce((sum, value) => sum + value, 0) / list.length : 0;
  const bySeller = new Map();
  for (const seller of state.sellers) bySeller.set(seller.id, { id: seller.id, name: seller.name, meetings: [] });
  for (const item of state.meetings) {
    if (!bySeller.has(item.seller.id)) bySeller.set(item.seller.id, { id: item.seller.id, name: item.seller.name, meetings: [] });
    bySeller.get(item.seller.id).meetings.push(item);
  }
  return [...bySeller.values()].map(entry => {
    const sellerTasks = state.tasks.filter(task => task.seller_id === entry.id);
    const openTasks = sellerTasks.filter(task => task.status === 'open');
    const lastMeeting = [...entry.meetings].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null;
    return {
      id: entry.id, name: entry.name, meetingCount: entry.meetings.length,
      avgRisk: avg(entry.meetings.map(item => item.summary.churn_risk_score)),
      avgOpportunity: avg(entry.meetings.map(item => item.summary.opportunity_score)),
      openTasks: openTasks.length, overdueTasks: openTasks.filter(overdue).length, lastMeeting,
    };
  });
}

function sellerRankingTable(list) {
  if (!list.length) return empty('Nenhum vendedor cadastrado', 'Cadastre pessoas na equipe para ver o ranking.');
  const sorted = [...list].sort((a, b) => b.meetingCount - a.meetingCount || b.avgOpportunity - a.avgOpportunity);
  return `<div class="table-scroll"><table><thead><tr><th>#</th><th>Vendedor</th><th>Reuniões</th><th>Risco médio</th><th>Expansão média</th><th>Tarefas</th></tr></thead><tbody>${sorted.map((seller, index) => `<tr>
    <td>${index === 0 && seller.meetingCount ? badge('Destaque', 'done') : `${index + 1}º`}</td>
    <td><strong>${esc(seller.name)}</strong></td>
    <td>${seller.meetingCount}</td>
    <td class="score ${seller.meetingCount ? riskClass(seller.avgRisk) : ''}">${seller.meetingCount ? points(seller.avgRisk) : '—'}</td>
    <td class="score">${seller.meetingCount ? points(seller.avgOpportunity) : '—'}</td>
    <td>${seller.overdueTasks > 0 ? badge(`${seller.overdueTasks} em atraso`, 'high') : badge(seller.openTasks ? `${seller.openTasks} em dia` : 'Sem pendências', 'done')}</td>
  </tr>`).join('')}</tbody></table></div>`;
}

function sellerCompareChart(list) {
  const active = list.filter(seller => seller.meetingCount);
  if (!active.length) return empty('Sem dados para comparar', 'O comparativo aparece quando houver reuniões analisadas.');
  const sorted = [...active].sort((a, b) => b.avgOpportunity - a.avgOpportunity);
  return sorted.map(seller => `<div class="compare-row">
    <strong>${esc(seller.name)}</strong>
    <div class="compare-bars">
      <div class="compare-bar"><span>Risco</span><div class="compare-bar-track"><div class="compare-bar-fill risk" style="width:${Math.min(100, seller.avgRisk)}%"></div></div><span class="compare-bar-value">${points(seller.avgRisk)}</span></div>
      <div class="compare-bar"><span>Expansão</span><div class="compare-bar-track"><div class="compare-bar-fill opportunity" style="width:${Math.min(100, seller.avgOpportunity)}%"></div></div><span class="compare-bar-value">${points(seller.avgOpportunity)}</span></div>
    </div>
  </div>`).join('');
}

function sellerMeetingsCompareCards(list) {
  if (!list.length) return empty('Nenhum vendedor cadastrado', 'Cadastre pessoas na equipe para acompanhar reuniões.');
  return list.map(seller => `<article class="card customer-card">
    <h3>${esc(seller.name)}</h3>
    <p class="meta">${seller.meetingCount} reunião${seller.meetingCount === 1 ? '' : 'ões'} registrada${seller.meetingCount === 1 ? '' : 's'}</p>
    <div class="customer-stats">
      <div><strong class="score ${seller.meetingCount ? riskClass(seller.avgRisk) : ''}">${seller.meetingCount ? points(seller.avgRisk) : '—'}</strong><small>risco médio</small></div>
      <div><strong>${seller.meetingCount ? points(seller.avgOpportunity) : '—'}</strong><small>expansão média</small></div>
      <div><strong>${seller.openTasks}</strong><small>tarefas abertas</small></div>
    </div>
    ${seller.lastMeeting ? `<p class="small muted">Última: <strong>${esc(seller.lastMeeting.customer_name)}</strong> · ${dateText(seller.lastMeeting.created_at)}</p><div class="actions"><button data-meeting="${seller.lastMeeting.id}">Ver última reunião</button></div>` : '<p class="small muted">Ainda sem reuniões registradas.</p>'}
  </article>`).join('');
}

function renderTeamDashboard() {
  if (state.user.role !== 'manager') return;
  const stats = sellerStats();
  const active = stats.filter(seller => seller.meetingCount);
  const avg = list => list.length ? list.reduce((sum, value) => sum + value, 0) / list.length : 0;
  const teamMetrics = [
    ['Vendedores', state.sellers.length, 'na equipe', ''],
    ['Reuniões', state.meetings.length, 'analisadas', ''],
    ['Risco médio', points(avg(active.map(seller => seller.avgRisk))), 'da equipe', ''],
    ['Expansão média', points(avg(active.map(seller => seller.avgOpportunity))), 'da equipe', ''],
    ['Em atraso', state.tasks.filter(overdue).length, 'tarefas da equipe', 'alert'],
  ];
  $('teamMetrics').innerHTML = teamMetrics.map(([label, count, note, kind]) => `<article class="metric ${kind}"><span>${label}</span><strong>${count}</strong><small>${note}</small></article>`).join('');
  $('todayLabel2').textContent = dateText(today());
  $('sellerRanking').innerHTML = sellerRankingTable(stats);
  $('sellerCompareChart').innerHTML = sellerCompareChart(stats);
  $('sellerMeetingsCompare').innerHTML = sellerMeetingsCompareCards(stats);
}

function renderOverview() {
  renderTeamDashboard();
  const openTasks = state.tasks.filter(task => task.status === 'open');
  const urgentCustomers = state.customers.filter(item => item.latest_summary?.churn_risk_score >= 70);
  const metrics = [
    ['Clientes', state.customers.length, 'na carteira', ''],
    ['Tarefas', openTasks.length, 'pendentes', ''],
    ['Em atraso', openTasks.filter(overdue).length, 'tarefas', 'alert'],
    ['Revisar', urgentCustomers.length, 'clientes', 'alert'],
  ];
  $('metrics').innerHTML = metrics.map(([label, count, note, kind]) => `<article class="metric ${kind}"><span>${label}</span><strong>${count}</strong><small>${note}</small></article>`).join('');
  $('todayLabel').textContent = dateText(today());
  $('taskCount').textContent = openTasks.length || '';
  $('upcomingTasks').innerHTML = taskRows(openTasks.slice(0, 4), true);
  const priority = [...state.customers].filter(item => item.latest_summary?.churn_risk_score >= 40 || item.latest_summary?.opportunity_score >= 45).sort((a, b) => b.latest_summary.churn_risk_score - a.latest_summary.churn_risk_score).slice(0, 4);
  $('priorityCustomers').innerHTML = priority.length ? priority.map(item => `<div class="list-row"><div><strong>${esc(item.name)}</strong><small>${esc(item.seller_name)} · ${item.latest_summary.churn_risk_score >= 40 ? `${points(item.latest_summary.churn_risk_score)} de risco` : `${points(item.latest_summary.opportunity_score)} de expansão`}</small></div><button data-customer="${item.id}">Abrir</button></div>`).join('') : empty('Nenhum cliente em atenção', 'Os sinais aparecem aqui quando passam do limite.');
  $('recentMeetings').innerHTML = meetingTable(state.meetings.slice(0, 4));
}

function renderCustomers() {
  const query = $('customerSearch').value.trim().toLocaleLowerCase('pt-BR');
  const stage = $('customerStage').value;
  const customers = state.customers.filter(item => (!stage || item.stage === stage) && `${item.name} ${item.segment}`.toLocaleLowerCase('pt-BR').includes(query));
  $('customerList').innerHTML = customers.length ? customers.map(item => `<article class="card customer-card">${badge(stages[item.stage])}<h3>${esc(item.name)}</h3><p class="meta">${esc(item.segment || 'Sem segmento')} · ${esc(item.seller_name)}</p><div class="customer-stats"><div><strong>${item.meeting_count}</strong><small>reuniões</small></div><div><strong>${item.open_tasks}</strong><small>tarefas</small></div><div><strong>${item.latest_summary ? points(item.latest_summary.churn_risk_score) : '—'}</strong><small>risco</small></div></div><p class="small muted">${item.next_due ? `Próximo prazo: ${dateText(item.next_due)}` : 'Sem próximo contato.'}</p><div class="actions"><button data-customer="${item.id}">Abrir</button><button data-edit-customer="${item.id}" class="text-button">Editar</button></div></article>`).join('') : empty('Nenhum cliente', 'Cadastre um cliente ou ajuste a busca.');
}

function renderMeetings() {
  const query = $('meetingSearch').value.trim().toLocaleLowerCase('pt-BR');
  const risk = $('meetingRisk').value;
  $('meetingList').innerHTML = meetingTable(state.meetings.filter(item => (!risk || riskClass(item.summary.churn_risk_score) === risk) && `${item.title} ${item.customer_name} ${item.seller.name}`.toLocaleLowerCase('pt-BR').includes(query)));
}

function renderTasks() {
  const status = $('taskStatus').value;
  const query = $('taskSearch').value.trim().toLocaleLowerCase('pt-BR');
  $('taskList').innerHTML = taskRows(state.tasks.filter(task => (status === 'all' || (status === 'overdue' ? overdue(task) : task.status === status)) && `${task.title} ${task.customer_name} ${task.seller_name}`.toLocaleLowerCase('pt-BR').includes(query)));
}

function renderTeam() {
  if (state.user.role !== 'manager') return;
  $('teamList').innerHTML = state.users.map(user => `<article class="card customer-card">${badge(user.active ? 'Ativo' : 'Desativado', user.active ? 'done' : '')}<h3>${esc(user.name)}</h3><p class="meta">${esc(user.email)} · ${roleName(user.role)}</p><div class="customer-stats"><div><strong>${state.customers.filter(item => item.seller_id === user.id).length}</strong><small>clientes</small></div><div><strong>${state.tasks.filter(item => item.seller_id === user.id && item.status === 'open').length}</strong><small>tarefas</small></div></div>${user.id !== state.user.id ? `<button data-access-user="${user.id}">${user.active ? 'Desativar' : 'Reativar'}</button>` : '<p class="small muted">Sua conta</p>'}</article>`).join('');
}

function customerOptions(selected = '') {
  return '<option value="">Selecione</option>' + state.customers.map(item => `<option value="${item.id}" ${String(item.id) === String(selected) ? 'selected' : ''}>${esc(item.name)}${state.user.role === 'manager' ? ` · ${esc(item.seller_name)}` : ''}</option>`).join('');
}

function render() {
  renderOverview(); renderCustomers(); renderMeetings(); renderTasks(); renderTeam();
  const selected = $('uploadCustomer').value;
  $('uploadCustomer').innerHTML = customerOptions(selected);
}

function field(name, label, value = '', type = 'text', attributes = '') {
  return `<label for="field-${name}">${label}</label><input id="field-${name}" name="${name}" type="${type}" value="${esc(value)}" ${attributes}>`;
}

function select(name, label, options, selected) {
  return `<label for="field-${name}">${label}</label><select id="field-${name}" name="${name}" required>${Object.entries(options).map(([key, value]) => `<option value="${esc(key)}" ${String(selected) === key ? 'selected' : ''}>${esc(value)}</option>`).join('')}</select>`;
}

function notes(value = '') {
  return `<label for="field-notes">Notas (opcional)</label><textarea id="field-notes" name="notes" maxlength="4000">${esc(value)}</textarea>`;
}

function editEntity(title, fields, save, label = 'Salvar') {
  $('entityForm').reset();
  $('entityForm').querySelector('[data-form-error]').textContent = '';
  $('formTitle').textContent = title;
  $('entityFields').innerHTML = fields;
  $('entitySubmit').textContent = label;
  state.saveEntity = save;
  state.savedMessage = {
    'Cadastrar cliente': 'Cliente cadastrado.',
    'Editar cliente': 'Cliente atualizado.',
    'Criar tarefa': 'Tarefa criada.',
    'Editar tarefa': 'Tarefa atualizada.',
    'Cadastrar pessoa': 'Pessoa cadastrada na equipe.',
    'Desativar acesso': 'Acesso desativado.',
    'Reativar acesso': 'Acesso reativado.',
    'Editar título da reunião': 'Título atualizado.',
  }[title];
  $('formDialog').showModal();
}

function editCustomer(id) {
  const item = state.customers.find(customer => customer.id === Number(id));
  let fields = field('name', 'Nome do cliente', item?.name, 'text', 'required maxlength="120"') + field('segment', 'Segmento (opcional)', item?.segment, 'text', 'maxlength="100"') + select('stage', 'Etapa do atendimento', stages, item?.stage || 'active') + notes(item?.notes);
  if (!item && state.user.role === 'manager') fields += select('seller_id', 'Vendedor responsável', { '': 'Selecione', ...Object.fromEntries(state.sellers.map(seller => [seller.id, seller.name])) }, '');
  editEntity(item ? 'Editar cliente' : 'Cadastrar cliente', fields, async values => {
    if (values.seller_id) values.seller_id = Number(values.seller_id);
    await api(item ? `/customers/${item.id}` : '/customers', { method: item ? 'PATCH' : 'POST', body: JSON.stringify(values) });
  }, item ? 'Salvar cadastro' : 'Cadastrar cliente');
}

function editTask(id, customerId = '', meetingId = null, suggestion = '') {
  if (!state.customers.length) { notify('Cadastre um cliente primeiro.'); showPage('customers'); return; }
  const item = state.tasks.find(task => task.id === Number(id));
  let fields = item ? `<p class="muted">${esc(item.customer_name)} · ${esc(item.seller_name)}</p>` : `<label for="field-customer_id">Cliente</label><select id="field-customer_id" name="customer_id" required>${customerOptions(customerId)}</select>`;
  fields += field('title', 'Tarefa', item?.title || suggestion.slice(0, 160), 'text', 'required maxlength="160" placeholder="Ex.: Enviar proposta"') + field('due_date', 'Prazo', item?.due_date || today(), 'date', 'required') + select('priority', 'Prioridade', { normal: 'Normal', high: 'Alta' }, item?.priority || 'normal') + notes(item?.notes);
  if (item) fields += select('status', 'Situação', { open: 'Pendente', done: 'Concluída' }, item.status);
  editEntity(item ? 'Editar tarefa' : 'Criar tarefa', fields, async values => {
    if (!item) { values.customer_id = Number(values.customer_id); values.meeting_id = meetingId; }
    await api(item ? `/tasks/${item.id}` : '/tasks', { method: item ? 'PATCH' : 'POST', body: JSON.stringify(values) });
  }, item ? 'Salvar tarefa' : 'Criar tarefa');
}

function addUser() {
  const fields = field('name', 'Nome', '', 'text', 'required maxlength="120" autocomplete="name"') + field('email', 'E-mail', '', 'email', 'required maxlength="254" autocomplete="off"') + select('role', 'Perfil', { seller: 'Vendedor', manager: 'Gerente' }, 'seller') + field('password', 'Senha inicial', '', 'password', 'required minlength="15" maxlength="128" autocomplete="new-password"') + '<p class="hint">15 a 128 caracteres.</p>' + field('current_password', 'Sua senha', '', 'password', 'required autocomplete="current-password"');
  editEntity('Cadastrar pessoa', fields, values => api('/users', { method: 'POST', body: JSON.stringify(values) }), 'Cadastrar pessoa');
}

function changeAccess(id) {
  const user = state.users.find(item => item.id === Number(id));
  const action = user.active ? 'Desativar' : 'Reativar';
  editEntity(`${action} acesso`, `<p>${esc(user.name)} · ${esc(user.email)}</p><p class="muted">${user.active ? 'As sessões serão encerradas. O histórico será mantido.' : 'A senha atual continuará válida.'}</p>` + field('current_password', 'Sua senha', '', 'password', 'required autocomplete="current-password"'), values => api(`/users/${user.id}/access`, { method: 'PATCH', body: JSON.stringify({ ...values, active: !user.active }) }), `${action} acesso`);
}

function showDetail(title, html, descriptor) {
  state.detail = descriptor;
  $('detailTitle').textContent = title;
  $('detailBody').innerHTML = html;
  if (!$('detailDialog').open) $('detailDialog').showModal();
}

async function openCustomer(id) {
  const customer = await api(`/customers/${id}`);
  const history = [...customer.meetings].reverse();
  const delta = history.length >= 2 ? history.at(-1).summary.churn_risk_score - history.at(-2).summary.churn_risk_score : null;
  const trend = delta === null ? 'É preciso ter duas reuniões para comparar.' : `Variação de ${delta > 0 ? '+' : ''}${points(delta)} no risco. Use como referência.`;
  showDetail(customer.name, `<p class="muted">${esc(stages[customer.stage])} · ${esc(customer.seller_name)} · ${esc(customer.segment || 'Sem segmento')}</p><div class="actions"><button data-edit-customer="${id}">Editar</button><button data-customer-task="${id}" class="primary">Nova tarefa</button></div><div class="detail-block"><h3>Notas</h3><p style="white-space:pre-wrap">${esc(customer.notes || 'Sem notas.')}</p></div><div class="detail-block"><h3>Indicadores</h3><p class="small muted">${esc(trend)}</p>${history.length ? `<div class="table-scroll"><table><thead><tr><th>Data</th><th>Reunião</th><th>Risco</th><th>Expansão</th></tr></thead><tbody>${history.map(item => `<tr><td>${dateText(item.created_at)}</td><td><button data-meeting="${item.id}">${esc(item.title)}</button></td><td>${points(item.summary.churn_risk_score)}</td><td>${points(item.summary.opportunity_score)}</td></tr>`).join('')}</tbody></table></div>` : empty('Sem reuniões', 'Envie uma transcrição para iniciar o histórico.')}</div><div class="detail-block"><h3>Tarefas</h3>${taskRows(customer.tasks)}</div>`, { type: 'customer', id });
}

function explanation(summary) {
  const details = summary.score_explanation;
  if (!details) return '<p class="small muted">Detalhamento indisponível para esta reunião.</p>';
  return `<div class="table-scroll"><table class="breakdown"><thead><tr><th>Componente</th><th>Risco</th><th>Expansão</th></tr></thead><tbody><tr><td>Intenção × 45</td><td>${points(details.churn.intent_points)}</td><td>${points(details.opportunity.intent_points)}</td></tr><tr><td>Preço × 12</td><td>${points(details.churn.price_points)}</td><td>—</td></tr><tr><td>Sentimento × 80</td><td>${points(details.churn.sentiment_points)}</td><td>—</td></tr><tr><td>Produtos × 8</td><td>—</td><td>${points(details.opportunity.product_points)}</td></tr></tbody></table></div><p class="hint">Máximo de 100 pontos. ${details.customer_speeches} falas do cliente. ${esc(details.note)}</p>`;
}

async function openMeeting(id) {
  const item = await api(`/meetings/${id}`);
  const summary = item.analysis.summary;
  const html = `<p class="muted">${esc(item.customer_name)} · ${esc(item.seller.name)} · ${dateText(item.created_at)}</p><div class="actions no-print"><button data-meeting-task="${item.id}" class="primary">Nova tarefa</button><button data-rename-meeting="${item.id}">Editar título</button><button id="printReport">Salvar PDF</button></div><div class="detail-scores"><div><small>Risco</small><strong class="score ${riskClass(summary.churn_risk_score)}">${points(summary.churn_risk_score)}</strong></div><div><small>Expansão</small><strong>${points(summary.opportunity_score)}</strong></div><div><small>Sentimento</small><strong>${points(summary.sentiment_score)}</strong></div></div><p class="method-note">Indicadores por regras. Revise as falas antes de agir.</p><div class="recommendation"><strong>Próximo passo</strong><p>${esc(summary.recommended_action)}</p></div><h3>Cálculo</h3>${explanation(summary)}<div class="detail-block"><h3>Termos citados</h3><div class="tags">${[...summary.products_identified, ...summary.key_terms.map(item => item.term)].map(term => badge(term)).join('') || '<p class="muted">Nenhum termo.</p>'}</div><h3>Transcrição</h3>${item.analysis.message_analysis.map((message, index) => `<article class="message"><div class="message-header"><strong>${index + 1}. ${esc(message.speaker)}</strong>${badge(intents[message.intent] || message.intent)}</div><p>${esc(message.original_text)}</p><small class="muted">Confiança: ${Math.round(message.classification.confidence * 100)}%</small></article>`).join('')}</div><p class="print-only small">Torus · ${dateText(today())}</p>`;
  showDetail(item.title, html, { type: 'meeting', id, item });
}

async function submitForm(form, operation) {
  const errorElement = form.querySelector('[data-form-error]') || $('loginError');
  const submit = form.querySelector('[type="submit"]');
  errorElement.textContent = '';
  submit.disabled = true;
  try { await operation(); } catch (error) { errorElement.textContent = error.message; } finally { submit.disabled = false; }
}

$('loginForm').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    const result = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email: $('email').value, password: $('password').value }) });
    state.token = result.access_token;
    sessionStorage.setItem('torus_token', state.token);
    await enterApp();
    $('password').value = '';
  });
});
$('entityForm').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    await state.saveEntity(Object.fromEntries(new FormData(event.currentTarget)));
    $('formDialog').close();
    $('entityForm').reset();
    notify(state.savedMessage);
    await refresh();
    if ($('detailDialog').open && state.detail) {
      if (state.detail.type === 'customer') await openCustomer(state.detail.id);
      else await openMeeting(state.detail.id);
    }
  });
});
$('passwordForm').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    if ($('newPassword').value !== $('confirmPassword').value) throw new Error('As senhas não conferem.');
    await api('/auth/change-password', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
    $('passwordForm').reset();
    clearSession();
    notify('Senha alterada.');
  });
});
$('uploadForm').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    const file = $('meetingFile').files[0];
    if (!file || file.size > 1000000) throw new Error('Escolha um arquivo JSON com até 1 MB.');
    const result = await api('/analyze_meeting_file', { method: 'POST', body: new FormData(event.currentTarget) });
    $('uploadForm').reset();
    notify('Reunião analisada.');
    await refresh();
    await openMeeting(result.record_id);
  });
});

document.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  try {
    const data = button.dataset;
    if (data.page) showPage(data.page);
    else if (data.close) $(data.close).close();
    else if (data.demo) {
      $('email').value = data.demo === 'manager' ? 'manager@torus.ai' : 'ana@torus.ai';
      $('password').value = data.demo === 'manager' ? 'Torus@2026' : 'Vendas@2026';
    } else if (data.customer) await openCustomer(data.customer);
    else if (data.meeting) await openMeeting(data.meeting);
    else if (data.editCustomer) editCustomer(data.editCustomer);
    else if (data.task) editTask(data.task);
    else if (data.customerTask) editTask(null, data.customerTask);
    else if (data.meetingTask) {
      const item = state.detail.item;
      editTask(null, item.customer_id, item.id, item.summary.recommended_action);
    } else if (data.renameMeeting) {
      const item = state.detail.item;
      editEntity('Editar título da reunião', field('title', 'Título', item.title, 'text', 'required maxlength="120"'), values => api(`/meetings/${item.id}`, { method: 'PATCH', body: JSON.stringify(values) }), 'Salvar título');
    } else if (data.accessUser) changeAccess(data.accessUser);
    else if (button.id === 'newCustomer') editCustomer();
    else if (button.id === 'newTask') editTask();
    else if (button.id === 'newUser') addUser();
    else if (button.id === 'printReport') window.print();
    else if (button.id === 'refreshButton') { button.disabled = true; await refresh(); notify('Dados atualizados.'); }
    else if (button.id === 'logoutButton') { try { await api('/auth/logout', { method: 'POST' }); } finally { clearSession(); } }
    else if (button.id === 'showPassword') {
      const show = $('password').type === 'password';
      $('password').type = show ? 'text' : 'password';
      button.textContent = show ? 'Ocultar' : 'Mostrar';
      button.setAttribute('aria-label', `${show ? 'Ocultar' : 'Mostrar'} senha`);
    } else if (button.id === 'mobileMenu') {
      const open = $('sidebar').classList.toggle('open');
      button.setAttribute('aria-expanded', String(open));
      updateSidebarAccess();
    } else if (button.id === 'exportMeetings') {
      const blob = await api('/reports/meetings.csv', { download: true });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'torus-reunioes.csv'; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify('Exportação pronta.');
    }
  } catch (error) { report(error); } finally { button.disabled = false; }
});

for (const id of ['customerSearch', 'customerStage']) $(id).addEventListener('input', renderCustomers);
for (const id of ['meetingSearch', 'meetingRisk']) $(id).addEventListener('input', renderMeetings);
for (const id of ['taskStatus', 'taskSearch']) $(id).addEventListener('input', renderTasks);
$('formDialog').addEventListener('close', () => { $('entityForm').reset(); });

if (state.token) enterApp().catch(error => { clearSession(); report(error); });
