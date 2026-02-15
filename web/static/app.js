
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
