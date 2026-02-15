"""默认的 Memora Web 前端静态资源。

当插件在打包或部署时遗漏了 webui 目录中的文件时，
web_server 会使用这里的内容在运行目录下自动生成
index.html、style.css 和 app.js，以保证 Web 管理界面可用。
"""

DEFAULT_INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memora Connect</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
</head>
<body>
  <div class="app-container">
    <!-- Header -->
    <header class="app-header">
      <div class="brand">
        <div class="brand-icon"></div>
        <span>Memora Connect</span>
      </div>
      
      <div class="search-bar">
        <i class="fa-solid fa-search search-icon"></i>
        <input type="text" id="globalSearch" placeholder="搜索记忆、概念、人物...">
      </div>

      <div class="header-controls">
        <select id="groupSelect" style="width: 150px;"></select>
        <button id="refreshBtn" class="icon-btn"><i class="fa-solid fa-sync"></i></button>
        <button id="settingsBtn" class="icon-btn"><i class="fa-solid fa-cog"></i></button>
      </div>
    </header>

    <!-- Sidebar -->
    <aside class="app-sidebar">
      <div class="tabs">
        <button class="tab-btn active" data-tab="concepts">概念</button>
        <button class="tab-btn" data-tab="memories">记忆</button>
        <button class="tab-btn" data-tab="impressions">印象</button>
      </div>

      <!-- Concepts Tab -->
      <div id="tab-concepts" class="tab-content">
        <div class="flex-row mb-2">
          <input type="text" id="newConceptName" placeholder="新概念名称" class="full-width">
          <button id="addConceptBtn" class="icon-btn"><i class="fa-solid fa-plus"></i></button>
        </div>
        <div class="list-group" id="conceptList"></div>
      </div>

      <!-- Memories Tab -->
      <div id="tab-memories" class="tab-content hidden">
        <div class="list-group" id="memoryListSidebar"></div>
      </div>

      <!-- Impressions Tab -->
      <div id="tab-impressions" class="tab-content hidden">
        <div class="flex-row mb-2">
           <button id="addImpressionBtn" class="full-width"><i class="fa-solid fa-plus"></i> 新建印象</button>
        </div>
        <div class="list-group" id="impressionList"></div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="app-main">
      <div id="graph"></div>
      
      <!-- Context Menu -->
      <div id="contextMenu" class="context-menu"></div>
    </main>
  </div>

  <!-- Floating Panel (Details / Edit) -->
  <div id="sidePanel" class="floating-panel">
    <div class="panel-header">
      <span id="panelTitle">详情</span>
      <button id="closePanelBtn" class="icon-btn" style="width: 24px; height: 24px;"><i class="fa-solid fa-times"></i></button>
    </div>
    <div class="panel-content" id="panelContent">
      <!-- Dynamic Content -->
    </div>
    <div class="panel-footer flex-row space-between" id="panelFooter">
      <!-- Dynamic Actions -->
    </div>
  </div>

  <!-- Settings Modal (hidden by default, maybe reuse panel or create modal) -->
  <dialog id="settingsDialog" style="padding: 20px; border-radius: 12px; border: 1px solid #ccc;">
    <h3>设置</h3>
    <label>访问令牌: <input type="password" id="tokenInput" class="full-width mt-2"></label>
    <div class="mt-2 flex-row" style="justify-content: flex-end;">
      <button id="saveSettingsBtn">保存</button>
    </div>
  </dialog>

  <script src="/static/app.js"></script>
</body>
</html>
"""

DEFAULT_STYLE_CSS = r""":root {
  --glass-bg: rgba(255, 255, 255, 0.65);
  --glass-border: rgba(255, 255, 255, 0.4);
  --glass-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.10);
  --primary-color: #007aff;
  --text-color: #1c1c1e;
  --secondary-text: #8e8e93;
  --danger-color: #ff3b30;
  --success-color: #34c759;
  --bg-gradient: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  --sidebar-width: 300px;
  --header-height: 60px;
  --radius-lg: 24px;
  --radius-md: 16px;
  --radius-sm: 10px;
  --font-stack: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
}

* {
  box-sizing: border-box;
  -webkit-tap-highlight-color: transparent;
}

body {
  font-family: var(--font-stack);
  margin: 0;
  padding: 0;
  background: #eef2f5; /* Fallback */
  background: var(--bg-gradient);
  color: var(--text-color);
  height: 100vh;
  overflow: hidden;
  font-size: 14px;
}

/* Layout */
.app-container {
  display: grid;
  grid-template-columns: var(--sidebar-width) 1fr;
  grid-template-rows: var(--header-height) 1fr;
  height: 100vh;
  width: 100vw;
}

/* Header */
.app-header {
  grid-column: 1 / -1;
  background: var(--glass-bg);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 100;
}

.brand {
  font-weight: 600;
  font-size: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-icon {
  width: 24px;
  height: 24px;
  background: var(--primary-color);
  border-radius: 8px;
}

.header-controls {
  display: flex;
  gap: 16px;
  align-items: center;
}

/* Sidebar */
.app-sidebar {
  grid-row: 2;
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-right: 1px solid var(--glass-border);
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  z-index: 90;
}

/* Main Content (Graph) */
.app-main {
  grid-column: 2;
  grid-row: 2;
  position: relative;
  overflow: hidden;
}

#graph {
  width: 100%;
  height: 100%;
  background: transparent;
}

/* UI Components */
.card {
  background: rgba(255, 255, 255, 0.7);
  border-radius: var(--radius-md);
  padding: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  border: 1px solid rgba(255,255,255,0.5);
}

.section-title {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--secondary-text);
  margin-bottom: 12px;
  font-weight: 600;
}

/* Inputs & Buttons */
input, select, textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(0,0,0,0.1);
  background: rgba(255,255,255,0.8);
  font-family: inherit;
  font-size: 14px;
  transition: all 0.2s;
  outline: none;
}

input:focus, select:focus, textarea:focus {
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.2);
}

button {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

button:active {
  transform: translateY(0);
}

button.secondary {
  background: rgba(0,0,0,0.05);
  color: var(--text-color);
}

button.danger {
  background: var(--danger-color);
}

button.icon-btn {
  padding: 8px;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.5);
}

/* Lists */
.list-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-item {
  background: rgba(255,255,255,0.6);
  padding: 10px;
  border-radius: var(--radius-sm);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: background 0.2s;
  border: 1px solid transparent;
}

.list-item:hover {
  background: rgba(255,255,255,0.9);
  border-color: rgba(0,0,0,0.05);
}

.list-item.active {
  background: white;
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(0, 122, 255, 0.15);
}

/* Floating Panels / Modals */
.floating-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 320px;
  max-height: calc(100% - 40px);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: saturate(180%) blur(25px);
  -webkit-backdrop-filter: saturate(180%) blur(25px);
  border-radius: var(--radius-lg);
  box-shadow: var(--glass-shadow);
  border: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.3s cubic-bezier(0.19, 1, 0.22, 1), opacity 0.3s ease;
  z-index: 50;
  transform: translateX(350px);
  opacity: 0;
  pointer-events: none;
}

.floating-panel.visible {
  transform: translateX(0);
  opacity: 1;
  pointer-events: auto;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.panel-content {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.panel-footer {
  padding: 16px 20px;
  border-top: 1px solid rgba(0,0,0,0.05);
  background: rgba(255,255,255,0.3);
}

/* Context Menu */
.context-menu {
  position: absolute;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(20px);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  padding: 6px;
  min-width: 160px;
  z-index: 200;
  display: none;
  border: 1px solid rgba(255,255,255,0.5);
}

.context-menu-item {
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.context-menu-item:hover {
  background: var(--primary-color);
  color: white;
}

/* Scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.1);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(0,0,0,0.2);
}

/* Utilities */
.hidden { display: none !important; }
.flex-row { display: flex; gap: 8px; align-items: center; }
.flex-col { display: flex; flex-direction: column; gap: 8px; }
.space-between { justify-content: space-between; }
.text-sm { font-size: 12px; color: var(--secondary-text); }
.mt-2 { margin-top: 8px; }
.mb-2 { margin-bottom: 8px; }
.p-2 { padding: 8px; }
.full-width { width: 100%; }

/* Search Bar */
.search-bar {
  position: relative;
  width: 300px;
}
.search-bar input {
  padding-left: 36px;
  border-radius: 20px;
  background: rgba(0,0,0,0.05);
  border: none;
}
.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0.5;
}

/* Tags */
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(0, 122, 255, 0.1);
  color: var(--primary-color);
  font-size: 11px;
  margin-right: 4px;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: rgba(0,0,0,0.05);
  border-radius: 12px;
  margin-bottom: 16px;
}

.tab-btn {
  flex: 1;
  background: transparent;
  color: var(--secondary-text);
  padding: 6px;
  font-size: 12px;
  border-radius: 8px;
}

.tab-btn.active {
  background: white;
  color: var(--text-color);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
"""

DEFAULT_APP_JS = r"""
/* API Service */
const API = {
  headers() {
    const h = { "Content-Type": "application/json" };
    if (Store.token) h["x-access-token"] = Store.token;
    return h;
  },

  async request(method, url, body = null) {
    const opts = { method, headers: this.headers() };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  get(url) { return this.request('GET', url); },
  post(url, body) { return this.request('POST', url, body); },
  put(url, body) { return this.request('PUT', url, body); },
  delete(url) { return this.request('DELETE', url); },
};

/* State Management */
const Store = {
  group: "",
  token: localStorage.getItem('memora_token') || "",
  concepts: [],
  memories: [],
  impressions: [],
  graphData: { nodes: [], edges: [] },
  selectedNodeId: null,
  selectedEdgeId: null,

  async init() {
    await this.loadGroups();
    await this.loadAll();
  },

  async loadGroups() {
    const data = await API.get('/api/groups');
    UI.renderGroups(data.groups);
  },

  async loadAll() {
    const pGroupId = encodeURIComponent(this.group);
    
    // Load Graph
    try {
      this.graphData = await API.get(`/api/graph?group_id=${pGroupId}`);
      Graph.render(this.graphData);
    } catch (e) { console.error("Graph load failed", e); }

    // Load Concepts
    try {
      const cData = await API.get(`/api/concepts?group_id=${pGroupId}`);
      this.concepts = cData.concepts || [];
      UI.renderConcepts(this.concepts);
    } catch (e) { console.error("Concepts load failed", e); }

    // Load Memories (Recent)
    try {
      const mData = await API.get(`/api/memories?group_id=${pGroupId}`);
      this.memories = mData.memories || [];
      UI.renderMemories(this.memories);
    } catch (e) { console.error("Memories load failed", e); }

    // Load Impressions
    try {
      const iData = await API.get(`/api/impressions?group_id=${pGroupId}`);
      this.impressions = iData.people || [];
      UI.renderImpressions(this.impressions);
    } catch (e) { console.error("Impressions load failed", e); }
  }
};

/* Graph Manager */
const Graph = {
  cy: null,
  layoutConfig: { name: 'cose', animate: true, animationDuration: 500, nodeDimensionsIncludeLabels: true },

  init() {
    this.cy = cytoscape({
      container: document.getElementById('graph'),
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'color': '#333',
            'font-size': '12px',
            'text-valign': 'center',
            'text-halign': 'center',
            'background-color': '#fff',
            'border-width': 2,
            'border-color': '#007aff',
            'width': 'label',
            'height': 'label',
            'padding': '10px',
            'text-wrap': 'wrap',
            'text-max-width': '100px',
            'shape': 'round-rectangle'
          }
        },
        {
          selector: 'edge',
          style: {
            'width': 2,
            'line-color': '#cfd8dc',
            'target-arrow-color': '#cfd8dc',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(weight)',
            'font-size': '10px',
            'color': '#90a4ae',
            'text-background-color': '#fff',
            'text-background-opacity': 0.7
          }
        },
        {
          selector: ':selected',
          style: {
            'border-color': '#ff9500',
            'border-width': 4,
            'line-color': '#ff9500',
            'target-arrow-color': '#ff9500'
          }
        }
      ],
      wheelSensitivity: 0.2,
    });

    this.bindEvents();
  },

  bindEvents() {
    this.cy.on('tap', 'node', e => {
      const node = e.target;
      Store.selectedNodeId = node.id();
      Store.selectedEdgeId = null;
      UI.showConceptPanel(node.id(), node.data('name'));
    });

    this.cy.on('tap', 'edge', e => {
      const edge = e.target;
      Store.selectedEdgeId = edge.id();
      Store.selectedNodeId = null;
      UI.showConnectionPanel(edge.id(), edge.data());
    });

    this.cy.on('tap', e => {
      if (e.target === this.cy) {
        Store.selectedNodeId = null;
        Store.selectedEdgeId = null;
        UI.hidePanel();
        UI.hideContextMenu();
      }
    });

    this.cy.on('cxttap', 'node', e => {
      UI.showContextMenu(e.originalEvent.clientX, e.originalEvent.clientY, 'node', e.target.id());
    });
    
    this.cy.on('cxttap', e => {
      if(e.target === this.cy) {
        UI.showContextMenu(e.originalEvent.clientX, e.originalEvent.clientY, 'bg');
      }
    });
  },

  render(data) {
    const nodes = data.nodes.map(n => ({ 
      data: { id: n.id, name: n.name, label: `${n.name}\n(${n.count})` } 
    }));
    const edges = data.edges.map(e => ({ 
      data: { 
        id: e.id, 
        source: e.from_concept, 
        target: e.to_concept, 
        weight: e.strength.toFixed(2),
        rawStrength: e.strength
      } 
    }));

    this.cy.elements().remove();
    this.cy.add({ nodes, edges });
    this.cy.layout(this.layoutConfig).run();
  },
  
  center() {
      this.cy.fit();
  }
};

/* UI Manager */
const UI = {
  // Elements
  el: {
    groupSelect: document.getElementById('groupSelect'),
    conceptList: document.getElementById('conceptList'),
    memoryListSidebar: document.getElementById('memoryListSidebar'),
    impressionList: document.getElementById('impressionList'),
    sidePanel: document.getElementById('sidePanel'),
    panelTitle: document.getElementById('panelTitle'),
    panelContent: document.getElementById('panelContent'),
    panelFooter: document.getElementById('panelFooter'),
    contextMenu: document.getElementById('contextMenu'),
    tabs: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
  },

  init() {
    // Tabs
    this.el.tabs.forEach(btn => {
      btn.addEventListener('click', () => {
        this.el.tabs.forEach(b => b.classList.remove('active'));
        this.el.tabContents.forEach(c => c.classList.add('hidden'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`).classList.remove('hidden');
      });
    });

    // Close Panel
    document.getElementById('closePanelBtn').addEventListener('click', () => this.hidePanel());

    // Settings
    document.getElementById('settingsBtn').addEventListener('click', () => {
      document.getElementById('tokenInput').value = Store.token;
      document.getElementById('settingsDialog').showModal();
    });
    document.getElementById('saveSettingsBtn').addEventListener('click', () => {
      Store.token = document.getElementById('tokenInput').value.trim();
      localStorage.setItem('memora_token', Store.token);
      document.getElementById('settingsDialog').close();
      Store.loadAll();
    });

    // Global Search
    document.getElementById('globalSearch').addEventListener('keydown', async (e) => {
      if (e.key === 'Enter') {
        const q = e.target.value.trim();
        if (!q) return;
        const res = await API.get(`/api/memories?group_id=${encodeURIComponent(Store.group)}&q=${encodeURIComponent(q)}`);
        // Switch to memory tab and show results
        this.el.tabs.forEach(b => b.classList.remove('active'));
        this.el.tabContents.forEach(c => c.classList.add('hidden'));
        document.querySelector('[data-tab="memories"]').classList.add('active');
        document.getElementById('tab-memories').classList.remove('hidden');
        this.renderMemories(res.memories || []);
      }
    });

    // Add Concept
    document.getElementById('addConceptBtn').addEventListener('click', async () => {
      const name = document.getElementById('newConceptName').value.trim();
      if (!name) return;
      await API.post('/api/concepts', { group_id: Store.group, name });
      document.getElementById('newConceptName').value = '';
      Store.loadAll();
    });
    
    // Add Impression
    document.getElementById('addImpressionBtn').addEventListener('click', () => {
        this.showCreateImpressionPanel();
    });

    // Refresh
    document.getElementById('refreshBtn').addEventListener('click', () => Store.loadAll());

    // Group Change
    this.el.groupSelect.addEventListener('change', (e) => {
      Store.group = e.target.value;
      Store.loadAll();
    });
  },

  renderGroups(groups) {
    this.el.groupSelect.innerHTML = '';
    groups.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g;
      opt.textContent = g || '默认/私聊';
      this.el.groupSelect.appendChild(opt);
    });
    this.el.groupSelect.value = Store.group;
  },

  renderConcepts(concepts) {
    this.el.conceptList.innerHTML = '';
    concepts.forEach(c => {
      const div = document.createElement('div');
      div.className = 'list-item';
      div.innerHTML = `<span>${c.name}</span><span class="text-sm">${c.id.substring(0,6)}...</span>`;
      div.onclick = () => {
         // Focus on graph
         const node = Graph.cy.getElementById(c.id);
         if(node.length) {
             Graph.cy.fit(node, 50);
             node.select();
             this.showConceptPanel(c.id, c.name);
         } else {
             this.showConceptPanel(c.id, c.name);
         }
      };
      this.el.conceptList.appendChild(div);
    });
  },

  renderMemories(memories) {
    this.el.memoryListSidebar.innerHTML = '';
    memories.forEach(m => {
      const div = document.createElement('div');
      div.className = 'list-item flex-col';
      div.style.alignItems = 'flex-start';
      div.innerHTML = `
        <div class="text-sm text-secondary">${m.created_at}</div>
        <div>${m.content}</div>
        <div class="flex-row">
            <span class="tag">强度: ${m.strength.toFixed(2)}</span>
            <span class="tag">CID: ${m.concept_id.substring(0,6)}</span>
        </div>
      `;
      div.onclick = () => {
          // Open edit panel
          this.showMemoryPanel(m, true);
      };
      this.el.memoryListSidebar.appendChild(div);
    });
  },

  renderImpressions(people) {
    this.el.impressionList.innerHTML = '';
    people.forEach(p => {
      const div = document.createElement('div');
      div.className = 'list-item';
      div.innerHTML = `<span>${p.name}</span>`;
      div.onclick = () => {
          this.showImpressionDetailPanel(p.name);
      };
      this.el.impressionList.appendChild(div);
    });
  },

  // Panels
  showPanel(title, contentHtml, footerHtml) {
    this.el.panelTitle.textContent = title;
    this.el.panelContent.innerHTML = contentHtml;
    this.el.panelFooter.innerHTML = footerHtml;
    this.el.sidePanel.classList.add('visible');
  },

  hidePanel() {
    this.el.sidePanel.classList.remove('visible');
  },

  async showConceptPanel(id, name) {
    // Fetch memories for concept
    let mems = [];
    try {
        const res = await API.get(`/api/memories?group_id=${encodeURIComponent(Store.group)}&concept_id=${id}`);
        mems = res.memories || [];
    } catch(e) {}

    const content = `
      <div class="flex-col">
        <label class="text-sm">ID: ${id}</label>
        <label>名称</label>
        <input type="text" id="editConceptName" value="${name}">
        <div class="mt-2">
            <label class="section-title">记忆列表 (${mems.length})</label>
            <div class="list-group mt-2">
                ${mems.map(m => `
                    <div class="card p-2 text-sm" onclick="UI.showMemoryPanel({id:'${m.id}', content:'${m.content.replace(/'/g,"\\'").replace(/\n/g," ")}', strength:${m.strength}, details:'${(m.details||"").replace(/'/g,"\\'")}', concept_id:'${id}'}, true)">
                        ${m.content}
                    </div>
                `).join('')}
            </div>
            <button class="mt-2 full-width secondary" onclick="UI.showMemoryPanel({concept_id:'${id}'}, false)">+ 添加记忆</button>
        </div>
      </div>
    `;

    const footer = `
      <button class="danger" onclick="App.deleteConcept('${id}')">删除概念</button>
      <button onclick="App.updateConcept('${id}')">保存修改</button>
    `;

    this.showPanel('概念详情', content, footer);
  },
  
  showMemoryPanel(memory, isEdit) {
      const content = `
        <div class="flex-col">
            <label>内容</label>
            <textarea id="memContent" rows="3">${memory.content || ''}</textarea>
            
            <label>细节</label>
            <textarea id="memDetails" rows="2">${memory.details || ''}</textarea>
            
            <div class="flex-row">
                <div class="flex-col full-width">
                    <label>强度 (0-1)</label>
                    <input type="number" id="memStrength" step="0.1" min="0" max="1" value="${memory.strength || 1}">
                </div>
                <div class="flex-col full-width">
                    <label>情感</label>
                    <input type="text" id="memEmotion" value="${memory.emotion || ''}">
                </div>
            </div>
            
            <label>参与者</label>
            <input type="text" id="memParticipants" value="${memory.participants || ''}">
            
            <label>地点</label>
            <input type="text" id="memLocation" value="${memory.location || ''}">
            
            <label>标签</label>
            <input type="text" id="memTags" value="${memory.tags || ''}">
            
            <input type="hidden" id="memConceptId" value="${memory.concept_id}">
        </div>
      `;
      
      const footer = isEdit 
        ? `<button class="danger" onclick="App.deleteMemory('${memory.id}')">删除</button>
           <button onclick="App.updateMemory('${memory.id}')">更新</button>`
        : `<button onclick="App.createMemory()">创建</button>`;
      
      this.showPanel(isEdit ? '编辑记忆' : '新建记忆', content, footer);
  },

  showConnectionPanel(id, data) {
    const content = `
      <div class="flex-col">
        <label>From: ${data.source}</label>
        <label>To: ${data.target}</label>
        <label>强度</label>
        <input type="number" id="connStrength" value="${data.rawStrength}" step="0.1" min="0" max="1">
      </div>
    `;

    const footer = `
      <button class="danger" onclick="App.deleteConnection('${id}')">断开连接</button>
      <button onclick="App.updateConnection('${id}')">更新</button>
    `;

    this.showPanel('连接详情', content, footer);
  },
  
  async showImpressionDetailPanel(person) {
      let data = {};
      try {
          data = await API.get(`/api/impressions?group_id=${encodeURIComponent(Store.group)}&person=${encodeURIComponent(person)}`);
      } catch(e) {}
      
      const summary = data.summary || {};
      const memories = data.memories || [];
      
      const content = `
         <div class="flex-col">
             <h3>${summary.name || person}</h3>
             <div class="card">
                 <label class="text-sm">摘要</label>
                 <div>${summary.summary || '无摘要'}</div>
                 <div class="mt-2 text-sm">好感度: ${summary.score !== null ? summary.score.toFixed(2) : 'N/A'}</div>
             </div>
             
             <div class="flex-row mt-2">
                 <input type="number" id="impDelta" placeholder="好感度变化" step="0.1">
                 <button class="small" onclick="App.adjustImpression('${person}')">调整</button>
             </div>
             
             <label class="section-title mt-2">相关记忆</label>
             <div class="list-group">
                 ${memories.map(m => `
                     <div class="list-item text-sm">
                         ${m.content} <span class="tag">${m.score?.toFixed(2)||''}</span>
                     </div>
                 `).join('')}
             </div>
         </div>
      `;
      
      this.showPanel('印象详情', content, '');
  },
  
  showCreateImpressionPanel() {
      const content = `
        <div class="flex-col">
            <label>人物名称</label>
            <input type="text" id="impPerson">
            <label>摘要</label>
            <textarea id="impSummary" rows="3"></textarea>
            <label>初始好感度</label>
            <input type="number" id="impScore" step="0.1">
            <label>详情</label>
            <textarea id="impDetails"></textarea>
        </div>
      `;
      const footer = `<button onclick="App.createImpression()">创建</button>`;
      this.showPanel('新建印象', content, footer);
  },
  
  showCreateConnectionPanel(fromId) {
       const content = `
        <div class="flex-col">
            <label>源概念 (From)</label>
            <input type="text" value="${fromId}" disabled>
            <label>目标概念ID (To)</label>
            <input type="text" id="connToId">
            <label>强度</label>
            <input type="number" id="newConnStrength" value="1.0" step="0.1">
            <p class="text-sm">提示：您可以输入目标概念ID</p>
        </div>
      `;
      const footer = `<button onclick="App.createConnection('${fromId}')">连接</button>`;
      this.showPanel('新建连接', content, footer);
  },

  // Context Menu
  showContextMenu(x, y, type, id) {
    this.el.contextMenu.style.left = `${x}px`;
    this.el.contextMenu.style.top = `${y}px`;
    this.el.contextMenu.style.display = 'block';
    
    let html = '';
    if (type === 'node') {
      html = `
        <div class="context-menu-item" onclick="UI.showConceptPanel('${id}', '${Graph.cy.getElementById(id).data('name')}')"><i class="fa-solid fa-eye"></i> 详情</div>
        <div class="context-menu-item" onclick="UI.showMemoryPanel({concept_id:'${id}'}, false)"><i class="fa-solid fa-plus"></i> 添加记忆</div>
        <div class="context-menu-item" onclick="UI.showCreateConnectionPanel('${id}')"><i class="fa-solid fa-link"></i> 连接到...</div>
        <div class="context-menu-item" onclick="App.deleteConcept('${id}')" style="color:var(--danger-color)"><i class="fa-solid fa-trash"></i> 删除</div>
      `;
    } else {
      // bg
      html = `
        <div class="context-menu-item" onclick="document.querySelector('[data-tab=\\'concepts\\']').click(); document.getElementById('newConceptName').focus();"><i class="fa-solid fa-plus"></i> 新建概念</div>
        <div class="context-menu-item" onclick="Graph.center()"><i class="fa-solid fa-crosshairs"></i> 居中视图</div>
        <div class="context-menu-item" onclick="Store.loadAll()"><i class="fa-solid fa-sync"></i> 刷新</div>
      `;
    }
    
    this.el.contextMenu.innerHTML = html;
  },

  hideContextMenu() {
    this.el.contextMenu.style.display = 'none';
  }
};

/* App Controller */
const App = {
  async init() {
    UI.init();
    Graph.init();
    await Store.init();
    
    // Global click to close context menu
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.context-menu')) {
            UI.hideContextMenu();
        }
    });
  },

  // Actions
  async updateConcept(id) {
    const name = document.getElementById('editConceptName').value.trim();
    if (!name) return;
    await API.put(`/api/concepts/${id}`, { group_id: Store.group, name });
    Store.loadAll();
    UI.hidePanel();
  },

  async deleteConcept(id) {
    if(!confirm('确定要删除该概念及其所有记忆吗？')) return;
    await API.delete(`/api/concepts/${id}?group_id=${encodeURIComponent(Store.group)}`);
    Store.loadAll();
    UI.hidePanel();
  },

  async createMemory() {
    const body = {
        group_id: Store.group,
        concept_id: document.getElementById('memConceptId').value,
        content: document.getElementById('memContent').value,
        details: document.getElementById('memDetails').value,
        participants: document.getElementById('memParticipants').value,
        tags: document.getElementById('memTags').value,
        emotion: document.getElementById('memEmotion').value,
        location: document.getElementById('memLocation').value,
        strength: parseFloat(document.getElementById('memStrength').value)
    };
    if(!body.content) return;
    await API.post('/api/memories', body);
    Store.loadAll();
    UI.hidePanel(); // Or refresh panel
  },

  async updateMemory(id) {
      const body = {
        group_id: Store.group,
        concept_id: document.getElementById('memConceptId').value,
        content: document.getElementById('memContent').value,
        details: document.getElementById('memDetails').value,
        participants: document.getElementById('memParticipants').value,
        tags: document.getElementById('memTags').value,
        emotion: document.getElementById('memEmotion').value,
        location: document.getElementById('memLocation').value,
        strength: parseFloat(document.getElementById('memStrength').value)
      };
      await API.put(`/api/memories/${id}`, body);
      Store.loadAll();
      UI.hidePanel();
  },

  async deleteMemory(id) {
      if(!confirm('删除记忆？')) return;
      await API.delete(`/api/memories/${id}?group_id=${encodeURIComponent(Store.group)}`);
      Store.loadAll();
      UI.hidePanel();
  },
  
  async updateConnection(id) {
      const s = parseFloat(document.getElementById('connStrength').value);
      await API.put(`/api/connections/${id}`, { group_id: Store.group, strength: s });
      Store.loadAll();
      UI.hidePanel();
  },
  
  async deleteConnection(id) {
      if(!confirm('断开连接？')) return;
      await API.delete(`/api/connections/${id}?group_id=${encodeURIComponent(Store.group)}`);
      Store.loadAll();
      UI.hidePanel();
  },
  
  async createConnection(fromId) {
      const toId = document.getElementById('connToId').value.trim();
      const strength = parseFloat(document.getElementById('newConnStrength').value);
      if(!toId) return;
      
      await API.post('/api/connections', {
          group_id: Store.group,
          from_concept: fromId,
          to_concept: toId,
          strength: strength
      });
      Store.loadAll();
      UI.hidePanel();
  },
  
  async createImpression() {
      const body = {
          group_id: Store.group,
          person: document.getElementById('impPerson').value.trim(),
          summary: document.getElementById('impSummary').value.trim(),
          score: parseFloat(document.getElementById('impScore').value),
          details: document.getElementById('impDetails').value.trim()
      };
      if(!body.person) return;
      await API.post('/api/impressions', body);
      Store.loadAll();
      UI.hidePanel();
  },
  
  async adjustImpression(person) {
      const delta = parseFloat(document.getElementById('impDelta').value);
      if(isNaN(delta)) return;
      await API.put(`/api/impressions/${encodeURIComponent(person)}/score`, {
          group_id: Store.group,
          delta: delta
      });
      UI.showImpressionDetailPanel(person); // Reload panel
  }
};

/* Start */
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// Expose for onclick handlers
window.UI = UI;
window.App = App;
window.Store = Store;
window.Graph = Graph;
"""
