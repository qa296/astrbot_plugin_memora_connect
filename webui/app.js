const state = {
  group: "",
  token: "",
  concepts: [],
  selectedConceptId: null,
  selectedPerson: null,
  cy: null,
};

function headers() {
  const h = {"Content-Type": "application/json"};
  if (state.token) h["x-access-token"] = state.token;
  return h;
}

function showToast(msg, type = 'info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  if (type === 'error') el.style.background = 'rgba(255, 59, 48, 0.9)';
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

async function fetchJson(url, opts = {}) {
  try {
    const res = await fetch(url, {headers: headers(), ...opts});
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  } catch (e) {
    showToast(e.message, 'error');
    throw e;
  }
}

function qs(sel) { return document.querySelector(sel); }

async function loadGroups() {
  try {
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
  } catch (e) {
    console.error("Failed to load groups", e);
  }
}

async function loadGraph() {
  const data = await fetchJson(`/api/graph?group_id=${encodeURIComponent(state.group)}`);
  
  // Theme colors
  const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary').trim();
  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim();

  const nodes = data.nodes.map(n => ({ 
    data: { 
      id: n.id, 
      label: n.name,
      count: n.count
    } 
  }));
  
  const edges = data.edges.map(e => ({ 
    data: { 
      id: `${e.from_concept}_${e.to_concept}`, 
      source: e.from_concept, 
      target: e.to_concept, 
      weight: e.strength 
    } 
  }));

  if (state.cy) {
    state.cy.destroy();
  }

  state.cy = cytoscape({
    container: document.getElementById('graph'),
    elements: { nodes, edges },
    style: [
      { 
        selector: 'node', 
        style: { 
          'label': 'data(label)',
          'background-color': '#fff',
          'border-width': 2,
          'border-color': primaryColor,
          'color': textColor,
          'font-size': 12,
          'text-valign': 'center',
          'text-halign': 'center',
          'width': 'mapData(count, 0, 20, 30, 60)',
          'height': 'mapData(count, 0, 20, 30, 60)',
          'font-weight': 'bold',
          'shadow-blur': 10,
          'shadow-color': 'rgba(0,0,0,0.1)',
          'shadow-opacity': 0.5
        } 
      },
      { 
        selector: 'node:selected', 
        style: { 
          'background-color': primaryColor,
          'color': '#fff',
          'border-color': '#fff',
          'border-width': 3
        } 
      },
      { 
        selector: 'edge', 
        style: { 
          'width': 'mapData(weight, 0, 1, 1, 4)', 
          'line-color': '#ccc',
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'target-arrow-color': '#ccc'
        } 
      },
    ],
    layout: { 
      name: 'cose', 
      animate: true,
      randomize: false, 
      componentSpacing: 100,
      nodeRepulsion: 400000,
      edgeElasticity: 100,
      nestingFactor: 5,
    }
  });

  state.cy.on('tap', 'node', (evt) => {
    const id = evt.target.id();
    state.selectedConceptId = id;
    render();
    loadMemories();
  });
}

async function loadConcepts() {
  const data = await fetchJson(`/api/concepts?group_id=${encodeURIComponent(state.group)}`);
  state.concepts = data.concepts || [];
  renderConcepts();
}

function renderConcepts() {
  const list = qs('#conceptList');
  list.innerHTML = '';
  for (const c of state.concepts) {
    const el = document.createElement('div');
    el.className = `item ${c.id === state.selectedConceptId ? 'active' : ''}`;
    
    const header = document.createElement('div');
    header.className = 'item-header';
    header.innerHTML = `<span class="item-title">${c.name}</span><span class="item-meta">ID: ${c.id}</span>`;
    
    const actions = document.createElement('div');
    actions.className = 'item-actions';
    
    const useBtn = document.createElement('button'); 
    useBtn.textContent = '选中';
    useBtn.onclick = (e) => { 
      e.stopPropagation();
      state.selectedConceptId = c.id; 
      renderConcepts(); 
      loadMemories(); 
      if (state.cy) {
        state.cy.$(`#${c.id}`).select();
      }
    };
    
    const renameBtn = document.createElement('button'); 
    renameBtn.textContent = '重命名';
    renameBtn.onclick = async (e) => {
      e.stopPropagation();
      const name = prompt('新名称', c.name);
      if (name == null) return;
      await fetchJson(`/api/concepts/${c.id}`, {method:'PUT', body: JSON.stringify({group_id: state.group, name})});
      showToast('重命名成功');
      loadConcepts();
    };
    
    const delBtn = document.createElement('button'); 
    delBtn.className = 'danger';
    delBtn.textContent = '删除';
    delBtn.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm('确认删除概念及其记忆?')) return;
      await fetchJson(`/api/concepts/${c.id}?group_id=${encodeURIComponent(state.group)}`, {method:'DELETE'});
      showToast('删除成功');
      if (state.selectedConceptId === c.id) state.selectedConceptId = null;
      loadConcepts(); loadMemories(); loadGraph();
    };
    
    actions.append(useBtn, renameBtn, delBtn);
    el.append(header, actions);
    el.onclick = () => useBtn.click();
    
    list.appendChild(el);
  }
}

async function loadMemories() {
  const params = new URLSearchParams();
  params.set('group_id', state.group);
  if (state.selectedConceptId) params.set('concept_id', state.selectedConceptId);
  
  const data = await fetchJson(`/api/memories?${params}`);
  const list = qs('#memoryList');
  list.innerHTML = '';
  
  if (!state.selectedConceptId) {
    list.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-secondary);">请在左侧选择一个概念以查看记忆</div>';
    return;
  }
  
  if (data.memories.length === 0) {
    list.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-secondary);">暂无记忆</div>';
    return;
  }

  for (const m of data.memories) {
    const el = document.createElement('div');
    el.className = 'item';
    
    const content = document.createElement('div');
    content.className = 'item-title';
    content.textContent = m.content;
    
    const meta = document.createElement('div');
    meta.className = 'item-meta';
    meta.innerHTML = `强度: ${m.strength?.toFixed?.(2) ?? m.strength} | ${m.details || '无细节'}`;
    
    const actions = document.createElement('div');
    actions.className = 'item-actions';

    const editBtn = document.createElement('button');
    editBtn.textContent = '编辑';
    editBtn.onclick = async () => {
      const content = prompt('内容', m.content);
      if (content == null) return;
      await fetchJson(`/api/memories/${m.id}`, {method: 'PUT', body: JSON.stringify({group_id: state.group, content})});
      showToast('更新成功');
      loadMemories();
    };
    
    const strengthBtn = document.createElement('button');
    strengthBtn.textContent = '强度';
    strengthBtn.onclick = async () => {
      const s = prompt('强度(0-1)', m.strength);
      if (s == null) return;
      await fetchJson(`/api/memories/${m.id}`, {method: 'PUT', body: JSON.stringify({group_id: state.group, strength: parseFloat(s)})});
      loadMemories();
    };
    
    const delBtn = document.createElement('button');
    delBtn.className = 'danger';
    delBtn.textContent = '删除';
    delBtn.onclick = async () => {
      if (!confirm('确认删除?')) return;
      await fetchJson(`/api/memories/${m.id}?group_id=${encodeURIComponent(state.group)}`, {method: 'DELETE'});
      showToast('删除成功');
      loadMemories();
    };

    actions.append(editBtn, strengthBtn, delBtn);
    el.append(content, meta, actions);
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
    
    const header = document.createElement('div');
    header.className = 'item-header';
    header.innerHTML = `<span class="item-title">${c.from_concept} → ${c.to_concept}</span>`;
    
    const meta = document.createElement('div');
    meta.className = 'item-meta';
    meta.textContent = `强度: ${c.strength.toFixed?.(2) ?? c.strength}`;

    const actions = document.createElement('div');
    actions.className = 'item-actions';
    
    const sBtn = document.createElement('button'); sBtn.textContent='强度';
    sBtn.onclick = async () => {
      const s = prompt('强度(0-1)', c.strength);
      if (s == null) return;
      await fetchJson(`/api/connections/${c.id}`, {method:'PUT', body: JSON.stringify({group_id: state.group, strength: parseFloat(s)})});
      loadConnections();
    };
    
    const dBtn = document.createElement('button'); dBtn.className='danger'; dBtn.textContent='删除';
    dBtn.onclick = async () => {
      if (!confirm('确认删除?')) return;
      await fetchJson(`/api/connections/${c.id}?group_id=${encodeURIComponent(state.group)}`, {method:'DELETE'});
      loadConnections();
    };
    
    actions.append(sBtn, dBtn);
    el.append(header, meta, actions);
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
    el.className = `item ${state.selectedPerson === p.name ? 'active' : ''}`;
    el.innerHTML = `<div class="item-title">${p.name}</div>`;
    el.onclick = () => loadImpressionDetail(p.name);
    list.appendChild(el);
  }
  
  if (state.selectedPerson && !people.some(x => x.name === state.selectedPerson)) {
    state.selectedPerson = null;
    const detailEl = qs('#impDetail');
    if (detailEl) {
      detailEl.innerHTML = '';
      detailEl.style.display = 'none';
    }
  }
}

async function loadImpressionDetail(person) {
  state.selectedPerson = person;
  // Update list selection UI
  loadImpressions(); 
  
  const params = new URLSearchParams();
  params.set('group_id', state.group);
  params.set('person', person);
  const data = await fetchJson(`/api/impressions?${params}`);
  const detail = qs('#impDetail');
  if (!detail) return;
  
  detail.style.display = 'block';

  const summary = data.summary || {};
  const memories = data.memories || [];

  if (!summary.name && !summary.summary && !memories.length) {
    detail.innerHTML = '<div style="padding:10px;">暂无印象数据</div>';
    return;
  }

  const scoreVal = typeof summary.score === 'number' ? summary.score.toFixed(2) : (summary.score ?? '');
  const headerHtml = `<h4 style="margin-top:0;">${summary.name || person} <span style="font-weight:normal; font-size:12px; color:var(--text-secondary)">好感度: ${scoreVal || '未知'}</span></h4>`;
  const infoHtml = `<div style="margin-bottom:8px;">${summary.summary || ''}</div><div class="item-meta">记录数: ${summary.memory_count ?? memories.length}，更新: ${summary.last_updated || ''}</div>`;

  let memHtml = '';
  if (memories.length) {
    memHtml = '<ul style="padding-left:20px; margin:8px 0;">' + memories.map(m => {
      const s = m.score?.toFixed?.(2) ?? m.score;
      const t = m.last_accessed || '';
      const d = m.details ? ` — ${m.details}` : '';
      return `<li style="margin-bottom:4px; font-size:13px;">${m.content}${d}<br><span class="item-meta">分数:${s ?? ''} 时间:${t}</span></li>`;
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
    
    const concept = state.concepts.find(c => c.id === m.concept_id);
    const conceptName = concept ? concept.name : m.concept_id;
    
    el.innerHTML = `
      <div class="item-title">${m.content}</div>
      <div class="item-meta">概念: ${conceptName} | 强度: ${m.strength?.toFixed?.(2) ?? m.strength}</div>
      <div class="item-actions">
        <button class="small" onclick="state.selectedConceptId='${m.concept_id}'; render(); loadMemories();">查看</button>
      </div>
    `;
    list.appendChild(el);
  }
}

function render() {
  renderConcepts();
}

async function main() {
  state.token = qs('#tokenInput').value.trim();
  // Using Promise.all for parallel loading
  await Promise.all([
    loadGroups(),
    loadConcepts(),
    loadGraph(),
    loadConnections(),
    loadImpressions()
  ]);
}

window.addEventListener('DOMContentLoaded', () => {
  const groupSel = qs('#groupSelect');
  groupSel.addEventListener('change', () => { state.group = groupSel.value; main(); });
  qs('#tokenInput').addEventListener('change', () => { state.token = qs('#tokenInput').value.trim(); main(); });
  qs('#refreshBtn').addEventListener('click', () => { showToast('Refreshing...'); main(); });

  qs('#addConceptBtn').addEventListener('click', async () => {
    const name = qs('#newConceptName').value.trim();
    if (!name) return;
    await fetchJson('/api/concepts', {method:'POST', body: JSON.stringify({group_id: state.group, name})});
    qs('#newConceptName').value = '';
    showToast('概念已添加');
    await loadConcepts(); await loadGraph();
  });

  qs('#addMemoryBtn').addEventListener('click', async () => {
    if (!state.selectedConceptId) { showToast('请先在左侧选择一个概念', 'error'); return; }
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
    showToast('记忆已添加');
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
    showToast('连接已建立');
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
    showToast('印象已记录');
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
      showToast('请先选择一个人物', 'error');
      return;
    }
    const delta = parseFloat(deltaStr);
    if (Number.isNaN(delta)) return;
    await fetchJson(`/api/impressions/${encodeURIComponent(state.selectedPerson)}/score`, {
      method: 'PUT',
      body: JSON.stringify({ group_id: state.group, delta }),
    });
    deltaInput.value = '';
    showToast('好感度已调整');
    await loadImpressionDetail(state.selectedPerson);
    await loadImpressions();
    await loadGraph();
  });

  main();
});
