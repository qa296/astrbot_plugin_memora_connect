const state = {
  group: "",
  token: "",
  concepts: [],
  selectedConceptId: null,
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
    const relType = c.relation_type ? ` | 类型:${c.relation_type}` : '';
    left.innerHTML = `<div>${c.from_concept} -> ${c.to_concept}</div><small>强度:${c.strength.toFixed?.(2) ?? c.strength}${relType}</small>`;
    const act = document.createElement('div');
    act.className = 'actions';
    const sBtn = document.createElement('button'); sBtn.className='small'; sBtn.textContent='强度';
    sBtn.onclick = async () => {
      const s = prompt('强度(0-1)', c.strength);
      if (s == null) return;
      await fetchJson(`/api/connections/${c.id}`, {method:'PUT', body: JSON.stringify({group_id: state.group, strength: parseFloat(s)})});
      loadConnections();
    };
    const rtBtn = document.createElement('button'); rtBtn.className='small'; rtBtn.textContent='关系';
    rtBtn.onclick = async () => {
      const rt = prompt('关系类型', c.relation_type || '');
      if (rt == null) return;
      await fetchJson(`/api/connections/${c.id}`, {method:'PUT', body: JSON.stringify({group_id: state.group, relation_type: rt})});
      loadConnections();
    };
    const dBtn = document.createElement('button'); dBtn.className='small danger'; dBtn.textContent='删除';
    dBtn.onclick = async () => {
      if (!confirm('确认删除?')) return;
      await fetchJson(`/api/connections/${c.id}?group_id=${encodeURIComponent(state.group)}`, {method:'DELETE'});
      loadConnections();
    };
    act.appendChild(sBtn); act.appendChild(rtBtn); act.appendChild(dBtn);
    el.appendChild(left); el.appendChild(act);
    list.appendChild(el);
  }
}

async function loadImpressions() {
  const data = await fetchJson(`/api/impressions?group_id=${encodeURIComponent(state.group)}`);
  const list = qs('#impList');
  list.innerHTML = '';
  for (const p of (data.people||[])) {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `<div>${p.name}</div>`;
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
    const attrs = [];
    if (c.importance !== undefined) attrs.push(`重要性:${c.importance.toFixed?.(2) ?? c.importance}`);
    if (c.abstractness !== undefined) attrs.push(`抽象性:${c.abstractness.toFixed?.(2) ?? c.abstractness}`);
    const attrStr = attrs.length > 0 ? ` | ${attrs.join(' ')}` : '';
    left.innerHTML = `<div>${c.name}</div><small>${c.id}${attrStr}</small>`;
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

async function loadEmotions() {
  const userId = qs('#emotionUser').value.trim();
  if (!userId) return;
  
  try {
    const data = await fetchJson(`/api/emotions?group_id=${encodeURIComponent(state.group)}&user_id=${encodeURIComponent(userId)}`);
    const list = qs('#emotionList');
    list.innerHTML = '';
    
    if (data.profile) {
      const el = document.createElement('div');
      el.className = 'item';
      const emotions = data.profile.emotions || {};
      const emotionItems = Object.entries(emotions).map(([k, v]) => `${k}:${v.toFixed?.(2) ?? v}`).join(' | ');
      el.innerHTML = `<div>${userId} 的情感档案</div><small>${emotionItems}</small>`;
      list.appendChild(el);
    } else {
      const el = document.createElement('div');
      el.className = 'item';
      el.innerHTML = `<div>未找到 ${userId} 的情感档案</div>`;
      list.appendChild(el);
    }
  } catch (e) {
    const list = qs('#emotionList');
    list.innerHTML = '<div class="item"><div>查询失败</div></div>';
  }
}

async function loadRelations() {
  const conceptId = qs('#relationConcept').value.trim();
  if (!conceptId) return;
  
  try {
    const data = await fetchJson(`/api/relations?group_id=${encodeURIComponent(state.group)}&concept_id=${encodeURIComponent(conceptId)}`);
    const list = qs('#relationList');
    list.innerHTML = '';
    
    if (data.relations && data.relations.length > 0) {
      for (const rel of data.relations) {
        const el = document.createElement('div');
        el.className = 'item';
        const relType = rel.relation_type || '未分类';
        el.innerHTML = `<div>${rel.from_concept} → ${rel.to_concept}</div><small>类型:${relType} | 强度:${rel.strength.toFixed?.(2) ?? rel.strength}</small>`;
        list.appendChild(el);
      }
    } else {
      const el = document.createElement('div');
      el.className = 'item';
      el.innerHTML = `<div>未找到与 ${conceptId} 相关的连接</div>`;
      list.appendChild(el);
    }
  } catch (e) {
    const list = qs('#relationList');
    list.innerHTML = '<div class="item"><div>查询失败</div></div>';
  }
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
      strength: parseFloat(qs('#connStrength').value || '1'),
      relation_type: qs('#connRelationType').value.trim()
    };
    if (!body.from_concept || !body.to_concept) return;
    await fetchJson('/api/connections', {method:'POST', body: JSON.stringify(body)});
    ['#connFrom','#connTo','#connStrength','#connRelationType'].forEach(id=>qs(id).value='');
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

  qs('#getEmotionBtn').addEventListener('click', async () => {
    await loadEmotions();
  });

  qs('#getRelationBtn').addEventListener('click', async () => {
    await loadRelations();
  });

  main();
});
