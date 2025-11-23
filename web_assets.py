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
  <title>Memora Dashboard</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
  <!-- Simple icons if needed, can add FontAwesome here if internet access allows, otherwise use unicode/svg -->
</head>
<body>
  <header>
    <div class="brand">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="#007AFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M2 17L12 22L22 17" stroke="#007AFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M2 12L12 17L22 12" stroke="#007AFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <h1>Memora</h1>
    </div>
    <div class="toolbar">
      <select id="groupSelect"></select>
      <input type="password" id="tokenInput" placeholder="访问令牌">
      <button id="refreshBtn" class="primary">刷新</button>
    </div>
  </header>

  <main>
    <!-- Left Column: Concepts -->
    <div class="sidebar">
      <section class="panel" style="flex: 1;">
        <div class="panel-header">
          <h2>概念</h2>
        </div>
        <div class="panel-body">
          <div class="form-grid" style="margin-bottom: 12px;">
            <div class="form-row">
              <input type="text" id="newConceptName" placeholder="新概念名称" style="flex:1;">
              <button id="addConceptBtn" class="primary">+</button>
            </div>
          </div>
          <div class="list" id="conceptList"></div>
        </div>
      </section>
    </div>

    <!-- Center Column: Graph & Memories -->
    <div class="center-stage">
      <section class="panel" style="height: 500px; flex-shrink: 0;">
        <div class="panel-header">
          <h2>记忆图谱</h2>
        </div>
        <div class="panel-body" style="padding: 0;">
          <div id="graph"></div>
        </div>
      </section>

      <section class="panel" style="flex: 1;">
        <div class="panel-header">
          <h2>记忆详情</h2>
        </div>
        <div class="panel-body">
          <div class="form-grid" style="margin-bottom: 20px;">
            <div class="form-row">
              <input type="text" id="memContent" placeholder="内容" style="flex: 2;">
              <input type="text" id="memDetails" placeholder="细节" style="flex: 2;">
              <button id="addMemoryBtn" class="primary">添加</button>
            </div>
            <div class="form-row">
              <input type="text" id="memParticipants" placeholder="参与者">
              <input type="text" id="memTags" placeholder="标签">
              <input type="text" id="memEmotion" placeholder="情感">
            </div>
            <div class="form-row">
              <input type="text" id="memLocation" placeholder="地点">
              <input type="number" id="memStrength" placeholder="强度(0-1)" step="0.1" min="0" max="1">
            </div>
          </div>
          <div class="list" id="memoryList"></div>
        </div>
      </section>
    </div>

    <!-- Right Column: Impressions & Search -->
    <div class="sidebar">
      <!-- Search Panel -->
      <section class="panel">
        <div class="panel-header">
          <h2>搜索</h2>
        </div>
        <div class="panel-body">
          <div class="form-row">
            <input type="text" id="memSearchQuery" placeholder="搜索记忆..." style="flex: 1;">
            <button id="memSearchBtn" class="primary">Go</button>
            <button id="memSearchClearBtn">X</button>
          </div>
          <div class="list" id="memSearchList" style="margin-top: 12px; max-height: 200px; overflow-y: auto;"></div>
        </div>
      </section>

      <!-- Impressions Panel -->
      <section class="panel" style="flex: 1;">
        <div class="panel-header">
          <h2>人物印象</h2>
        </div>
        <div class="panel-body">
           <div class="form-grid" style="margin-bottom: 12px;">
             <div class="form-row">
                <input type="text" id="impPerson" placeholder="人物" style="flex: 1;">
                <input type="number" id="impScore" placeholder="分数" style="width: 60px;">
                <button id="addImpBtn" class="primary">记录</button>
             </div>
             <input type="text" id="impSummary" placeholder="摘要">
             <input type="text" id="impDetails" placeholder="详细">
           </div>
           
           <div class="list" id="impList" style="margin-bottom: 12px; max-height: 200px; overflow-y: auto;"></div>
           
           <div id="impDetail" class="impression-detail" style="display: none;"></div>
           
           <div class="form-row" style="margin-top: 12px;">
             <input type="number" id="impDelta" placeholder="调整(-1~1)" step="0.1" min="-1" max="1" style="flex:1">
             <button id="impAdjustBtn">调整好感</button>
           </div>
        </div>
      </section>

      <!-- Connections Panel -->
      <section class="panel">
        <div class="panel-header">
          <h2>连接</h2>
        </div>
        <div class="panel-body">
          <div class="form-grid" style="margin-bottom: 12px;">
            <div class="form-row">
              <input type="text" id="connFrom" placeholder="From" style="flex: 1;">
              <input type="text" id="connTo" placeholder="To" style="flex: 1;">
            </div>
            <div class="form-row">
              <input type="number" id="connStrength" placeholder="强度" value="1" step="0.1" min="0" max="1" style="flex: 1;">
              <button id="addConnBtn" class="primary">连线</button>
            </div>
          </div>
          <div class="list" id="connList" style="max-height: 200px; overflow-y: auto;"></div>
        </div>
      </section>
    </div>
  </main>

  <script src="/static/app.js"></script>
</body>
</html>
"""

DEFAULT_STYLE_CSS = """:root {
  --app-bg: #f2f2f7; /* iOS System Gray 6 */
  --glass-bg: rgba(255, 255, 255, 0.75);
  --glass-border: rgba(255, 255, 255, 0.5);
  --glass-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
  --primary: #007AFF;
  --danger: #FF3B30;
  --success: #34C759;
  --text-primary: #000000;
  --text-secondary: #8E8E93;
  --radius-l: 20px;
  --radius-m: 12px;
  --radius-s: 8px;
  --font-stack: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --header-height: 60px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --app-bg: #000000;
    --glass-bg: rgba(30, 30, 30, 0.75);
    --glass-border: rgba(255, 255, 255, 0.1);
    --text-primary: #FFFFFF;
    --text-secondary: #98989D;
  }
}

* {
  box-sizing: border-box;
  -webkit-font-smoothing: antialiased;
}

body {
  margin: 0;
  font-family: var(--font-stack);
  background: var(--app-bg);
  background-image: radial-gradient(circle at 50% 0%, #eef2f5 0%, var(--app-bg) 70%);
  color: var(--text-primary);
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
header {
  height: var(--header-height);
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--glass-border);
  position: sticky;
  top: 0;
  z-index: 100;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.5px;
}

.toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
}

/* Inputs & Buttons */
input, select, button {
  font-family: inherit;
  font-size: 14px;
  outline: none;
}

input, select {
  padding: 8px 12px;
  border-radius: var(--radius-m);
  border: 1px solid rgba(0,0,0,0.1);
  background: rgba(255,255,255,0.8);
  color: var(--text-primary);
  transition: all 0.2s ease;
}

input:focus, select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
  background: #fff;
}

button {
  padding: 8px 16px;
  border-radius: var(--radius-m);
  border: none;
  font-weight: 500;
  cursor: pointer;
  background: rgba(0,0,0,0.05);
  color: var(--primary);
  transition: all 0.2s ease;
}

button:hover {
  background: rgba(0,0,0,0.1);
}

button:active {
  transform: scale(0.96);
}

button.primary {
  background: var(--primary);
  color: white;
  box-shadow: 0 2px 8px rgba(0, 122, 255, 0.3);
}

button.primary:hover {
  background: #006ce6;
}

button.danger {
  color: var(--danger);
  background: rgba(255, 59, 48, 0.1);
}

button.danger:hover {
  background: rgba(255, 59, 48, 0.2);
}

/* Layout */
main {
  flex: 1;
  display: grid;
  grid-template-columns: 300px 1fr 350px;
  grid-template-rows: 1fr;
  gap: 20px;
  padding: 20px;
  overflow: hidden;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
  padding-right: 4px; /* Scrollbar space */
}

.center-stage {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0; /* Fix flex child overflow */
}

/* Cards / Panels */
.panel {
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-l);
  box-shadow: var(--glass-shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.2s ease;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.panel-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

/* Graph */
#graph {
  width: 100%;
  height: 100%;
  border-radius: var(--radius-m);
  background: rgba(255,255,255,0.3);
}

/* Lists */
.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  background: rgba(255,255,255,0.5);
  padding: 12px;
  border-radius: var(--radius-m);
  border: 1px solid transparent;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item:hover {
  background: rgba(255,255,255,0.9);
  border-color: rgba(0,0,0,0.05);
  box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}

.item.active {
  background: #fff;
  border-color: var(--primary);
  box-shadow: 0 4px 12px rgba(0, 122, 255, 0.15);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.item-title {
  font-weight: 500;
  font-size: 15px;
}

.item-meta {
  font-size: 12px;
  color: var(--text-secondary);
}

.item-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.item-actions button {
  padding: 4px 10px;
  font-size: 12px;
  background: rgba(0,0,0,0.03);
}

/* Forms */
.form-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.form-row {
  display: flex;
  gap: 10px;
}

/* Scrollbars */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.1);
  border-radius: 10px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(0,0,0,0.2);
}

/* Mobile Responsiveness */
@media (max-width: 1024px) {
  main {
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto 1fr;
    overflow-y: auto;
    display: block;
  }
  
  .sidebar, .center-stage {
    width: 100%;
    margin-bottom: 20px;
  }
  
  #graph {
    min-height: 400px;
  }
}

/* Toast Notification */
.toast-container {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 1000;
}

.toast {
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 12px 24px;
  border-radius: 50px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  font-size: 14px;
  animation: slideUp 0.3s ease-out;
  display: flex;
  align-items: center;
  gap: 8px;
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* Spinner */
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(0, 122, 255, 0.3);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
"""

DEFAULT_APP_JS = """const state = {
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
"""
