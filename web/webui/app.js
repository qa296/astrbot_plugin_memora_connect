const state = {
  group: "",
  token: "",
  concepts: [],
  selectedConceptId: null,
  selectedPerson: null,
};

function headers() {
  const h = {"Content-Type": "application/json"};
  if (state.token) h["x-access-token"] = state.token;
  return h;
}

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, {headers: headers(), ...opts});
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function qs(sel) { return document.querySelector(sel); }

async function loadGroups() {
  const data = await fetchJson(`/api/groups`);
  const sel = qs('#groupSelect');
  sel.innerHTML = '';
  for (const g of data.groups) {
    const opt = document.createElement('option');
    opt.value = g;
    opt.textContent = g || '(默认/私聊)';
    sel.appendChild(opt);
  }
  sel.value = state.group;
}

async function loadGraph() {
  const data = await fetchJson(`/api/graph?group_id=${encodeURIComponent(state.group)}`);
  const nodes = data.nodes.map(n => ({ data: { id: n.id, label: `${n.name}(${n.count})` } }));
  const edges = data.edges.map(e => ({ data: { id: `${e.from_concept}_${e.to_concept}`, source: e.from_concept, target: e.to_concept, weight: e.strength } }));
  const cy = cytoscape({
    container: document.getElementById('graph'),
    elements: { nodes, edges },
    style: [
      { selector: 'node', style: { 'label': 'data(label)', 'background-color': '#64b5f6', 'font-size': 10 } },
      { selector: 'edge', style: { 'width': 2, 'line-color': '#bbb' } },
    ],
    layout: { name: 'cose', fit: true }
  });
  cy.on('tap', 'node', (evt) => {
    const id = evt.target.id();
    state.selectedConceptId = id;
    render();
    loadMemories();
  });
}

async function loadConcepts() {
  const data = await fetchJson(`/api/concepts?group_id=${encodeURIComponent(state.group)}`);
  state.concepts = data.concepts || [];
  render();
}

async function loadMemories() {
  const params = new URLSearchParams();
  params.set('group_id', state.group);
  if (state.selectedConceptId) params.set('concept_id', state.selectedConceptId);
  const data = await fetchJson(`/api/memories?${params}`);
  const list = qs('#memoryList');
  list.innerHTML = '';
  for (const m of data.memories) {
    const el = document.createElement('div');
    el.className = 'item';
    const left = document.createElement('div');
    left.innerHTML = `<div>${m.content}</div><small>强度:${m.strength?.toFixed?.(2) ?? m.strength} 概念:${m.concept_id}</small>`;
    const act = document.createElement('div');
    act.className = 'actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'small';
    editBtn.textContent = '编辑';
    editBtn.onclick = async () => {
      const content = prompt('内容', m.content);
      if (content == null) return;
      await fetchJson(`/api/memories/${m.id}`, {method: 'PUT', body: JSON.stringify({group_id: state.group, content})});
      loadMemories();
    };
    const strengthBtn = document.createElement('button');
    strengthBtn.className = 'small';
    strengthBtn.textContent = '强度';
    strengthBtn.onclick = async () => {
      const s = prompt('强度(0-1)', m.strength);
      if (s == null) return;
      await fetchJson(`/api/memories/${m.id}`, {method: 'PUT', body: JSON.stringify({group_id: state.group, strength: parseFloat(s)})});
      loadMemories();
    };
    const delBtn = document.createElement('button');
    delBtn.className = 'small danger';
    delBtn.textContent = '删除';
    delBtn.onclick = async () => {
      if (!confirm('确认删除?')) return;
      await fetchJson(`/api/memories/${m.id}?group_id=${encodeURIComponent(state.group)}`, {method: 'DELETE'});
      loadMemories();
    };

    act.appendChild(editBtn);
    act.appendChild(strengthBtn);
    act.appendChild(delBtn);
    el.appendChild(left);
    el.appendChild(act);
    list.appendChild(el);
  }
}

async function loadConnections() {
  const data = await fetchJson(`/api/connections?group_id=${encodeURIComponent(state.group)}`);
  const list = qs('#connList');
  list.innerHTML = '';
  for (const c of data.connections) {
    const el = document.createElement('div');
    el.className = 'item';
    const left = document.createElement('div');
    left.innerHTML = `<div>${c.from_concept} -> ${c.to_concept}</div><small>强度:${c.strength.toFixed?.(2) ?? c.strength}</small>`;
    const act = document.createElement('div');
    act.className = 'actions';
    const sBtn = document.createElement('button'); sBtn.className='small'; sBtn.textContent='强度';
    sBtn.onclick = async () => {
      const s = prompt('强度(0-1)', c.strength);
      if (s == null) return;
      await fetchJson(`/api/connections/${c.id}`, {method:'PUT', body: JSON.stringify({group_id: state.group, strength: parseFloat(s)})});
      loadConnections();
    };
    const dBtn = document.createElement('button'); dBtn.className='small danger'; dBtn.textContent='删除';
    dBtn.onclick = async () => {
      if (!confirm('确认删除?')) return;
      await fetchJson(`/api/connections/${c.id}?group_id=${encodeURIComponent(state.group)}`, {method:'DELETE'});
      loadConnections();
    };
    act.appendChild(sBtn); act.appendChild(dBtn);
    el.appendChild(left); el.appendChild(act);
    list.appendChild(el);
  }
}

async function loadImpressions() {
  const data = await fetchJson(`/api/impressions?group_id=${encodeURIComponent(state.group)}`);
  const list = qs('#impList');
  list.innerHTML = '';
  const people = data.people || [];
  for (const p of people) {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `<div>${p.name}</div>`;
    el.onclick = () => loadImpressionDetail(p.name);
    list.appendChild(el);
  }
  // 如果当前选中人物已不在列表中，则清空详情
  if (state.selectedPerson && !people.some(x => x.name === state.selectedPerson)) {
    state.selectedPerson = null;
    const detailEl = qs('#impDetail');
    if (detailEl) detailEl.innerHTML = '';
  }
}

async function loadImpressionDetail(person) {
  state.selectedPerson = person;
  const params = new URLSearchParams();
  params.set('group_id', state.group);
  params.set('person', person);
  const data = await fetchJson(`/api/impressions?${params}`);
  const detail = qs('#impDetail');
  if (!detail) return;

  const summary = data.summary || {};
  const memories = data.memories || [];

  if (!summary.name && !summary.summary && !memories.length) {
    detail.innerHTML = '<div>暂无印象数据</div>';
    return;
  }

  const scoreVal = typeof summary.score === 'number' ? summary.score.toFixed(2) : (summary.score ?? '');
  const headerHtml = `<h4>${summary.name || person}（好感度: ${scoreVal || '未知'}）</h4>`;
  const infoHtml = `<div>${summary.summary || ''}</div><small>记录数: ${summary.memory_count ?? memories.length}，最后更新: ${summary.last_updated || ''}</small>`;

  let memHtml = '';
  if (memories.length) {
    memHtml = '<ul>' + memories.map(m => {
      const s = m.score?.toFixed?.(2) ?? m.score;
      const t = m.last_accessed || '';
      const d = m.details ? ` — ${m.details}` : '';
      return `<li>${m.content}${d}<small> 分数:${s ?? ''} 时间:${t}</small></li>`;
    }).join('') + '</ul>';
  }

  detail.innerHTML = headerHtml + infoHtml + memHtml;
}

async function searchMemories() {
  const list = qs('#memSearchList');
  if (!list) return;
  const q = qs('#memSearchQuery').value.trim();
  list.innerHTML = '';
  if (!q) return;

  const params = new URLSearchParams();
  params.set('group_id', state.group);
  params.set('q', q);
  const data = await fetchJson(`/api/memories?${params}`);
  const memories = data.memories || [];

  for (const m of memories) {
    const el = document.createElement('div');
    el.className = 'item';
    const left = document.createElement('div');
    const concept = state.concepts.find(c => c.id === m.concept_id);
    const conceptName = concept ? concept.name : m.concept_id;
    left.innerHTML = `<div>${m.content}</div><small>概念:${conceptName} 强度:${m.strength?.toFixed?.(2) ?? m.strength}</small>`;
    const act = document.createElement('div');
    act.className = 'actions';

    const gotoBtn = document.createElement('button');
    gotoBtn.className = 'small';
    gotoBtn.textContent = '查看';
    gotoBtn.onclick = () => {
      state.selectedConceptId = m.concept_id;
      render();
      loadMemories();
    };

    act.appendChild(gotoBtn);
    el.appendChild(left);
    el.appendChild(act);
    list.appendChild(el);
  }
}

function renderConcepts() {
  const list = qs('#conceptList');
  list.innerHTML = '';
  for (const c of state.concepts) {
    const el = document.createElement('div');
    el.className = 'item';
    const left = document.createElement('div');
    left.innerHTML = `<div>${c.name}</div><small>${c.id}</small>`;
    const act = document.createElement('div');
    act.className = 'actions';
    const useBtn = document.createElement('button'); useBtn.className='small'; useBtn.textContent='选中';
    useBtn.onclick = () => { state.selectedConceptId = c.id; render(); loadMemories(); };
    const renameBtn = document.createElement('button'); renameBtn.className='small'; renameBtn.textContent='重命名';
    renameBtn.onclick = async () => {
      const name = prompt('新名称', c.name);
      if (name == null) return;
      await fetchJson(`/api/concepts/${c.id}`, {method:'PUT', body: JSON.stringify({group_id: state.group, name})});
      loadConcepts();
    };
    const delBtn = document.createElement('button'); delBtn.className='small danger'; delBtn.textContent='删除';
    delBtn.onclick = async () => {
      if (!confirm('确认删除概念及其记忆?')) return;
      await fetchJson(`/api/concepts/${c.id}?group_id=${encodeURIComponent(state.group)}`, {method:'DELETE'});
      loadConcepts(); loadMemories(); loadGraph();
    };
    act.appendChild(useBtn); act.appendChild(renameBtn); act.appendChild(delBtn);
    el.appendChild(left); el.appendChild(act);
    list.appendChild(el);
  }
}

function render() {
  renderConcepts();
}

async function main() {
  state.token = qs('#tokenInput').value.trim();
  await loadGroups();
  await loadConcepts();
  await loadGraph();
  await loadConnections();
  await loadImpressions();
}

window.addEventListener('DOMContentLoaded', () => {
  const groupSel = qs('#groupSelect');
  groupSel.addEventListener('change', () => { state.group = groupSel.value; main(); });
  qs('#tokenInput').addEventListener('change', () => { state.token = qs('#tokenInput').value.trim(); main(); });
  qs('#refreshBtn').addEventListener('click', () => main());

  qs('#addConceptBtn').addEventListener('click', async () => {
    const name = qs('#newConceptName').value.trim();
    if (!name) return;
    await fetchJson('/api/concepts', {method:'POST', body: JSON.stringify({group_id: state.group, name})});
    qs('#newConceptName').value = '';
    await loadConcepts(); await loadGraph();
  });

  qs('#addMemoryBtn').addEventListener('click', async () => {
    if (!state.selectedConceptId) { alert('请先在左侧选择一个概念'); return; }
    const body = {
      group_id: state.group,
      concept_id: state.selectedConceptId,
      content: qs('#memContent').value,
      details: qs('#memDetails').value,
      participants: qs('#memParticipants').value,
      tags: qs('#memTags').value,
      emotion: qs('#memEmotion').value,
      location: qs('#memLocation').value,
      strength: parseFloat(qs('#memStrength').value || '1')
    };
    if (!body.content) return;
    await fetchJson('/api/memories', {method:'POST', body: JSON.stringify(body)});
    ['#memContent','#memDetails','#memParticipants','#memTags','#memEmotion','#memLocation','#memStrength'].forEach(id=>qs(id).value='');
    await loadMemories(); await loadGraph();
  });

  qs('#addConnBtn').addEventListener('click', async () => {
    const body = {
      group_id: state.group,
      from_concept: qs('#connFrom').value.trim(),
      to_concept: qs('#connTo').value.trim(),
      strength: parseFloat(qs('#connStrength').value || '1')
    };
    if (!body.from_concept || !body.to_concept) return;
    await fetchJson('/api/connections', {method:'POST', body: JSON.stringify(body)});
    ['#connFrom','#connTo','#connStrength'].forEach(id=>qs(id).value='');
    await loadConnections(); await loadGraph();
  });

  qs('#addImpBtn').addEventListener('click', async () => {
    const body = {
      group_id: state.group,
      person: qs('#impPerson').value.trim(),
      summary: qs('#impSummary').value.trim(),
      score: parseFloat(qs('#impScore').value || ''),
      details: qs('#impDetails').value.trim()
    };
    if (!body.person || !body.summary) return;
    await fetchJson('/api/impressions', {method:'POST', body: JSON.stringify(body)});
    ['#impPerson','#impSummary','#impScore','#impDetails'].forEach(id=>qs(id).value='');
    await loadImpressions(); await loadGraph();
  });

  const searchBtn = qs('#memSearchBtn');
  if (searchBtn) searchBtn.addEventListener('click', () => { searchMemories(); });
  const searchInput = qs('#memSearchQuery');
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchMemories();
    });
  }
  const clearBtn = qs('#memSearchClearBtn');
  if (clearBtn) clearBtn.addEventListener('click', () => {
    const input = qs('#memSearchQuery');
    if (input) input.value = '';
    const list = qs('#memSearchList');
    if (list) list.innerHTML = '';
  });

  const adjustBtn = qs('#impAdjustBtn');
  if (adjustBtn) adjustBtn.addEventListener('click', async () => {
    const deltaInput = qs('#impDelta');
    if (!deltaInput) return;
    const deltaStr = deltaInput.value.trim();
    if (!deltaStr) return;
    if (!state.selectedPerson) {
      alert('请先在下方列表中选择一个人物');
      return;
    }
    const delta = parseFloat(deltaStr);
    if (Number.isNaN(delta)) return;
    await fetchJson(`/api/impressions/${encodeURIComponent(state.selectedPerson)}/score`, {
      method: 'PUT',
      body: JSON.stringify({ group_id: state.group, delta }),
    });
    deltaInput.value = '';
    await loadImpressionDetail(state.selectedPerson);
    await loadImpressions();
    await loadGraph();
  });

  main();
});
