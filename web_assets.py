"""默认的 Memora Web 前端静态资源。

当插件在打包或部署时遗漏了 webui 目录中的文件时，
web_server 会使用这里的内容在运行目录下自动生成
index.html、style.css 和 app.js，以保证 Web 管理界面可用。

重构版本：iOS 26 玻璃拟态风格 + 图谱中心化交互设计
"""

DEFAULT_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memora Connect</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
  <!-- 顶部玻璃拟态导航栏 -->
  <nav class="glass-nav">
    <div class="nav-brand">
      <svg class="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 6v6l4 2"/>
      </svg>
      <h1>Memora Connect</h1>
    </div>
    <div class="nav-controls">
      <div class="control-group">
        <label for="tokenInput">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
        </label>
        <input type="password" id="tokenInput" placeholder="访问令牌" class="glass-input">
      </div>
      <div class="control-group">
        <label for="groupSelect">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
        </label>
        <select id="groupSelect" class="glass-select"></select>
      </div>
      <button id="refreshBtn" class="glass-button" title="刷新数据">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
      <button id="themeToggle" class="glass-button" title="切换主题">
        <svg class="theme-icon sun" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/>
          <line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
        <svg class="theme-icon moon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      </button>
      <button id="settingsBtn" class="glass-button" title="设置">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 1v6m0 6v6M5.64 5.64l4.24 4.24m4.24 4.24l4.24 4.24M1 12h6m6 0h6M5.64 18.36l4.24-4.24m4.24-4.24l4.24-4.24"/>
        </svg>
      </button>
    </div>
  </nav>

  <!-- 主容器 -->
  <main class="main-container">
    <!-- 图谱画布 -->
    <div id="graphCanvas" class="graph-canvas">
      <svg id="graphSvg"></svg>
      <canvas id="graphBackdrop"></canvas>
      
      <!-- 图谱控制浮层 -->
      <div class="graph-controls glass-panel">
        <button id="zoomIn" class="icon-button" title="放大">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            <line x1="11" y1="8" x2="11" y2="14"/>
            <line x1="8" y1="11" x2="14" y2="11"/>
          </svg>
        </button>
        <button id="zoomOut" class="icon-button" title="缩小">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            <line x1="8" y1="11" x2="14" y2="11"/>
          </svg>
        </button>
        <button id="resetZoom" class="icon-button" title="重置视图">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
          </svg>
        </button>
        <button id="centerGraph" class="icon-button" title="居中">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="1"/>
            <circle cx="12" cy="12" r="5"/>
            <circle cx="12" cy="12" r="9"/>
          </svg>
        </button>
        <div class="control-divider"></div>
        <button id="layoutCircle" class="icon-button" title="环形布局">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="10"/>
          </svg>
        </button>
        <button id="layoutForce" class="icon-button active" title="力导向布局">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </button>
        <button id="layoutTree" class="icon-button" title="树形布局">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <line x1="12" y1="2" x2="12" y2="8"/>
            <line x1="12" y1="8" x2="8" y2="12"/>
            <line x1="12" y1="8" x2="16" y2="12"/>
            <line x1="8" y1="12" x2="8" y2="16"/>
            <line x1="16" y1="12" x2="16" y2="16"/>
          </svg>
        </button>
      </div>

      <!-- 图谱统计浮层 -->
      <div class="graph-stats glass-panel">
        <div class="stat-item">
          <span class="stat-label">节点</span>
          <span class="stat-value" id="nodeCount">0</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">连接</span>
          <span class="stat-value" id="edgeCount">0</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">记忆</span>
          <span class="stat-value" id="memoryCount">0</span>
        </div>
      </div>

      <!-- 搜索浮层 -->
      <div class="graph-search glass-panel">
        <input type="text" id="graphSearch" class="glass-input" placeholder="搜索概念或记忆...">
        <div id="searchResults" class="search-results"></div>
      </div>
    </div>

    <!-- 左侧边栏 -->
    <aside id="leftSidebar" class="sidebar left glass-panel">
      <div class="sidebar-header">
        <h2>概念列表</h2>
        <button class="sidebar-toggle" data-target="left">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
      </div>
      <div class="sidebar-content">
        <div class="action-group">
          <input type="text" id="newConceptName" class="glass-input" placeholder="新概念名称">
          <button id="addConceptBtn" class="glass-button primary">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            <span>添加</span>
          </button>
        </div>
        <div id="conceptList" class="item-list"></div>
      </div>
    </aside>

    <!-- 右侧边栏 -->
    <aside id="rightSidebar" class="sidebar right glass-panel">
      <div class="sidebar-header">
        <button class="sidebar-toggle" data-target="right">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
        <h2>详情面板</h2>
      </div>
      <div class="sidebar-content">
        <div class="tabs">
          <button class="tab-button active" data-tab="memories">记忆</button>
          <button class="tab-button" data-tab="connections">连接</button>
          <button class="tab-button" data-tab="impressions">印象</button>
        </div>
        
        <!-- 记忆标签页 -->
        <div id="memoriesTab" class="tab-content active">
          <div class="action-group vertical">
            <input type="text" id="memContent" class="glass-input" placeholder="记忆内容">
            <input type="text" id="memDetails" class="glass-input" placeholder="详细描述">
            <div class="input-row">
              <input type="text" id="memParticipants" class="glass-input" placeholder="参与者">
              <input type="text" id="memLocation" class="glass-input" placeholder="地点">
            </div>
            <div class="input-row">
              <input type="text" id="memTags" class="glass-input" placeholder="标签">
              <input type="text" id="memEmotion" class="glass-input" placeholder="情感">
            </div>
            <div class="input-row">
              <input type="number" id="memStrength" class="glass-input" placeholder="强度" step="0.1" min="0" max="1">
              <button id="addMemoryBtn" class="glass-button primary">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17 21 17 13 7 13 7 21"/>
                  <polyline points="7 3 7 8 15 8"/>
                </svg>
                <span>添加记忆</span>
              </button>
            </div>
          </div>
          <div id="memoryList" class="item-list"></div>
        </div>

        <!-- 连接标签页 -->
        <div id="connectionsTab" class="tab-content">
          <div class="action-group vertical">
            <div class="input-row">
              <input type="text" id="connFrom" class="glass-input" placeholder="源概念ID">
              <input type="text" id="connTo" class="glass-input" placeholder="目标概念ID">
            </div>
            <div class="input-row">
              <input type="number" id="connStrength" class="glass-input" placeholder="强度" value="1" step="0.1" min="0" max="1">
              <button id="addConnBtn" class="glass-button primary">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                <span>添加连接</span>
              </button>
            </div>
          </div>
          <div id="connList" class="item-list"></div>
        </div>

        <!-- 印象标签页 -->
        <div id="impressionsTab" class="tab-content">
          <div class="action-group vertical">
            <input type="text" id="impPerson" class="glass-input" placeholder="人物">
            <input type="text" id="impSummary" class="glass-input" placeholder="印象摘要">
            <div class="input-row">
              <input type="number" id="impScore" class="glass-input" placeholder="好感度" step="0.1" min="0" max="1">
              <input type="text" id="impDetails" class="glass-input" placeholder="详细描述">
            </div>
            <button id="addImpBtn" class="glass-button primary full-width">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              <span>记录印象</span>
            </button>
          </div>
          <div id="impList" class="item-list"></div>
          <div id="impDetail" class="impression-detail"></div>
          <div class="action-group">
            <input type="number" id="impDelta" class="glass-input" placeholder="调整量" step="0.1" min="-1" max="1">
            <button id="impAdjustBtn" class="glass-button">调整好感度</button>
          </div>
        </div>
      </div>
    </aside>
  </main>

  <!-- 上下文菜单 -->
  <div id="contextMenu" class="context-menu glass-panel" style="display: none;"></div>

  <!-- 节点详情浮窗 -->
  <div id="nodeTooltip" class="node-tooltip glass-panel" style="display: none;"></div>

  <!-- 通知容器 -->
  <div id="notifications" class="notifications"></div>

  <script src="/static/app.js"></script>
</body>
</html>
"""

DEFAULT_STYLE_CSS = """/* ========================================
   Memora Connect - iOS 26 玻璃拟态风格
   ======================================== */

:root {
  /* 颜色系统 - 亮色主题 */
  --color-primary: #007AFF;
  --color-primary-light: #4DA2FF;
  --color-primary-dark: #0051D5;
  --color-secondary: #5856D6;
  --color-success: #34C759;
  --color-warning: #FF9500;
  --color-danger: #FF3B30;
  
  --color-bg-base: #F2F2F7;
  --color-bg-elevated: #FFFFFF;
  --color-bg-overlay: rgba(255, 255, 255, 0.8);
  
  --color-text-primary: #000000;
  --color-text-secondary: #3C3C43;
  --color-text-tertiary: #8E8E93;
  
  --color-border: rgba(0, 0, 0, 0.1);
  --color-divider: rgba(0, 0, 0, 0.05);
  
  /* 玻璃拟态效果 */
  --glass-bg: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.18);
  --glass-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
  --glass-blur: 20px;
  
  /* 间距 */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  /* 圆角 */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  
  /* 动画 */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-base: 250ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 350ms cubic-bezier(0.4, 0, 0.2, 1);
  
  /* 图谱配色 */
  --node-color-default: #007AFF;
  --node-color-selected: #5856D6;
  --node-color-hover: #4DA2FF;
  --edge-color-default: rgba(142, 142, 147, 0.5);
  --edge-color-strong: rgba(88, 86, 214, 0.8);
}

/* 暗色主题 */
[data-theme="dark"] {
  --color-bg-base: #000000;
  --color-bg-elevated: #1C1C1E;
  --color-bg-overlay: rgba(28, 28, 30, 0.8);
  
  --color-text-primary: #FFFFFF;
  --color-text-secondary: #EBEBF5;
  --color-text-tertiary: #8E8E93;
  
  --color-border: rgba(255, 255, 255, 0.15);
  --color-divider: rgba(255, 255, 255, 0.08);
  
  --glass-bg: rgba(28, 28, 30, 0.72);
  --glass-border: rgba(255, 255, 255, 0.08);
  --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  
  --node-color-default: #0A84FF;
  --node-color-selected: #5E5CE6;
  --node-color-hover: #409CFF;
  --edge-color-default: rgba(142, 142, 147, 0.3);
  --edge-color-strong: rgba(94, 92, 230, 0.6);
}

/* ========================================
   基础样式
   ======================================== */

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', 
               'Helvetica Neue', Arial, sans-serif;
  background: var(--color-bg-base);
  color: var(--color-text-primary);
  overflow: hidden;
  width: 100vw;
  height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ========================================
   顶部导航栏
   ======================================== */

.glass-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-lg);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
  border-bottom: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  position: relative;
  z-index: 1000;
  height: 60px;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.logo-icon {
  width: 28px;
  height: 28px;
  color: var(--color-primary);
  stroke-width: 2;
}

.nav-brand h1 {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.nav-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.control-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.control-group label svg {
  width: 18px;
  height: 18px;
  color: var(--color-text-tertiary);
  stroke-width: 2;
}

/* ========================================
   玻璃拟态组件
   ======================================== */

.glass-panel {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--glass-shadow);
}

.glass-input,
.glass-select {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  font-size: 14px;
  color: var(--color-text-primary);
  outline: none;
  transition: all var(--transition-fast);
  min-width: 120px;
}

.glass-input:focus,
.glass-select:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.1);
}

.glass-input::placeholder {
  color: var(--color-text-tertiary);
}

.glass-button {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 8px 16px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  outline: none;
}

.glass-button:hover {
  background: var(--color-bg-overlay);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.glass-button:active {
  transform: translateY(0);
}

.glass-button.primary {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.glass-button.primary:hover {
  background: var(--color-primary-light);
}

.glass-button svg {
  width: 18px;
  height: 18px;
  stroke-width: 2;
}

.icon-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  outline: none;
}

.icon-button:hover {
  background: var(--color-bg-overlay);
  transform: scale(1.05);
}

.icon-button.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.icon-button svg {
  width: 20px;
  height: 20px;
  stroke: currentColor;
  stroke-width: 2;
}

/* 主题切换按钮 */
.theme-icon {
  width: 20px;
  height: 20px;
  stroke-width: 2;
  transition: all var(--transition-base);
}

.theme-icon.moon {
  display: none;
}

[data-theme="dark"] .theme-icon.sun {
  display: none;
}

[data-theme="dark"] .theme-icon.moon {
  display: block;
}

/* ========================================
   主容器
   ======================================== */

.main-container {
  display: flex;
  width: 100%;
  height: calc(100vh - 60px);
  position: relative;
  overflow: hidden;
}

/* ========================================
   图谱画布
   ======================================== */

.graph-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
}

#graphSvg {
  width: 100%;
  height: 100%;
  cursor: grab;
}

#graphSvg:active {
  cursor: grabbing;
}

#graphBackdrop {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: -1;
}

/* 图谱控制浮层 */
.graph-controls {
  position: absolute;
  bottom: var(--spacing-lg);
  right: var(--spacing-lg);
  display: flex;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs);
}

.control-divider {
  width: 1px;
  background: var(--color-divider);
  margin: 0 var(--spacing-xs);
}

/* 图谱统计浮层 */
.graph-stats {
  position: absolute;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  display: flex;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
}

.stat-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}

/* 搜索浮层 */
.graph-search {
  position: absolute;
  top: var(--spacing-lg);
  left: 50%;
  transform: translateX(-50%);
  min-width: 400px;
  max-width: 600px;
  padding: var(--spacing-sm);
}

.graph-search .glass-input {
  width: 100%;
  padding: 10px 16px;
  font-size: 15px;
}

.search-results {
  margin-top: var(--spacing-sm);
  max-height: 300px;
  overflow-y: auto;
  display: none;
}

.search-results:not(:empty) {
  display: block;
}

.search-result-item {
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.search-result-item:hover {
  background: var(--color-bg-overlay);
}

.search-result-title {
  font-weight: 500;
  color: var(--color-text-primary);
}

.search-result-desc {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

/* ========================================
   侧边栏
   ======================================== */

.sidebar {
  width: 360px;
  height: 100%;
  display: flex;
  flex-direction: column;
  transition: transform var(--transition-base);
  position: relative;
  z-index: 100;
}

.sidebar.left {
  border-right: 1px solid var(--glass-border);
}

.sidebar.right {
  border-left: 1px solid var(--glass-border);
}

.sidebar.collapsed.left {
  transform: translateX(-100%);
}

.sidebar.collapsed.right {
  transform: translateX(100%);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-divider);
}

.sidebar-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.sidebar-toggle {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--color-text-secondary);
}

.sidebar-toggle:hover {
  background: var(--color-bg-overlay);
  color: var(--color-text-primary);
}

.sidebar-toggle svg {
  width: 20px;
  height: 20px;
  stroke-width: 2;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-md);
}

/* 自定义滚动条 */
.sidebar-content::-webkit-scrollbar,
.search-results::-webkit-scrollbar,
.item-list::-webkit-scrollbar {
  width: 6px;
}

.sidebar-content::-webkit-scrollbar-track,
.search-results::-webkit-scrollbar-track,
.item-list::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-content::-webkit-scrollbar-thumb,
.search-results::-webkit-scrollbar-thumb,
.item-list::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}

.sidebar-content::-webkit-scrollbar-thumb:hover,
.search-results::-webkit-scrollbar-thumb:hover,
.item-list::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-tertiary);
}

/* ========================================
   标签页
   ======================================== */

.tabs {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-xs);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
}

.tab-button {
  flex: 1;
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.tab-button:hover {
  background: var(--color-bg-overlay);
  color: var(--color-text-primary);
}

.tab-button.active {
  background: var(--color-primary);
  color: white;
}

.tab-content {
  display: none;
}

.tab-content.active {
  display: block;
}

/* ========================================
   表单与列表
   ======================================== */

.action-group {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.action-group.vertical {
  flex-direction: column;
}

.input-row {
  display: flex;
  gap: var(--spacing-sm);
}

.input-row .glass-input {
  flex: 1;
}

.glass-button.full-width {
  width: 100%;
  justify-content: center;
}

.item-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  max-height: 400px;
  overflow-y: auto;
}

.list-item {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
  cursor: pointer;
}

.list-item:hover {
  background: var(--color-bg-overlay);
  transform: translateX(2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.list-item.selected {
  border-color: var(--color-primary);
  background: rgba(0, 122, 255, 0.05);
}

.list-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-xs);
}

.list-item-title {
  font-weight: 600;
  color: var(--color-text-primary);
  font-size: 15px;
}

.list-item-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.list-item-actions button {
  padding: 4px 8px;
  font-size: 12px;
  border-radius: var(--radius-sm);
}

.list-item-body {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.list-item-meta {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-xs);
}

/* ========================================
   上下文菜单
   ======================================== */

.context-menu {
  position: fixed;
  min-width: 180px;
  padding: var(--spacing-xs);
  z-index: 10000;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
  font-size: 14px;
  color: var(--color-text-primary);
}

.context-menu-item:hover {
  background: var(--color-bg-overlay);
}

.context-menu-item.danger {
  color: var(--color-danger);
}

.context-menu-item svg {
  width: 16px;
  height: 16px;
  stroke-width: 2;
}

.context-menu-divider {
  height: 1px;
  background: var(--color-divider);
  margin: var(--spacing-xs) 0;
}

/* ========================================
   节点提示框
   ======================================== */

.node-tooltip {
  position: fixed;
  max-width: 300px;
  padding: var(--spacing-md);
  z-index: 9999;
  pointer-events: none;
}

.tooltip-header {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: var(--spacing-sm);
  color: var(--color-text-primary);
}

.tooltip-content {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.tooltip-meta {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--color-divider);
}

.tooltip-meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tooltip-meta-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.tooltip-meta-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
}

/* ========================================
   通知系统
   ======================================== */

.notifications {
  position: fixed;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  z-index: 10001;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  pointer-events: none;
}

.notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--glass-shadow);
  min-width: 300px;
  pointer-events: all;
  animation: slideInRight var(--transition-base);
}

@keyframes slideInRight {
  from {
    transform: translateX(400px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.notification.success {
  border-left: 3px solid var(--color-success);
}

.notification.error {
  border-left: 3px solid var(--color-danger);
}

.notification.warning {
  border-left: 3px solid var(--color-warning);
}

.notification.info {
  border-left: 3px solid var(--color-primary);
}

.notification-icon svg {
  width: 20px;
  height: 20px;
  stroke-width: 2;
}

.notification-content {
  flex: 1;
}

.notification-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-text-primary);
}

.notification-message {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

/* ========================================
   印象详情
   ======================================== */

.impression-detail {
  padding: var(--spacing-md);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
}

.impression-detail h4 {
  font-size: 16px;
  margin-bottom: var(--spacing-sm);
  color: var(--color-text-primary);
}

.impression-detail ul {
  list-style: none;
  padding: 0;
}

.impression-detail li {
  padding: var(--spacing-xs) 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

/* ========================================
   响应式设计
   ======================================== */

@media (max-width: 1024px) {
  .sidebar {
    width: 320px;
  }
  
  .graph-search {
    min-width: 300px;
  }
}

@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    top: 60px;
    bottom: 0;
    z-index: 200;
  }
  
  .sidebar.left {
    left: 0;
  }
  
  .sidebar.right {
    right: 0;
  }
  
  .graph-search {
    min-width: 250px;
  }
  
  .nav-controls {
    flex-wrap: wrap;
  }
}

/* ========================================
   性能优化
   ======================================== */

/* 减少重绘 */
.sidebar,
.glass-panel,
.list-item {
  will-change: transform;
}

/* GPU加速 */
.icon-button,
.glass-button,
.tab-button {
  transform: translateZ(0);
}

/* 减少动画计算 */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
"""

DEFAULT_APP_JS = """// ========================================
// Memora Connect - 现代化图谱交互脚本
// ========================================

// 全局状态管理
const state = {
  group: "",
  token: "",
  concepts: [],
  memories: [],
  connections: [],
  impressions: [],
  selectedConceptId: null,
  selectedPerson: null,
  graphData: { nodes: [], edges: [] },
  theme: localStorage.getItem('theme') || 'light',
  layoutMode: 'force'
};

// D3图谱实例
let graphSimulation = null;
let graphSvg = null;
let graphG = null;
let zoom = null;

// ========================================
// 工具函数
// ========================================

function qs(sel) { 
  return document.querySelector(sel); 
}

function qsa(sel) { 
  return document.querySelectorAll(sel); 
}

function headers() {
  const h = {"Content-Type": "application/json"};
  if (state.token) h["x-access-token"] = state.token;
  return h;
}

async function fetchJson(url, opts = {}) {
  try {
    const res = await fetch(url, {headers: headers(), ...opts});
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (error) {
    showNotification('错误', error.message, 'error');
    throw error;
  }
}

// 防抖函数
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// 节流函数
function throttle(func, limit) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

// ========================================
// 通知系统
// ========================================

function showNotification(title, message, type = 'info') {
  const container = qs('#notifications');
  const notification = document.createElement('div');
  notification.className = `notification ${type}`;
  
  const icons = {
    success: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    error: '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    warning: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'
  };
  
  notification.innerHTML = `
    <div class="notification-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        ${icons[type]}
      </svg>
    </div>
    <div class="notification-content">
      <div class="notification-title">${title}</div>
      <div class="notification-message">${message}</div>
    </div>
  `;
  
  container.appendChild(notification);
  
  setTimeout(() => {
    notification.style.animation = 'slideInRight 250ms reverse';
    setTimeout(() => notification.remove(), 250);
  }, 3000);
}

// ========================================
// 主题切换
// ========================================

function initTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  qs('#themeToggle')?.addEventListener('click', () => {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('theme', state.theme);
    if (graphSimulation) {
      updateGraphTheme();
    }
  });
}

function updateGraphTheme() {
  const isDark = state.theme === 'dark';
  graphG.selectAll('.node circle')
    .attr('fill', d => d.id === state.selectedConceptId ? 
      (isDark ? '#5E5CE6' : '#5856D6') : 
      (isDark ? '#0A84FF' : '#007AFF'));
  graphG.selectAll('.edge')
    .attr('stroke', d => d.strength > 0.5 ? 
      (isDark ? 'rgba(94, 92, 230, 0.6)' : 'rgba(88, 86, 214, 0.8)') : 
      (isDark ? 'rgba(142, 142, 147, 0.3)' : 'rgba(142, 142, 147, 0.5)'));
}

// ========================================
// 侧边栏控制
// ========================================

function initSidebar() {
  qsa('.sidebar-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.target;
      const sidebar = qs(`.sidebar.${target}`);
      sidebar.classList.toggle('collapsed');
      
      // 更新箭头方向
      const svg = btn.querySelector('svg polyline');
      if (sidebar.classList.contains('collapsed')) {
        svg.setAttribute('points', target === 'left' ? '9 18 15 12 9 6' : '15 18 9 12 15 6');
      } else {
        svg.setAttribute('points', target === 'left' ? '15 18 9 12 15 6' : '9 18 15 12 9 6');
      }
    });
  });
}

// ========================================
// 标签页切换
// ========================================

function initTabs() {
  qsa('.tab-button').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabName = btn.dataset.tab;
      
      // 切换按钮状态
      qsa('.tab-button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      // 切换内容
      qsa('.tab-content').forEach(c => c.classList.remove('active'));
      qs(`#${tabName}Tab`).classList.add('active');
    });
  });
}

// ========================================
// D3力导向图初始化
// ========================================

function initGraph() {
  const container = qs('#graphCanvas');
  const width = container.clientWidth;
  const height = container.clientHeight;
  
  // 创建SVG
  graphSvg = d3.select('#graphSvg')
    .attr('width', width)
    .attr('height', height);
  
  // 创建画布背景
  const canvas = qs('#graphBackdrop');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  
  // 渐变背景
  const gradient = ctx.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, state.theme === 'dark' ? '#000000' : '#F2F2F7');
  gradient.addColorStop(1, state.theme === 'dark' ? '#1C1C1E' : '#E5E5EA');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
  
  // 创建缩放
  zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => {
      graphG.attr('transform', event.transform);
    });
  
  graphSvg.call(zoom);
  
  // 创建容器组
  graphG = graphSvg.append('g');
  
  // 定义箭头标记
  graphSvg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '-0 -5 10 10')
    .attr('refX', 25)
    .attr('refY', 0)
    .attr('orient', 'auto')
    .attr('markerWidth', 8)
    .attr('markerHeight', 8)
    .append('svg:path')
    .attr('d', 'M 0,-5 L 10,0 L 0,5')
    .attr('fill', '#8E8E93');
  
  // 监听窗口大小变化
  window.addEventListener('resize', debounce(() => {
    const newWidth = container.clientWidth;
    const newHeight = container.clientHeight;
    graphSvg.attr('width', newWidth).attr('height', newHeight);
    canvas.width = newWidth;
    canvas.height = newHeight;
    if (graphSimulation) {
      graphSimulation.force('center', d3.forceCenter(newWidth / 2, newHeight / 2));
      graphSimulation.alpha(0.3).restart();
    }
  }, 250));
}

// ========================================
// 图谱渲染
// ========================================

function renderGraph(data) {
  if (!data || !data.nodes || !data.edges) return;
  
  state.graphData = data;
  const width = qs('#graphCanvas').clientWidth;
  const height = qs('#graphCanvas').clientHeight;
  
  // 更新统计
  qs('#nodeCount').textContent = data.nodes.length;
  qs('#edgeCount').textContent = data.edges.length;
  
  // 清空现有内容
  graphG.selectAll('*').remove();
  
  // 创建力导向模拟
  graphSimulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges)
      .id(d => d.id)
      .distance(d => 100 / (d.strength + 0.1)))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(30));
  
  // 绘制连接线
  const link = graphG.append('g')
    .selectAll('line')
    .data(data.edges)
    .join('line')
    .attr('class', 'edge')
    .attr('stroke', d => d.strength > 0.5 ? 
      (state.theme === 'dark' ? 'rgba(94, 92, 230, 0.6)' : 'rgba(88, 86, 214, 0.8)') : 
      (state.theme === 'dark' ? 'rgba(142, 142, 147, 0.3)' : 'rgba(142, 142, 147, 0.5)'))
    .attr('stroke-width', d => Math.max(1, d.strength * 4))
    .attr('marker-end', 'url(#arrowhead)')
    .style('cursor', 'pointer')
    .on('contextmenu', (event, d) => {
      event.preventDefault();
      showEdgeContextMenu(event, d);
    });
  
  // 绘制节点组
  const node = graphG.append('g')
    .selectAll('g')
    .data(data.nodes)
    .join('g')
    .attr('class', 'node')
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended))
    .on('click', (event, d) => {
      event.stopPropagation();
      selectNode(d);
    })
    .on('contextmenu', (event, d) => {
      event.preventDefault();
      showNodeContextMenu(event, d);
    })
    .on('mouseover', throttle((event, d) => {
      showNodeTooltip(event, d);
      // 高亮相连节点
      highlightConnectedNodes(d);
    }, 100))
    .on('mouseout', () => {
      hideNodeTooltip();
      resetNodeHighlight();
    });
  
  // 节点圆圈
  node.append('circle')
    .attr('r', d => Math.max(15, Math.min(30, Math.sqrt(d.count) * 3)))
    .attr('fill', d => d.id === state.selectedConceptId ? 
      (state.theme === 'dark' ? '#5E5CE6' : '#5856D6') : 
      (state.theme === 'dark' ? '#0A84FF' : '#007AFF'))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)
    .style('filter', 'drop-shadow(0 2px 8px rgba(0, 0, 0, 0.15))');
  
  // 节点标签
  node.append('text')
    .text(d => d.name)
    .attr('text-anchor', 'middle')
    .attr('dy', d => Math.max(15, Math.min(30, Math.sqrt(d.count) * 3)) + 15)
    .attr('fill', state.theme === 'dark' ? '#FFFFFF' : '#000000')
    .attr('font-size', '12px')
    .attr('font-weight', '500')
    .style('pointer-events', 'none')
    .style('user-select', 'none');
  
  // 记忆数量标签
  node.append('text')
    .text(d => d.count)
    .attr('text-anchor', 'middle')
    .attr('dy', 5)
    .attr('fill', '#fff')
    .attr('font-size', '11px')
    .attr('font-weight', '600')
    .style('pointer-events', 'none')
    .style('user-select', 'none');
  
  // 更新位置
  graphSimulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

// 拖拽事件
function dragstarted(event, d) {
  if (!event.active) graphSimulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}

function dragged(event, d) {
  d.fx = event.x;
  d.fy = event.y;
}

function dragended(event, d) {
  if (!event.active) graphSimulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}

// 选中节点
function selectNode(d) {
  state.selectedConceptId = d.id;
  
  // 更新节点样式
  graphG.selectAll('.node circle')
    .attr('fill', node => node.id === d.id ? 
      (state.theme === 'dark' ? '#5E5CE6' : '#5856D6') : 
      (state.theme === 'dark' ? '#0A84FF' : '#007AFF'));
  
  // 加载记忆
  loadMemories();
  renderConcepts();
  
  showNotification('已选中', `概念: ${d.name}`, 'info');
}

// 高亮相连节点
function highlightConnectedNodes(d) {
  const connectedIds = new Set();
  state.graphData.edges.forEach(e => {
    if (e.source.id === d.id) connectedIds.add(e.target.id);
    if (e.target.id === d.id) connectedIds.add(e.source.id);
  });
  
  graphG.selectAll('.node circle')
    .style('opacity', node => node.id === d.id || connectedIds.has(node.id) ? 1 : 0.3);
  
  graphG.selectAll('.edge')
    .style('opacity', edge => 
      edge.source.id === d.id || edge.target.id === d.id ? 1 : 0.1);
}

function resetNodeHighlight() {
  graphG.selectAll('.node circle').style('opacity', 1);
  graphG.selectAll('.edge').style('opacity', 1);
}

// ========================================
// 图谱控制
// ========================================

function initGraphControls() {
  qs('#zoomIn')?.addEventListener('click', () => {
    graphSvg.transition().duration(300).call(zoom.scaleBy, 1.3);
  });
  
  qs('#zoomOut')?.addEventListener('click', () => {
    graphSvg.transition().duration(300).call(zoom.scaleBy, 0.7);
  });
  
  qs('#resetZoom')?.addEventListener('click', () => {
    graphSvg.transition().duration(500).call(
      zoom.transform,
      d3.zoomIdentity
    );
  });
  
  qs('#centerGraph')?.addEventListener('click', () => {
    const width = qs('#graphCanvas').clientWidth;
    const height = qs('#graphCanvas').clientHeight;
    if (graphSimulation) {
      graphSimulation.force('center', d3.forceCenter(width / 2, height / 2));
      graphSimulation.alpha(0.5).restart();
    }
  });
  
  // 布局切换
  qs('#layoutForce')?.addEventListener('click', () => {
    state.layoutMode = 'force';
    setActiveLayoutButton('layoutForce');
    applyForceLayout();
  });
  
  qs('#layoutCircle')?.addEventListener('click', () => {
    state.layoutMode = 'circle';
    setActiveLayoutButton('layoutCircle');
    applyCircleLayout();
  });
  
  qs('#layoutTree')?.addEventListener('click', () => {
    state.layoutMode = 'tree';
    setActiveLayoutButton('layoutTree');
    applyTreeLayout();
  });
}

function setActiveLayoutButton(id) {
  qsa('.graph-controls .icon-button').forEach(btn => {
    if (btn.id.startsWith('layout')) {
      btn.classList.remove('active');
    }
  });
  qs(`#${id}`)?.classList.add('active');
}

function applyForceLayout() {
  if (!graphSimulation) return;
  const width = qs('#graphCanvas').clientWidth;
  const height = qs('#graphCanvas').clientHeight;
  
  graphSimulation
    .force('link', d3.forceLink(state.graphData.edges)
      .id(d => d.id)
      .distance(100))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .alpha(1)
    .restart();
}

function applyCircleLayout() {
  if (!graphSimulation) return;
  const width = qs('#graphCanvas').clientWidth;
  const height = qs('#graphCanvas').clientHeight;
  const radius = Math.min(width, height) / 3;
  
  graphSimulation
    .force('link', null)
    .force('charge', null)
    .force('radial', d3.forceRadial(radius, width / 2, height / 2))
    .alpha(1)
    .restart();
}

function applyTreeLayout() {
  if (!state.graphData.nodes.length) return;
  const width = qs('#graphCanvas').clientWidth;
  const height = qs('#graphCanvas').clientHeight;
  
  // 简单树形布局
  const root = state.graphData.nodes[0];
  const treeData = d3.stratify()
    .id(d => d.id)
    .parentId(d => {
      const parent = state.graphData.edges.find(e => e.target.id === d.id);
      return parent ? parent.source.id : null;
    })(state.graphData.nodes.filter((d, i) => i === 0 || 
      state.graphData.edges.some(e => e.target.id === d.id)));
  
  const treeLayout = d3.tree().size([width - 100, height - 100]);
  const treeNodes = treeLayout(treeData);
  
  graphSimulation
    .force('link', null)
    .force('charge', null)
    .force('center', null)
    .alpha(0);
  
  treeNodes.descendants().forEach(node => {
    const graphNode = state.graphData.nodes.find(n => n.id === node.id);
    if (graphNode) {
      graphNode.fx = node.x + 50;
      graphNode.fy = node.y + 50;
    }
  });
  
  graphSimulation.alpha(0.3).restart();
}

// ========================================
// 上下文菜单
// ========================================

function showNodeContextMenu(event, d) {
  const menu = qs('#contextMenu');
  menu.innerHTML = `
    <div class="context-menu-item" data-action="edit">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
      </svg>
      <span>编辑概念</span>
    </div>
    <div class="context-menu-item" data-action="addMemory">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
        <polyline points="17 21 17 13 7 13 7 21"/>
        <polyline points="7 3 7 8 15 8"/>
      </svg>
      <span>添加记忆</span>
    </div>
    <div class="context-menu-item" data-action="addConnection">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
      <span>创建连接</span>
    </div>
    <div class="context-menu-divider"></div>
    <div class="context-menu-item danger" data-action="delete">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
      </svg>
      <span>删除概念</span>
    </div>
  `;
  
  menu.style.display = 'block';
  menu.style.left = event.pageX + 'px';
  menu.style.top = event.pageY + 'px';
  
  // 添加事件监听
  menu.querySelectorAll('.context-menu-item').forEach(item => {
    item.addEventListener('click', async () => {
      const action = item.dataset.action;
      menu.style.display = 'none';
      
      switch (action) {
        case 'edit':
          const newName = prompt('新概念名称', d.name);
          if (newName) {
            await fetchJson(`/api/concepts/${d.id}`, {
              method: 'PUT',
              body: JSON.stringify({ group_id: state.group, name: newName })
            });
            showNotification('成功', '概念已更新', 'success');
            await loadAll();
          }
          break;
        case 'addMemory':
          state.selectedConceptId = d.id;
          qs('#rightSidebar')?.classList.remove('collapsed');
          qsa('.tab-button')[0]?.click();
          qs('#memContent')?.focus();
          break;
        case 'addConnection':
          qs('#connFrom').value = d.id;
          qs('#rightSidebar')?.classList.remove('collapsed');
          qsa('.tab-button')[1]?.click();
          qs('#connTo')?.focus();
          break;
        case 'delete':
          if (confirm(`确定删除概念"${d.name}"及其所有记忆吗？`)) {
            await fetchJson(`/api/concepts/${d.id}?group_id=${encodeURIComponent(state.group)}`, {
              method: 'DELETE'
            });
            showNotification('成功', '概念已删除', 'success');
            await loadAll();
          }
          break;
      }
    });
  });
  
  // 点击其他地方关闭菜单
  setTimeout(() => {
    document.addEventListener('click', () => {
      menu.style.display = 'none';
    }, { once: true });
  }, 0);
}

function showEdgeContextMenu(event, d) {
  const menu = qs('#contextMenu');
  menu.innerHTML = `
    <div class="context-menu-item" data-action="editStrength">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path d="M21.21 15.89A10 10 0 1 1 8 2.83"/>
        <path d="M22 12A10 10 0 0 0 12 2v10z"/>
      </svg>
      <span>调整强度</span>
    </div>
    <div class="context-menu-divider"></div>
    <div class="context-menu-item danger" data-action="delete">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
      </svg>
      <span>删除连接</span>
    </div>
  `;
  
  menu.style.display = 'block';
  menu.style.left = event.pageX + 'px';
  menu.style.top = event.pageY + 'px';
  
  menu.querySelectorAll('.context-menu-item').forEach(item => {
    item.addEventListener('click', async () => {
      const action = item.dataset.action;
      menu.style.display = 'none';
      
      if (action === 'editStrength') {
        const strength = prompt('新强度 (0-1)', d.strength);
        if (strength !== null) {
          await fetchJson(`/api/connections/${d.id}`, {
            method: 'PUT',
            body: JSON.stringify({ group_id: state.group, strength: parseFloat(strength) })
          });
          showNotification('成功', '连接强度已更新', 'success');
          await loadGraph();
        }
      } else if (action === 'delete') {
        if (confirm('确定删除此连接吗？')) {
          await fetchJson(`/api/connections/${d.id}?group_id=${encodeURIComponent(state.group)}`, {
            method: 'DELETE'
          });
          showNotification('成功', '连接已删除', 'success');
          await loadGraph();
        }
      }
    });
  });
  
  setTimeout(() => {
    document.addEventListener('click', () => {
      menu.style.display = 'none';
    }, { once: true });
  }, 0);
}

// ========================================
// 节点提示框
// ========================================

function showNodeTooltip(event, d) {
  const tooltip = qs('#nodeTooltip');
  const memories = state.memories.filter(m => m.concept_id === d.id);
  
  tooltip.innerHTML = `
    <div class="tooltip-header">${d.name}</div>
    <div class="tooltip-content">
      ${memories.slice(0, 3).map(m => `• ${m.content}`).join('<br>') || '暂无记忆'}
    </div>
    <div class="tooltip-meta">
      <div class="tooltip-meta-item">
        <span class="tooltip-meta-label">记忆数</span>
        <span class="tooltip-meta-value">${d.count}</span>
      </div>
      <div class="tooltip-meta-item">
        <span class="tooltip-meta-label">连接数</span>
        <span class="tooltip-meta-value">${
          state.graphData.edges.filter(e => 
            e.source.id === d.id || e.target.id === d.id).length
        }</span>
      </div>
    </div>
  `;
  
  tooltip.style.display = 'block';
  tooltip.style.left = (event.pageX + 15) + 'px';
  tooltip.style.top = (event.pageY + 15) + 'px';
}

function hideNodeTooltip() {
  qs('#nodeTooltip').style.display = 'none';
}

// ========================================
// 搜索功能
// ========================================

function initSearch() {
  const input = qs('#graphSearch');
  const results = qs('#searchResults');
  
  input?.addEventListener('input', debounce(async (e) => {
    const query = e.target.value.trim();
    if (!query) {
      results.innerHTML = '';
      return;
    }
    
    // 搜索概念
    const matchedConcepts = state.concepts.filter(c => 
      c.name.toLowerCase().includes(query.toLowerCase())
    );
    
    // 搜索记忆
    let matchedMemories = [];
    try {
      const data = await fetchJson(`/api/memories?group_id=${encodeURIComponent(state.group)}&q=${encodeURIComponent(query)}`);
      matchedMemories = data.memories || [];
    } catch (error) {
      console.error('搜索失败:', error);
    }
    
    // 渲染结果
    results.innerHTML = '';
    
    if (matchedConcepts.length === 0 && matchedMemories.length === 0) {
      results.innerHTML = '<div class="search-result-item"><div class="search-result-desc">无匹配结果</div></div>';
      return;
    }
    
    matchedConcepts.forEach(c => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = `
        <div class="search-result-title">${c.name}</div>
        <div class="search-result-desc">概念 · ID: ${c.id}</div>
      `;
      item.addEventListener('click', () => {
        const node = state.graphData.nodes.find(n => n.id === c.id);
        if (node) selectNode(node);
        results.innerHTML = '';
        input.value = '';
      });
      results.appendChild(item);
    });
    
    matchedMemories.slice(0, 5).forEach(m => {
      const concept = state.concepts.find(c => c.id === m.concept_id);
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = `
        <div class="search-result-title">${m.content}</div>
        <div class="search-result-desc">记忆 · ${concept?.name || m.concept_id}</div>
      `;
      item.addEventListener('click', () => {
        state.selectedConceptId = m.concept_id;
        const node = state.graphData.nodes.find(n => n.id === m.concept_id);
        if (node) selectNode(node);
        results.innerHTML = '';
        input.value = '';
      });
      results.appendChild(item);
    });
  }, 300));
}

// ========================================
// 数据加载
// ========================================

async function loadGroups() {
  const data = await fetchJson('/api/groups');
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
  try {
    const data = await fetchJson(`/api/graph?group_id=${encodeURIComponent(state.group)}`);
    if (data.error) {
      showNotification('错误', data.error, 'error');
      return;
    }
    
    // 转换数据格式
    const nodes = data.nodes.map(n => ({
      id: n.id,
      name: n.name,
      count: n.count || 0
    }));
    
    const edges = data.edges.map(e => ({
      id: `${e.from_concept}_${e.to_concept}`,
      source: e.from_concept,
      target: e.to_concept,
      strength: e.strength || 0.5
    }));
    
    renderGraph({ nodes, edges });
  } catch (error) {
    console.error('加载图谱失败:', error);
  }
}

async function loadConcepts() {
  const data = await fetchJson(`/api/concepts?group_id=${encodeURIComponent(state.group)}`);
  state.concepts = data.concepts || [];
  renderConcepts();
}

function renderConcepts() {
  const list = qs('#conceptList');
  list.innerHTML = '';
  
  if (state.concepts.length === 0) {
    list.innerHTML = '<div class="list-item"><div class="list-item-body">暂无概念</div></div>';
    return;
  }
  
  state.concepts.forEach(c => {
    const item = document.createElement('div');
    item.className = 'list-item' + (c.id === state.selectedConceptId ? ' selected' : '');
    item.innerHTML = `
      <div class="list-item-header">
        <div class="list-item-title">${c.name}</div>
        <div class="list-item-actions">
          <button class="glass-button" data-action="select">选中</button>
          <button class="glass-button" data-action="delete" style="background: var(--color-danger); color: white;">删除</button>
        </div>
      </div>
      <div class="list-item-meta">ID: ${c.id}</div>
    `;
    
    item.querySelector('[data-action="select"]').addEventListener('click', (e) => {
      e.stopPropagation();
      const node = state.graphData.nodes.find(n => n.id === c.id);
      if (node) selectNode(node);
    });
    
    item.querySelector('[data-action="delete"]').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm(`确定删除概念"${c.name}"吗？`)) {
        await fetchJson(`/api/concepts/${c.id}?group_id=${encodeURIComponent(state.group)}`, {
          method: 'DELETE'
        });
        showNotification('成功', '概念已删除', 'success');
        await loadAll();
      }
    });
    
    list.appendChild(item);
  });
}

async function loadMemories() {
  const params = new URLSearchParams();
  params.set('group_id', state.group);
  if (state.selectedConceptId) params.set('concept_id', state.selectedConceptId);
  
  const data = await fetchJson(`/api/memories?${params}`);
  state.memories = data.memories || [];
  renderMemories();
  
  // 更新统计
  qs('#memoryCount').textContent = state.memories.length;
}

function renderMemories() {
  const list = qs('#memoryList');
  list.innerHTML = '';
  
  if (state.memories.length === 0) {
    list.innerHTML = '<div class="list-item"><div class="list-item-body">暂无记忆</div></div>';
    return;
  }
  
  state.memories.forEach(m => {
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      <div class="list-item-header">
        <div class="list-item-title">${m.content}</div>
        <div class="list-item-actions">
          <button class="glass-button" data-action="edit">编辑</button>
          <button class="glass-button" data-action="delete" style="background: var(--color-danger); color: white;">删除</button>
        </div>
      </div>
      ${m.details ? `<div class="list-item-body">${m.details}</div>` : ''}
      <div class="list-item-meta">
        强度: ${(m.strength || 0).toFixed(2)} | 
        ${m.participants ? '参与: ' + m.participants + ' | ' : ''}
        ${m.tags ? '标签: ' + m.tags : ''}
      </div>
    `;
    
    item.querySelector('[data-action="edit"]').addEventListener('click', async (e) => {
      e.stopPropagation();
      const content = prompt('内容', m.content);
      if (content !== null) {
        await fetchJson(`/api/memories/${m.id}`, {
          method: 'PUT',
          body: JSON.stringify({ group_id: state.group, content })
        });
        showNotification('成功', '记忆已更新', 'success');
        await loadMemories();
      }
    });
    
    item.querySelector('[data-action="delete"]').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm('确定删除此记忆吗？')) {
        await fetchJson(`/api/memories/${m.id}?group_id=${encodeURIComponent(state.group)}`, {
          method: 'DELETE'
        });
        showNotification('成功', '记忆已删除', 'success');
        await loadMemories();
        await loadGraph();
      }
    });
    
    list.appendChild(item);
  });
}

async function loadConnections() {
  const data = await fetchJson(`/api/connections?group_id=${encodeURIComponent(state.group)}`);
  state.connections = data.connections || [];
  renderConnections();
}

function renderConnections() {
  const list = qs('#connList');
  list.innerHTML = '';
  
  if (state.connections.length === 0) {
    list.innerHTML = '<div class="list-item"><div class="list-item-body">暂无连接</div></div>';
    return;
  }
  
  state.connections.forEach(c => {
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      <div class="list-item-header">
        <div class="list-item-title">${c.from_concept} → ${c.to_concept}</div>
        <div class="list-item-actions">
          <button class="glass-button" data-action="edit">强度</button>
          <button class="glass-button" data-action="delete" style="background: var(--color-danger); color: white;">删除</button>
        </div>
      </div>
      <div class="list-item-meta">强度: ${(c.strength || 0).toFixed(2)}</div>
    `;
    
    item.querySelector('[data-action="edit"]').addEventListener('click', async (e) => {
      e.stopPropagation();
      const strength = prompt('强度 (0-1)', c.strength);
      if (strength !== null) {
        await fetchJson(`/api/connections/${c.id}`, {
          method: 'PUT',
          body: JSON.stringify({ group_id: state.group, strength: parseFloat(strength) })
        });
        showNotification('成功', '连接已更新', 'success');
        await loadConnections();
        await loadGraph();
      }
    });
    
    item.querySelector('[data-action="delete"]').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm('确定删除此连接吗？')) {
        await fetchJson(`/api/connections/${c.id}?group_id=${encodeURIComponent(state.group)}`, {
          method: 'DELETE'
        });
        showNotification('成功', '连接已删除', 'success');
        await loadConnections();
        await loadGraph();
      }
    });
    
    list.appendChild(item);
  });
}

async function loadImpressions() {
  const data = await fetchJson(`/api/impressions?group_id=${encodeURIComponent(state.group)}`);
  state.impressions = data.people || [];
  renderImpressions();
}

function renderImpressions() {
  const list = qs('#impList');
  list.innerHTML = '';
  
  if (state.impressions.length === 0) {
    list.innerHTML = '<div class="list-item"><div class="list-item-body">暂无人物印象</div></div>';
    return;
  }
  
  state.impressions.forEach(p => {
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      <div class="list-item-header">
        <div class="list-item-title">${p.name}</div>
      </div>
    `;
    item.addEventListener('click', () => loadImpressionDetail(p.name));
    list.appendChild(item);
  });
}

async function loadImpressionDetail(person) {
  state.selectedPerson = person;
  const params = new URLSearchParams();
  params.set('group_id', state.group);
  params.set('person', person);
  const data = await fetchJson(`/api/impressions?${params}`);
  
  const detail = qs('#impDetail');
  const summary = data.summary || {};
  const memories = data.memories || [];
  
  if (!summary.name && !memories.length) {
    detail.innerHTML = '<div>暂无数据</div>';
    return;
  }
  
  const scoreVal = typeof summary.score === 'number' ? summary.score.toFixed(2) : (summary.score || '');
  
  detail.innerHTML = `
    <h4>${summary.name || person} (好感度: ${scoreVal})</h4>
    <div>${summary.summary || ''}</div>
    <small>记录数: ${summary.memory_count || memories.length} | 最后更新: ${summary.last_updated || ''}</small>
    ${memories.length ? '<ul>' + memories.map(m => 
      `<li>${m.content} ${m.details ? '— ' + m.details : ''} <small>分数: ${m.score?.toFixed?.(2) || ''}</small></li>`
    ).join('') + '</ul>' : ''}
  `;
}

// ========================================
// 表单操作
// ========================================

function initFormActions() {
  // 添加概念
  qs('#addConceptBtn')?.addEventListener('click', async () => {
    const name = qs('#newConceptName').value.trim();
    if (!name) return;
    
    await fetchJson('/api/concepts', {
      method: 'POST',
      body: JSON.stringify({ group_id: state.group, name })
    });
    
    qs('#newConceptName').value = '';
    showNotification('成功', '概念已添加', 'success');
    await loadAll();
  });
  
  // 添加记忆
  qs('#addMemoryBtn')?.addEventListener('click', async () => {
    if (!state.selectedConceptId) {
      showNotification('提示', '请先选择一个概念', 'warning');
      return;
    }
    
    const content = qs('#memContent').value.trim();
    if (!content) return;
    
    const body = {
      group_id: state.group,
      concept_id: state.selectedConceptId,
      content,
      details: qs('#memDetails').value.trim(),
      participants: qs('#memParticipants').value.trim(),
      location: qs('#memLocation').value.trim(),
      tags: qs('#memTags').value.trim(),
      emotion: qs('#memEmotion').value.trim(),
      strength: parseFloat(qs('#memStrength').value || '1')
    };
    
    await fetchJson('/api/memories', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    
    ['#memContent', '#memDetails', '#memParticipants', '#memLocation', '#memTags', '#memEmotion', '#memStrength']
      .forEach(id => qs(id).value = '');
    
    showNotification('成功', '记忆已添加', 'success');
    await loadMemories();
    await loadGraph();
  });
  
  // 添加连接
  qs('#addConnBtn')?.addEventListener('click', async () => {
    const from = qs('#connFrom').value.trim();
    const to = qs('#connTo').value.trim();
    if (!from || !to) return;
    
    await fetchJson('/api/connections', {
      method: 'POST',
      body: JSON.stringify({
        group_id: state.group,
        from_concept: from,
        to_concept: to,
        strength: parseFloat(qs('#connStrength').value || '1')
      })
    });
    
    ['#connFrom', '#connTo'].forEach(id => qs(id).value = '');
    showNotification('成功', '连接已添加', 'success');
    await loadConnections();
    await loadGraph();
  });
  
  // 添加印象
  qs('#addImpBtn')?.addEventListener('click', async () => {
    const person = qs('#impPerson').value.trim();
    const summary = qs('#impSummary').value.trim();
    if (!person || !summary) return;
    
    await fetchJson('/api/impressions', {
      method: 'POST',
      body: JSON.stringify({
        group_id: state.group,
        person,
        summary,
        score: parseFloat(qs('#impScore').value || ''),
        details: qs('#impDetails').value.trim()
      })
    });
    
    ['#impPerson', '#impSummary', '#impScore', '#impDetails'].forEach(id => qs(id).value = '');
    showNotification('成功', '印象已记录', 'success');
    await loadImpressions();
    await loadGraph();
  });
  
  // 调整好感度
  qs('#impAdjustBtn')?.addEventListener('click', async () => {
    if (!state.selectedPerson) {
      showNotification('提示', '请先选择一个人物', 'warning');
      return;
    }
    
    const delta = parseFloat(qs('#impDelta').value || '0');
    if (delta === 0) return;
    
    await fetchJson(`/api/impressions/${state.selectedPerson}/score`, {
      method: 'PUT',
      body: JSON.stringify({
        group_id: state.group,
        delta
      })
    });
    
    qs('#impDelta').value = '';
    showNotification('成功', '好感度已调整', 'success');
    await loadImpressionDetail(state.selectedPerson);
  });
}

// ========================================
// 全局刷新
// ========================================

async function loadAll() {
  await Promise.all([
    loadGroups(),
    loadConcepts(),
    loadGraph(),
    loadMemories(),
    loadConnections(),
    loadImpressions()
  ]);
}

// ========================================
// 初始化
// ========================================

window.addEventListener('DOMContentLoaded', async () => {
  // 初始化UI
  initTheme();
  initSidebar();
  initTabs();
  initGraph();
  initGraphControls();
  initSearch();
  initFormActions();
  
  // 绑定全局事件
  qs('#groupSelect')?.addEventListener('change', (e) => {
    state.group = e.target.value;
    loadAll();
  });
  
  qs('#tokenInput')?.addEventListener('change', (e) => {
    state.token = e.target.value.trim();
    loadAll();
  });
  
  qs('#refreshBtn')?.addEventListener('click', () => {
    showNotification('刷新中...', '正在重新加载数据', 'info');
    loadAll();
  });
  
  // 点击空白处取消选择
  graphSvg.on('click', function(event) {
    if (event.target === this) {
      state.selectedConceptId = null;
      graphG.selectAll('.node circle')
        .attr('fill', state.theme === 'dark' ? '#0A84FF' : '#007AFF');
    }
  });
  
  // 初始加载
  try {
    await loadAll();
    showNotification('欢迎', 'Memora Connect 已就绪', 'success');
  } catch (error) {
    showNotification('错误', '初始化失败: ' + error.message, 'error');
  }
});
"""
