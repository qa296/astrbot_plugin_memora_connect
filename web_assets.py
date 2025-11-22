"""默认的 Memora Web 前端静态资源。

当插件在打包或部署时遗漏了 webui 目录中的文件时，
web_server 会使用这里的内容在运行目录下自动生成
index.html、style.css 和 app.js，以保证 Web 管理界面可用。
"""

DEFAULT_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memora Connect Web</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
</head>
<body>
  <header>
    <h1>Memora Connect Web</h1>
    <div class="toolbar">
      <label>访问令牌: <input type="password" id="tokenInput" placeholder="如果配置了 access_token 则需填写"></label>
      <label>群组: <select id="groupSelect"></select></label>
      <button id="refreshBtn">刷新</button>
    </div>
  </header>

  <main>
    <section class="panel">
      <h2>记忆图谱</h2>
      <div id="graph"></div>
    </section>
    <section class="panel">
      <h2>概念与记忆</h2>
      <div class="two-col">
        <div>
          <h3>概念</h3>
          <div class="list" id="conceptList"></div>
          <div class="form">
            <input type="text" id="newConceptName" placeholder="新概念名称">
            <button id="addConceptBtn">添加概念</button>
          </div>
        </div>
        <div>
          <h3>记忆</h3>
          <div class="form">
            <input type="text" id="memContent" placeholder="内容">
            <input type="text" id="memDetails" placeholder="细节">
            <input type="text" id="memParticipants" placeholder="参与者">
            <input type="text" id="memTags" placeholder="标签">
            <input type="text" id="memEmotion" placeholder="情感">
            <input type="text" id="memLocation" placeholder="地点">
            <input type="number" id="memStrength" placeholder="强度(0-1)" step="0.1" min="0" max="1">
            <button id="addMemoryBtn">添加记忆(使用选中概念)</button>
          </div>
          <div class="list" id="memoryList"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>连接</h2>
      <div class="form">
        <input type="text" id="connFrom" placeholder="from 概念ID">
        <input type="text" id="connTo" placeholder="to 概念ID">
        <input type="number" id="connStrength" placeholder="强度(0-1)" value="1" step="0.1" min="0" max="1">
        <button id="addConnBtn">添加连接</button>
      </div>
      <div class="list" id="connList"></div>
    </section>

    <section class="panel">
      <h2>人物印象</h2>
      <div class="form">
        <input type="text" id="impPerson" placeholder="人物">
        <input type="text" id="impSummary" placeholder="摘要">
        <input type="number" id="impScore" placeholder="分数(0-1)" step="0.1" min="0" max="1">
        <input type="text" id="impDetails" placeholder="详细">
        <button id="addImpBtn">记录/更新印象</button>
      </div>
      <div class="list" id="impList"></div>
    </section>
  </main>

  <footer>
    <small>Memora Connect Web UI</small>
  </footer>

  <script src="/static/app.js"></script>
</body>
</html>
"""

DEFAULT_STYLE_CSS = """* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0; background: #f6f7fb; color: #222; }
header { background: #2b3a67; color: #fff; padding: 12px 16px; }
h1 { margin: 0 0 8px; font-size: 18px; }
.toolbar { display: flex; gap: 12px; align-items: center; }
.toolbar input, .toolbar select { padding: 4px 6px; }
main { display: grid; grid-template-columns: 1fr; gap: 16px; padding: 16px; }
.panel { background: #fff; border-radius: 8px; padding: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.panel h2 { margin-top: 0; font-size: 16px; }
#graph { width: 100%; height: 380px; background: #fafafa; border: 1px solid #e5e7ef; border-radius: 6px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
.form input { padding: 6px 8px; border: 1px solid #d7d9e0; border-radius: 6px; }
.form button { padding: 8px 12px; border: none; background: #2b3a67; color: #fff; border-radius: 6px; cursor: pointer; }
.list { display: grid; gap: 6px; max-height: 260px; overflow: auto; border: 1px dashed #e1e3ea; padding: 8px; border-radius: 6px; background: #fbfcff; }
.item { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px; border: 1px solid #eee; border-radius: 6px; background: #fff; }
.item small { color: #666; }
.item .actions { display: flex; gap: 6px; }
button.small { background: #4b83f5; padding: 4px 8px; font-size: 12px; }
button.danger { background: #da4b4b; }
footer { text-align: center; padding: 12px; color: #666; }
"""

DEFAULT_APP_JS = """const state = {
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

  main();
});
"""
