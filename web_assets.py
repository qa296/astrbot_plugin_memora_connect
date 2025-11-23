"""默认的 Memora Web 前端静态资源。

当插件在打包或部署时遗漏了 webui 目录中的文件时，
web_server 会使用这里的内容在运行目录下自动生成
index.html、style.css 和 app.js，以保证 Web 管理界面可用。

Updated to v0.2.7+ Refactored WebUI (Vue3 + ElementPlus + Tailwind)
"""

DEFAULT_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memora Connect Dashboard</title>
  
  <!-- Styles -->
  <link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css" />
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            primary: '#409eff',
            dark: {
              bg: '#1a1a1a',
              panel: '#242424',
              border: '#363636'
            }
          }
        }
      }
    }
  </script>
  <link rel="stylesheet" href="/static/style.css">

  <!-- Libraries -->
  <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
  <script src="https://unpkg.com/element-plus/dist/index.full.js"></script>
  <script src="https://unpkg.com/@element-plus/icons-vue"></script>
  <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
  <script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
</head>
<body class="bg-gray-100 dark:bg-dark-bg text-gray-800 dark:text-gray-200 m-0 transition-colors duration-300">
  <div id="app" class="h-screen flex flex-col overflow-hidden" v-cloak>
    
    <!-- Header -->
    <header class="bg-white dark:bg-dark-panel border-b border-gray-200 dark:border-dark-border h-14 flex items-center px-4 justify-between shadow-sm z-10">
      <div class="flex items-center gap-3">
        <el-icon :size="24" class="text-primary"><connection /></el-icon>
        <h1 class="font-bold text-lg tracking-wide">Memora Connect</h1>
      </div>
      
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
            <span class="text-sm text-gray-500">群组:</span>
            <el-select v-model="state.group" placeholder="选择群组" size="small" @change="refreshData" class="w-40">
                <el-option v-for="g in groups" :key="g" :label="g || '默认/私聊'" :value="g"></el-option>
            </el-select>
        </div>
        
        <el-input
          v-if="!hasTokenInUrl"
          v-model="state.token"
          type="password"
          placeholder="Access Token"
          size="small"
          class="w-32"
          show-password
          @change="refreshData"
        ></el-input>

        <el-button circle size="small" @click="toggleTheme">
          <el-icon v-if="isDark"><moon /></el-icon>
          <el-icon v-else><sunny /></el-icon>
        </el-button>
        
        <el-button type="primary" circle size="small" @click="refreshData" :loading="loading">
          <el-icon><refresh /></el-icon>
        </el-button>
      </div>
    </header>

    <!-- Main Content -->
    <div class="flex-1 flex overflow-hidden">
      
      <!-- Sidebar -->
      <aside class="w-64 bg-white dark:bg-dark-panel border-r border-gray-200 dark:border-dark-border flex flex-col">
        <el-menu
          :default-active="activeTab"
          class="border-none bg-transparent"
          @select="(val) => activeTab = val"
        >
          <el-menu-item index="graph">
            <el-icon><share /></el-icon>
            <span>记忆图谱</span>
          </el-menu-item>
          <el-menu-item index="concepts">
            <el-icon><collection /></el-icon>
            <span>概念管理</span>
          </el-menu-item>
          <el-menu-item index="memories">
            <el-icon><notebook /></el-icon>
            <span>记忆列表</span>
          </el-menu-item>
          <el-menu-item index="connections">
            <el-icon><link /></el-icon>
            <span>连接管理</span>
          </el-menu-item>
          <el-menu-item index="impressions">
            <el-icon><user /></el-icon>
            <span>人物印象</span>
          </el-menu-item>
        </el-menu>

        <div class="mt-auto p-4 text-xs text-center text-gray-400 border-t border-gray-100 dark:border-dark-border">
          AstrBot Memora Plugin<br>v0.2.7+
        </div>
      </aside>

      <!-- View Area -->
      <main class="flex-1 relative bg-gray-50 dark:bg-dark-bg overflow-hidden">
        
        <!-- Graph View -->
        <div v-show="activeTab === 'graph'" class="absolute inset-0 flex flex-col">
          <div id="cy" class="flex-1 bg-gray-50 dark:bg-gray-900"></div>
          <!-- Graph Overlay Controls -->
          <div class="absolute top-4 left-4 p-2 bg-white/80 dark:bg-black/50 backdrop-blur rounded shadow space-y-2 z-10 w-64">
             <div class="text-xs font-bold mb-1">图谱控制</div>
             <el-select v-model="graphLayout" size="small" class="w-full" placeholder="布局" @change="updateGraphLayout">
                <el-option label="Cose (智能)" value="cose"></el-option>
                <el-option label="Grid (网格)" value="grid"></el-option>
                <el-option label="Circle (圆形)" value="circle"></el-option>
                <el-option label="Concentric (同心)" value="concentric"></el-option>
             </el-select>
             <div class="flex gap-2">
                <el-button size="small" @click="fitGraph">适配视图</el-button>
                <el-button size="small" @click="randomizeGraph">随机重排</el-button>
             </div>
             <div v-if="selectedNode" class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600 text-sm">
                <div class="font-bold truncate">{{ selectedNode.label }}</div>
                <div class="text-xs text-gray-500">ID: {{ selectedNode.id }}</div>
                <div class="mt-2 flex gap-2">
                   <el-button type="primary" size="small" link @click="viewConceptMemories(selectedNode.id)">查看记忆</el-button>
                </div>
             </div>
          </div>
        </div>

        <!-- Concepts View -->
        <div v-if="activeTab === 'concepts'" class="h-full flex flex-col p-4 overflow-auto">
          <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-bold">概念管理</h2>
            <el-button type="primary" @click="showAddConceptDialog = true">
                <el-icon class="mr-1"><plus /></el-icon>添加概念
            </el-button>
          </div>
          
          <el-card shadow="never" class="flex-1 flex flex-col">
             <el-table :data="concepts" stripe style="width: 100%" height="100%">
                <el-table-column prop="id" label="ID" width="100" show-overflow-tooltip></el-table-column>
                <el-table-column prop="name" label="名称"></el-table-column>
                <el-table-column label="操作" width="200" align="right">
                    <template #default="scope">
                        <el-button size="small" @click="selectConcept(scope.row)">查看</el-button>
                        <el-button size="small" type="warning" @click="editConcept(scope.row)">重命名</el-button>
                        <el-button size="small" type="danger" @click="deleteConcept(scope.row)">删除</el-button>
                    </template>
                </el-table-column>
             </el-table>
          </el-card>
        </div>

        <!-- Memories View -->
        <div v-if="activeTab === 'memories'" class="h-full flex flex-col p-4 overflow-auto">
           <div class="flex justify-between items-center mb-4">
             <div class="flex items-center gap-4">
                 <h2 class="text-xl font-bold">记忆列表</h2>
                 <el-input v-model="searchQuery" placeholder="搜索记忆内容..." prefix-icon="Search" clearable @clear="searchMemories" @keyup.enter="searchMemories" class="w-64"></el-input>
             </div>
             <el-button type="primary" @click="openAddMemoryDialog()">
                 <el-icon class="mr-1"><plus /></el-icon>添加记忆
             </el-button>
           </div>

           <el-card shadow="never" class="flex-1 flex flex-col">
              <el-table :data="memories" stripe style="width: 100%" height="100%">
                 <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip></el-table-column>
                 <el-table-column prop="concept_id" label="所属概念" width="150"></el-table-column>
                 <el-table-column prop="strength" label="强度" width="100">
                    <template #default="scope">
                        <el-tag :type="getStrengthType(scope.row.strength)">{{ scope.row.strength?.toFixed(2) }}</el-tag>
                    </template>
                 </el-table-column>
                 <el-table-column prop="last_accessed" label="最后访问" width="180">
                    <template #default="scope">
                        {{ formatDate(scope.row.last_accessed) }}
                    </template>
                 </el-table-column>
                 <el-table-column label="操作" width="180" align="right">
                     <template #default="scope">
                         <el-button size="small" @click="editMemory(scope.row)">编辑</el-button>
                         <el-button size="small" type="danger" @click="deleteMemory(scope.row)">删除</el-button>
                     </template>
                 </el-table-column>
              </el-table>
           </el-card>
        </div>

        <!-- Connections View -->
        <div v-if="activeTab === 'connections'" class="h-full flex flex-col p-4 overflow-auto">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-bold">连接管理</h2>
                <el-button type="primary" @click="showAddConnectionDialog = true">
                    <el-icon class="mr-1"><plus /></el-icon>添加连接
                </el-button>
            </div>
            
            <el-card shadow="never" class="flex-1 flex flex-col">
                <el-table :data="connections" stripe style="width: 100%" height="100%">
                    <el-table-column prop="from_concept" label="From 概念" width="200"></el-table-column>
                    <el-table-column width="50" align="center">
                        <template #default>
                            <el-icon><right /></el-icon>
                        </template>
                    </el-table-column>
                    <el-table-column prop="to_concept" label="To 概念" width="200"></el-table-column>
                    <el-table-column prop="strength" label="强度" width="120">
                         <template #default="scope">
                             <el-progress :percentage="scope.row.strength * 100" :show-text="false"></el-progress>
                             <span class="text-xs">{{ scope.row.strength.toFixed(2) }}</span>
                         </template>
                    </el-table-column>
                    <el-table-column label="操作" align="right">
                        <template #default="scope">
                            <el-button size="small" @click="editConnection(scope.row)">调整强度</el-button>
                            <el-button size="small" type="danger" @click="deleteConnection(scope.row)">删除</el-button>
                        </template>
                    </el-table-column>
                </el-table>
            </el-card>
        </div>

        <!-- Impressions View -->
        <div v-if="activeTab === 'impressions'" class="h-full flex flex-col p-4 overflow-auto">
             <div class="flex h-full gap-4">
                 <!-- Left: Person List -->
                 <div class="w-1/4 flex flex-col">
                     <div class="flex justify-between items-center mb-4">
                         <h2 class="text-xl font-bold">人物列表</h2>
                         <el-button size="small" type="primary" icon="Plus" circle @click="showAddImpressionDialog = true"></el-button>
                     </div>
                     <el-card shadow="never" class="flex-1 overflow-auto" :body-style="{ padding: '0' }">
                         <el-menu :default-active="selectedPerson" @select="loadImpressionDetail">
                             <el-menu-item v-for="p in impressionPeople" :key="p.name" :index="p.name">
                                 <span>{{ p.name }}</span>
                             </el-menu-item>
                         </el-menu>
                     </el-card>
                 </div>

                 <!-- Right: Detail -->
                 <div class="flex-1 flex flex-col">
                      <div v-if="selectedPerson" class="h-full flex flex-col">
                          <div class="bg-white dark:bg-dark-panel p-4 rounded shadow-sm mb-4">
                              <div class="flex justify-between items-start">
                                  <div>
                                      <h3 class="text-2xl font-bold mb-2">{{ impressionDetail?.summary?.name || selectedPerson }}</h3>
                                      <div class="text-gray-500 mb-2">{{ impressionDetail?.summary?.summary }}</div>
                                      <div class="flex items-center gap-4 text-sm">
                                          <span class="flex items-center gap-1"><el-icon><star /></el-icon> 好感度: {{ impressionDetail?.summary?.score?.toFixed(2) || 'N/A' }}</span>
                                          <span class="flex items-center gap-1"><el-icon><clock /></el-icon> 更新于: {{ formatDate(impressionDetail?.summary?.last_updated) }}</span>
                                      </div>
                                  </div>
                                  <div class="flex flex-col gap-2">
                                      <div class="flex gap-2">
                                          <el-input-number v-model="scoreDelta" size="small" :step="0.1" :min="-1" :max="1" style="width: 100px"></el-input-number>
                                          <el-button size="small" @click="adjustScore">调整好感</el-button>
                                      </div>
                                  </div>
                              </div>
                          </div>

                          <el-card shadow="never" class="flex-1 flex flex-col" header="印象记录">
                              <el-timeline>
                                  <el-timeline-item
                                    v-for="(mem, index) in impressionDetail?.memories"
                                    :key="index"
                                    :timestamp="formatDate(mem.created_at)"
                                    placement="top"
                                  >
                                    <el-card shadow="hover" :body-style="{ padding: '12px' }">
                                        <div class="font-medium">{{ mem.content }}</div>
                                        <div class="text-xs text-gray-400 mt-1" v-if="mem.details">细节: {{ mem.details }}</div>
                                        <div class="text-xs text-gray-400 mt-1 flex gap-2">
                                            <span v-if="mem.score !== null">Score: {{ mem.score }}</span>
                                        </div>
                                    </el-card>
                                  </el-timeline-item>
                              </el-timeline>
                          </el-card>
                      </div>
                      <div v-else class="h-full flex items-center justify-center text-gray-400">
                          请选择左侧人物查看详情
                      </div>
                 </div>
             </div>
        </div>

      </main>
    </div>

    <!-- Dialogs -->
    
    <!-- Add Concept -->
    <el-dialog v-model="showAddConceptDialog" title="添加概念" width="400px">
        <el-input v-model="newConceptName" placeholder="输入概念名称"></el-input>
        <template #footer>
            <el-button @click="showAddConceptDialog = false">取消</el-button>
            <el-button type="primary" @click="createConcept">确定</el-button>
        </template>
    </el-dialog>

    <!-- Add/Edit Memory -->
    <el-dialog v-model="showMemoryDialog" :title="isEditMemory ? '编辑记忆' : '添加记忆'" width="500px">
        <el-form label-width="80px">
            <el-form-item label="所属概念" v-if="!isEditMemory">
                <el-select v-model="memoryForm.concept_id" filterable allow-create default-first-option placeholder="选择或输入概念" class="w-full">
                    <el-option v-for="c in concepts" :key="c.id" :label="c.name" :value="c.id"></el-option>
                </el-select>
            </el-form-item>
            <el-form-item label="内容">
                <el-input v-model="memoryForm.content" type="textarea" rows="3"></el-input>
            </el-form-item>
            <el-form-item label="细节">
                <el-input v-model="memoryForm.details"></el-input>
            </el-form-item>
            <el-form-item label="参与者">
                <el-input v-model="memoryForm.participants"></el-input>
            </el-form-item>
            <el-form-item label="地点">
                <el-input v-model="memoryForm.location"></el-input>
            </el-form-item>
            <el-form-item label="情感">
                <el-input v-model="memoryForm.emotion"></el-input>
            </el-form-item>
            <el-form-item label="标签">
                <el-input v-model="memoryForm.tags"></el-input>
            </el-form-item>
            <el-form-item label="强度">
                <el-slider v-model="memoryForm.strength" :min="0" :max="1" :step="0.1" show-input></el-slider>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="showMemoryDialog = false">取消</el-button>
            <el-button type="primary" @click="saveMemory">保存</el-button>
        </template>
    </el-dialog>

    <!-- Add Connection -->
    <el-dialog v-model="showAddConnectionDialog" title="添加连接" width="400px">
        <el-form label-width="80px">
            <el-form-item label="From">
                 <el-select v-model="connectionForm.from_concept" filterable placeholder="起始概念" class="w-full">
                     <el-option v-for="c in concepts" :key="c.id" :label="c.name" :value="c.id"></el-option>
                 </el-select>
            </el-form-item>
            <el-form-item label="To">
                 <el-select v-model="connectionForm.to_concept" filterable placeholder="目标概念" class="w-full">
                     <el-option v-for="c in concepts" :key="c.id" :label="c.name" :value="c.id"></el-option>
                 </el-select>
            </el-form-item>
            <el-form-item label="强度">
                <el-slider v-model="connectionForm.strength" :min="0" :max="1" :step="0.1" show-input></el-slider>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="showAddConnectionDialog = false">取消</el-button>
            <el-button type="primary" @click="createConnection">确定</el-button>
        </template>
    </el-dialog>

    <!-- Add Impression -->
    <el-dialog v-model="showAddImpressionDialog" title="添加印象" width="400px">
        <el-form label-width="80px">
             <el-form-item label="人物">
                 <el-input v-model="impressionForm.person"></el-input>
             </el-form-item>
             <el-form-item label="摘要">
                 <el-input v-model="impressionForm.summary" type="textarea"></el-input>
             </el-form-item>
             <el-form-item label="初始好感">
                 <el-input-number v-model="impressionForm.score" :min="0" :max="1" :step="0.1"></el-input-number>
             </el-form-item>
             <el-form-item label="细节">
                 <el-input v-model="impressionForm.details"></el-input>
             </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="showAddImpressionDialog = false">取消</el-button>
            <el-button type="primary" @click="createImpression">确定</el-button>
        </template>
    </el-dialog>

  </div>

  <script src="/static/app.js"></script>
</body>
</html>
"""

DEFAULT_STYLE_CSS = """[v-cloak] {
  display: none;
}

body {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
}

/* Element Plus Dark Mode overrides if necessary */
html.dark .el-card {
    background-color: #242424;
    border-color: #363636;
    color: #e5e7eb;
}

html.dark .el-table {
    --el-table-bg-color: #242424;
    --el-table-tr-bg-color: #242424;
    --el-table-header-bg-color: #2c2c2c;
    --el-table-row-hover-bg-color: #2c2c2c;
    --el-table-border-color: #363636;
    color: #e5e7eb;
}

html.dark .el-table th.el-table__cell {
    background-color: #2c2c2c;
}

html.dark .el-dialog {
    background-color: #242424;
}

html.dark .el-input__wrapper, html.dark .el-textarea__inner {
    background-color: #1a1a1a;
    box-shadow: 0 0 0 1px #363636 inset;
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: #ccc;
    border-radius: 4px;
}
html.dark ::-webkit-scrollbar-thumb {
    background: #555;
}
::-webkit-scrollbar-thumb:hover {
    background: #aaa;
}
html.dark ::-webkit-scrollbar-thumb:hover {
    background: #777;
}
"""

DEFAULT_APP_JS = """const { createApp, ref, reactive, onMounted, watch, computed } = Vue;
const { ElMessage, ElMessageBox, ElNotification } = ElementPlus;

const app = createApp({
    setup() {
        // State
        const state = reactive({
            token: '',
            group: '',
        });

        const groups = ref([]);
        const concepts = ref([]);
        const memories = ref([]);
        const connections = ref([]);
        const impressionPeople = ref([]);
        const impressionDetail = ref(null);

        const activeTab = ref('graph');
        const loading = ref(false);
        const isDark = ref(false);
        const hasTokenInUrl = ref(false);

        // Graph
        const graphLayout = ref('cose');
        const selectedNode = ref(null);
        let cy = null;

        // Dialogs
        const showAddConceptDialog = ref(false);
        const showMemoryDialog = ref(false);
        const showAddConnectionDialog = ref(false);
        const showAddImpressionDialog = ref(false);

        // Forms
        const newConceptName = ref('');
        const searchQuery = ref('');
        const selectedPerson = ref('');
        const scoreDelta = ref(0);

        const memoryForm = reactive({
            id: null,
            concept_id: '',
            content: '',
            details: '',
            participants: '',
            location: '',
            emotion: '',
            tags: '',
            strength: 1.0
        });
        const isEditMemory = ref(false);

        const connectionForm = reactive({
            from_concept: '',
            to_concept: '',
            strength: 1.0
        });

        const impressionForm = reactive({
            person: '',
            summary: '',
            score: 0,
            details: ''
        });

        // --- Helpers ---
        const getHeaders = () => {
            const h = { "Content-Type": "application/json" };
            if (state.token) h["x-access-token"] = state.token;
            return h;
        };

        const api = axios.create();
        api.interceptors.request.use(config => {
            config.headers = { ...config.headers, ...getHeaders() };
            return config;
        });
        api.interceptors.response.use(res => res, err => {
            ElMessage.error(err.response?.data?.error || err.message);
            return Promise.reject(err);
        });

        const formatDate = (ts) => {
            if (!ts) return '-';
            return new Date(ts * 1000).toLocaleString();
        };

        const getStrengthType = (val) => {
            if (val > 0.8) return 'success';
            if (val > 0.5) return 'warning';
            return 'info';
        };

        // --- Actions ---
        const refreshData = async () => {
            loading.value = true;
            try {
                if (!groups.value.length) await loadGroups();
                await Promise.all([
                    loadConcepts(),
                    loadGraph(),
                    loadConnections(), // Pre-load for list view
                    loadImpressions(), // Pre-load for list view
                ]);
                // If on memories tab, load memories
                if (activeTab.value === 'memories') await searchMemories();
            } finally {
                loading.value = false;
            }
        };

        const loadGroups = async () => {
            const { data } = await api.get('/api/groups');
            groups.value = data.groups;
            if (!state.group && groups.value.length > 0) {
                 // state.group = groups.value[0]; // Don't auto select, let user choose or use default empty
            }
        };

        const loadConcepts = async () => {
            const { data } = await api.get(`/api/concepts?group_id=${encodeURIComponent(state.group)}`);
            concepts.value = data.concepts || [];
        };

        const loadGraph = async () => {
            try {
                const { data } = await api.get(`/api/graph?group_id=${encodeURIComponent(state.group)}`);
                if (!cy) initGraph();
                
                const nodes = data.nodes.map(n => ({ data: { id: n.id, label: `${n.name}`, count: n.count } }));
                const edges = data.edges.map(e => ({ 
                    data: { 
                        id: `${e.from_concept}_${e.to_concept}`, 
                        source: e.from_concept, 
                        target: e.to_concept, 
                        weight: e.strength 
                    } 
                }));
                
                cy.elements().remove();
                cy.add({ nodes, edges });
                updateGraphLayout();
            } catch (e) {
                console.error(e);
            }
        };

        const initGraph = () => {
            const container = document.getElementById('cy');
            if (!container) return;
            
            const styleColor = isDark.value ? '#a0cfff' : '#409eff';
            const labelColor = isDark.value ? '#eee' : '#333';

            cy = cytoscape({
                container: container,
                style: [
                    { 
                        selector: 'node', 
                        style: { 
                            'label': 'data(label)', 
                            'background-color': styleColor, 
                            'color': labelColor,
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'font-size': '12px',
                            'width': 'label',
                            'height': 'label',
                            'padding': '10px',
                            'text-wrap': 'wrap',
                            'shape': 'round-rectangle'
                        } 
                    },
                    { 
                        selector: 'edge', 
                        style: { 
                            'width': 2, 
                            'line-color': '#ccc',
                            'target-arrow-shape': 'triangle',
                            'target-arrow-color': '#ccc',
                            'curve-style': 'bezier'
                        } 
                    },
                    {
                        selector: ':selected',
                        style: {
                            'background-color': '#e6a23c',
                            'line-color': '#e6a23c',
                            'target-arrow-color': '#e6a23c'
                        }
                    }
                ]
            });

            cy.on('tap', 'node', (evt) => {
                const node = evt.target;
                selectedNode.value = { id: node.id(), label: node.data('label') };
            });

            cy.on('tap', (evt) => {
                if (evt.target === cy) {
                    selectedNode.value = null;
                }
            });
        };

        const updateGraphLayout = () => {
            if (!cy) return;
            const layout = cy.layout({ 
                name: graphLayout.value, 
                animate: true,
                fit: true,
                padding: 30,
                // Cose specific
                idealEdgeLength: 100,
                nodeOverlap: 20,
                refresh: 20,
                componentSpacing: 100,
                nodeRepulsion: 400000,
                edgeElasticity: 100,
                nestingFactor: 5,
                gravity: 80,
                numIter: 1000,
                initialTemp: 200,
                coolingFactor: 0.95,
                minTemp: 1.0
            });
            layout.run();
        };

        const fitGraph = () => cy && cy.fit();
        const randomizeGraph = () => updateGraphLayout();

        const viewConceptMemories = (conceptId) => {
            searchQuery.value = '';
            activeTab.value = 'memories';
            // Use search mechanism but filter by concept locally or via API if implemented
            // The current API supports concept_id filter in /api/memories
            loadMemoriesByConcept(conceptId);
        };

        const loadMemoriesByConcept = async (conceptId) => {
             const params = new URLSearchParams();
             params.set('group_id', state.group);
             params.set('concept_id', conceptId);
             const { data } = await api.get(`/api/memories?${params}`);
             memories.value = data.memories || [];
        };

        // --- Concepts ---
        const createConcept = async () => {
            if (!newConceptName.value.trim()) return;
            await api.post('/api/concepts', { group_id: state.group, name: newConceptName.value.trim() });
            ElMessage.success('概念已创建');
            showAddConceptDialog.value = false;
            newConceptName.value = '';
            refreshData();
        };

        const selectConcept = (row) => {
            selectedNode.value = { id: row.id, label: row.name };
            activeTab.value = 'graph';
            // Optionally focus on graph node
        };

        const editConcept = async (row) => {
            try {
                const { value } = await ElMessageBox.prompt('请输入新名称', '重命名概念', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    inputValue: row.name,
                });
                await api.put(`/api/concepts/${row.id}`, { group_id: state.group, name: value });
                ElMessage.success('重命名成功');
                refreshData();
            } catch (e) {
                // cancel
            }
        };

        const deleteConcept = async (row) => {
            try {
                await ElMessageBox.confirm('确认删除该概念及其所有关联记忆吗?', '警告', {
                    confirmButtonText: '删除',
                    cancelButtonText: '取消',
                    type: 'warning',
                });
                await api.delete(`/api/concepts/${row.id}?group_id=${encodeURIComponent(state.group)}`);
                ElMessage.success('删除成功');
                refreshData();
            } catch (e) {
                // cancel
            }
        };

        // --- Memories ---
        const searchMemories = async () => {
            // If query is empty, load all (limited by backend default?) or top?
            // Current backend supports listing all if no query but group_id is present
            const params = new URLSearchParams();
            params.set('group_id', state.group);
            if (searchQuery.value) params.set('q', searchQuery.value);
            
            const { data } = await api.get(`/api/memories?${params}`);
            memories.value = data.memories || [];
        };

        const openAddMemoryDialog = () => {
            isEditMemory.value = false;
            Object.assign(memoryForm, {
                id: null,
                concept_id: '',
                content: '',
                details: '',
                participants: '',
                location: '',
                emotion: '',
                tags: '',
                strength: 1.0
            });
            showMemoryDialog.value = true;
        };

        const editMemory = (row) => {
            isEditMemory.value = true;
            Object.assign(memoryForm, row);
            showMemoryDialog.value = true;
        };

        const saveMemory = async () => {
            if (!memoryForm.content) return ElMessage.warning('内容不能为空');
            
            if (isEditMemory.value) {
                await api.put(`/api/memories/${memoryForm.id}`, { ...memoryForm, group_id: state.group });
            } else {
                if (!memoryForm.concept_id) return ElMessage.warning('必须选择一个概念');
                // Check if concept_id is a name (for create-new)
                const body = { ...memoryForm, group_id: state.group };
                
                // If user typed a new concept name in the select box
                const existing = concepts.value.find(c => c.id === memoryForm.concept_id);
                if (!existing) {
                    body.concept_name = memoryForm.concept_id; // use as name
                    body.concept_id = '';
                }

                await api.post('/api/memories', body);
            }
            
            ElMessage.success('保存成功');
            showMemoryDialog.value = false;
            if (activeTab.value === 'memories') searchMemories();
            else refreshData();
        };

        const deleteMemory = async (row) => {
            try {
                await ElMessageBox.confirm('确认删除这条记忆吗?', '警告', { type: 'warning' });
                await api.delete(`/api/memories/${row.id}?group_id=${encodeURIComponent(state.group)}`);
                ElMessage.success('删除成功');
                if (activeTab.value === 'memories') searchMemories();
                else refreshData();
            } catch (e) {}
        };

        // --- Connections ---
        const loadConnections = async () => {
            const { data } = await api.get(`/api/connections?group_id=${encodeURIComponent(state.group)}`);
            connections.value = data.connections || [];
        };

        const createConnection = async () => {
            if (!connectionForm.from_concept || !connectionForm.to_concept) return ElMessage.warning('请选择概念');
            await api.post('/api/connections', { ...connectionForm, group_id: state.group });
            ElMessage.success('连接已创建');
            showAddConnectionDialog.value = false;
            loadConnections();
            loadGraph(); // Update graph
        };

        const editConnection = async (row) => {
             try {
                const { value } = await ElMessageBox.prompt('请输入新强度 (0-1)', '调整强度', {
                    inputValue: row.strength,
                    inputType: 'number',
                    inputPattern: /^(0(\.\d+)?|1(\.0+)?)$/,
                    inputErrorMessage: '请输入 0 到 1 之间的数字'
                });
                await api.put(`/api/connections/${row.id}`, { group_id: state.group, strength: value });
                ElMessage.success('更新成功');
                loadConnections();
                loadGraph();
             } catch (e) {}
        };

        const deleteConnection = async (row) => {
            try {
                await ElMessageBox.confirm('确认删除该连接吗?', '警告', { type: 'warning' });
                await api.delete(`/api/connections/${row.id}?group_id=${encodeURIComponent(state.group)}`);
                ElMessage.success('删除成功');
                loadConnections();
                loadGraph();
            } catch (e) {}
        };

        // --- Impressions ---
        const loadImpressions = async () => {
            const { data } = await api.get(`/api/impressions?group_id=${encodeURIComponent(state.group)}`);
            impressionPeople.value = data.people || [];
        };

        const loadImpressionDetail = async (name) => {
            selectedPerson.value = name;
            const params = new URLSearchParams();
            params.set('group_id', state.group);
            params.set('person', name);
            const { data } = await api.get(`/api/impressions?${params}`);
            impressionDetail.value = data;
        };

        const createImpression = async () => {
            if (!impressionForm.person || !impressionForm.summary) return ElMessage.warning('请填写人物和摘要');
            await api.post('/api/impressions', { ...impressionForm, group_id: state.group });
            ElMessage.success('印象已创建');
            showAddImpressionDialog.value = false;
            Object.assign(impressionForm, { person:'', summary:'', score:0, details:'' });
            loadImpressions();
            if (impressionForm.person === selectedPerson.value) loadImpressionDetail(selectedPerson.value);
        };

        const adjustScore = async () => {
             if (!selectedPerson.value) return;
             await api.put(`/api/impressions/${encodeURIComponent(selectedPerson.value)}/score`, {
                 group_id: state.group,
                 delta: scoreDelta.value
             });
             ElMessage.success('好感度已调整');
             scoreDelta.value = 0;
             loadImpressionDetail(selectedPerson.value);
        };

        // --- UI/Theme ---
        const toggleTheme = () => {
            isDark.value = !isDark.value;
            if (isDark.value) {
                document.documentElement.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            } else {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('theme', 'light');
            }
            // Refresh graph style
            if (cy) {
                const styleColor = isDark.value ? '#a0cfff' : '#409eff';
                const labelColor = isDark.value ? '#eee' : '#333';
                cy.style().selector('node').style({ 'background-color': styleColor, 'color': labelColor }).update();
            }
        };

        const checkUrlToken = () => {
            const params = new URLSearchParams(window.location.search);
            const t = params.get('token');
            if (t) {
                state.token = t;
                hasTokenInUrl.value = true;
            }
        };

        // Init
        onMounted(() => {
            // Theme init
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                isDark.value = true;
                document.documentElement.classList.add('dark');
            }

            checkUrlToken();
            refreshData();
        });
        
        watch(activeTab, (val) => {
             if (val === 'graph') {
                 // Need wait for view update
                 setTimeout(() => {
                     if (cy) {
                         cy.resize();
                         cy.fit();
                     } else {
                         initGraph();
                         loadGraph();
                     }
                 }, 100);
             } else if (val === 'memories') {
                 if (memories.value.length === 0) searchMemories();
             }
        });

        return {
            state,
            groups,
            concepts,
            memories,
            connections,
            impressionPeople,
            impressionDetail,
            activeTab,
            loading,
            isDark,
            hasTokenInUrl,
            graphLayout,
            selectedNode,
            showAddConceptDialog,
            showMemoryDialog,
            showAddConnectionDialog,
            showAddImpressionDialog,
            newConceptName,
            searchQuery,
            selectedPerson,
            scoreDelta,
            memoryForm,
            isEditMemory,
            connectionForm,
            impressionForm,
            formatDate,
            getStrengthType,
            refreshData,
            toggleTheme,
            // Actions
            updateGraphLayout,
            fitGraph,
            randomizeGraph,
            viewConceptMemories,
            createConcept,
            selectConcept,
            editConcept,
            deleteConcept,
            searchMemories,
            openAddMemoryDialog,
            editMemory,
            saveMemory,
            deleteMemory,
            createConnection,
            editConnection,
            deleteConnection,
            loadImpressionDetail,
            createImpression,
            adjustScore
        };
    }
});

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

app.use(ElementPlus);
app.mount('#app');
"""
