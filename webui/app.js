const { createApp, ref, reactive, onMounted, watch, computed } = Vue;
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
