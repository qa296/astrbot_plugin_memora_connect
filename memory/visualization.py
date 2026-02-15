import os
import time
import math
import asyncio
from typing import Any, Dict, List, Optional

# 背景渲染使用无头后端，避免服务器/无显示环境报错
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import networkx as nx
except ImportError:
    nx = None

# 尝试导入 community_louvain，用于社区检测
try:
    import community as community_louvain
except ImportError:
    community_louvain = None

import logging
logger: logging.Logger = logging.getLogger(__name__)
try:
    from astrbot.api import logger as _astr_logger  # type: ignore
    if _astr_logger:
        logger = _astr_logger  # type: ignore[assignment]
except Exception:
    pass

class MemoryGraphVisualizer:
    """
    记忆图谱可视化
    - 节点(球)大小: 随记忆数量与强度增大而增大
    - 边(线)有无: 依据连接强度(存在即显示, 过低滤除)
    - 边长短: 使用 spring_layout 的权重(weight), 强度越大, 节点越靠近, 视觉上线更短
    - 颜色编码:
       * 印象(Imprint:*) 概念: 红色系
       * 重要事件(概念下存在高强度记忆或标签含“重要/important”): 绿色系
       * 其他普通概念: 蓝色系
    """

    def __init__(self, memory_system: Any) -> None:
        self.ms = memory_system

        # 设置中文字体，使用多种方法确保汉字显示
        try:
            from matplotlib.font_manager import FontProperties
            
            # 方法1：尝试使用font.otf
            font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.otf")
            custom_font_loaded = False
            
            if os.path.exists(font_path):
                try:
                    # 注册自定义字体
                    font_prop = FontProperties(fname=font_path)
                    font_name = font_prop.get_name()
                    
                    # 设置字体属性
                    matplotlib.rcParams["font.family"] = font_name
                    matplotlib.rcParams["font.sans-serif"] = [font_name] + matplotlib.rcParams["font.sans-serif"]
                    matplotlib.rcParams["axes.unicode_minus"] = False
                    
                    # 保存字体属性供后续使用
                    self.font_prop = font_prop
                    custom_font_loaded = True
                    
                    logger.info(f"已加载自定义字体: {font_name}")
                except Exception as e:
                    logger.warning(f"加载自定义字体失败: {e}")
            
            # 方法2：如果自定义字体加载失败，尝试系统中文字体
            if not custom_font_loaded:
                # 尝试多种中文字体
                chinese_fonts = ["SimHei", "Microsoft YaHei", "STHeiti", "STSong", "STKaiti", "STFangsong", "Arial Unicode MS", "DejaVu Sans"]
                available_font = None
                
                for font in chinese_fonts:
                    try:
                        # 测试字体是否可用
                        test_prop = FontProperties(family=font)
                        # 如果没有抛出异常，认为字体可用
                        available_font = font
                        break
                    except:
                        continue
                
                if available_font:
                    matplotlib.rcParams["font.sans-serif"] = [available_font] + matplotlib.rcParams["font.sans-serif"]
                    matplotlib.rcParams["axes.unicode_minus"] = False
                    self.font_prop = FontProperties(family=available_font)
                    logger.info(f"使用系统中文字体: {available_font}")
                else:
                    # 方法3：使用matplotlib的默认字体设置
                    matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"] + matplotlib.rcParams["font.sans-serif"]
                    matplotlib.rcParams["axes.unicode_minus"] = False
                    self.font_prop = FontProperties(family="sans-serif")
                    logger.warning("未找到合适的中文字体，使用默认字体")
            
        except Exception as e:
            logger.error(f"字体设置失败: {e}")
            # 最后的备用方案
            matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            self.font_prop = FontProperties(family="sans-serif")

    async def generate_graph_image(self, max_nodes: int = 120, max_edges: int = 400, edge_strength_threshold: float = 0.05, layout_style: str = "auto", group_id: Optional[str] = None) -> str:
        """
        异步生成记忆图谱 PNG, 返回图片绝对路径
        为避免阻塞事件循环, 将同步绘图放到线程池执行
        
        Args:
            layout_style: 布局风格，可选值：
                - auto: 自动选择最适合的布局（默认）
                - force_directed: 力导向布局
                - circular: 圆形布局
                - kamada_kawai: Kamada-Kawai布局
                - spectral: 谱布局
                - community: 社区布局
                - hierarchical: 多层次布局
            group_id: 群组ID，用于群聊隔离。如果为None，则自动获取当前会话ID
        """
        try:
            # 如果没有提供group_id，尝试从记忆系统获取当前会话ID
            actual_group_id = ""
            if group_id is None:
                # 尝试从记忆系统获取当前会话ID
                if hasattr(self.ms, 'get_current_group_id'):
                    actual_group_id = await self.ms.get_current_group_id()
                elif hasattr(self.ms, 'current_group_id'):
                    actual_group_id = self.ms.current_group_id
            else:
                actual_group_id = group_id
            
            # 在主事件循环中获取所有需要的数据
            graph_data = await self._prepare_graph_data(max_nodes, max_edges, edge_strength_threshold, actual_group_id)
            
            # 将数据传递给同步绘图函数，在线程池中只执行纯绘图操作
            return await asyncio.to_thread(
                self._generate_graph_image_sync,
                graph_data,
                layout_style
            )
        except Exception as e:
            logger.error(f"生成记忆图谱失败: {e}", exc_info=True)
            return ""

    async def _prepare_graph_data(self, max_nodes: int, max_edges: int, edge_strength_threshold: float, group_id: str = "") -> Dict[str, Any]:
        """
        在主事件循环中准备所有需要的数据，避免在线程池中访问异步资源
        支持群聊隔离：根据group_id过滤记忆、概念和连接
        """
        graph = getattr(self.ms, "memory_graph", None)
        if not graph or not graph.concepts:
            return {"error": "记忆图谱为空, 无法生成图谱"}

        # 获取所有概念、记忆和连接
        concepts = list(graph.concepts.values())
        memories = list(graph.memories.values())
        connections = list(graph.connections)

        # 如果启用了群聊隔离且有group_id，过滤数据
        if group_id and self.ms.memory_config.get("enable_group_isolation", True):
            # 过滤记忆：只包含指定群聊的记忆
            filtered_memory_ids = set()
            for memory in memories:
                # 检查记忆是否有group_id字段
                memory_group_id = getattr(memory, 'group_id', '')
                if memory_group_id:
                    if memory_group_id == group_id:
                        filtered_memory_ids.add(memory.id)
                else:
                    # 如果记忆没有group_id字段，检查是否为印象记忆
                    # 印象记忆通常以"Imprint:"开头，需要特殊处理
                    if hasattr(memory, 'content') and memory.content and memory.content.startswith("Imprint:"):
                        # 对于印象记忆，检查内容中是否包含群组ID
                        if f"Imprint:{group_id}:" in memory.content:
                            filtered_memory_ids.add(memory.id)
                    else:
                        # 对于非印象记忆且没有group_id字段的旧版本数据，默认包含
                        # 这样可以确保旧版本数据在群聊隔离模式下仍然可见
                        filtered_memory_ids.add(memory.id)
            
            # 根据过滤后的记忆获取相关的概念
            filtered_concept_ids = set()
            for memory_id in filtered_memory_ids:
                memory = graph.memories.get(memory_id)
                if memory:
                    filtered_concept_ids.add(memory.concept_id)
            
            # 过滤概念：只包含与过滤后记忆相关的概念
            concepts = [c for c in concepts if c.id in filtered_concept_ids]
            
            # 过滤连接：只包含过滤后概念之间的连接
            connections = [
                conn for conn in connections
                if conn.from_concept in filtered_concept_ids and conn.to_concept in filtered_concept_ids
            ]
            
            # 更新记忆列表
            memories = [m for m in memories if m.id in filtered_memory_ids]

        # 1) 统计每个概念的记忆数量与强度
        concept_stats: Dict[str, Dict[str, float]] = {}
        for cid in graph.concepts.keys():
            concept_stats[cid] = {"count": 0, "sum_strength": 0.0, "max_strength": 0.0}
        
        # 只统计过滤后的记忆
        for m in memories:
            stat = concept_stats.get(m.concept_id)
            if stat is None:
                continue
            stat["count"] += 1
            stat["sum_strength"] += float(m.strength or 0.0)
            stat["max_strength"] = max(stat["max_strength"], float(m.strength or 0.0))

        for cid, s in concept_stats.items():
            cnt = max(1, int(s["count"]))
            s["avg_strength"] = s["sum_strength"] / cnt if cnt > 0 else 0.0

        # 2) 节点选择(如概念过多, 选取 Top-N)
        ranked_concepts = sorted(
            concepts,  # 使用过滤后的概念
            key=lambda c: (concept_stats.get(c.id, {}).get("count", 0), concept_stats.get(c.id, {}).get("avg_strength", 0.0)),
            reverse=True
        )
        selected_concepts: List[Any] = ranked_concepts[:max_nodes]
        selected_ids = set(c.id for c in selected_concepts)

        # 3) 过滤边(只保留强度足够且两端都被选中的)
        filtered_edges: List[Any] = []
        for conn in connections:  # 使用过滤后的连接
            if conn.strength is None:
                continue
            if conn.strength < edge_strength_threshold:
                continue
            if (conn.from_concept in selected_ids) and (conn.to_concept in selected_ids):
                filtered_edges.append(conn)

        # 缩减边数量: 保留强度靠前的前 max_edges 条
        filtered_edges.sort(key=lambda e: float(e.strength or 0.0), reverse=True)
        filtered_edges = filtered_edges[:max_edges]

        # 4) 准备节点数据
        nodes_data = []
        for c in selected_concepts:
            stat = concept_stats.get(c.id, {"count": 0, "avg_strength": 0.0, "max_strength": 0.0})
            nodes_data.append({
                "id": c.id,
                "name": c.name,
                "count": stat["count"],
                "avg_strength": stat["avg_strength"],
                "max_strength": stat["max_strength"]
            })

        # 5) 准备边数据
        edges_data = []
        for e in filtered_edges:
            edges_data.append({
                "from_concept": e.from_concept,
                "to_concept": e.to_concept,
                "strength": float(e.strength or 0.0)
            })

        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "group_id": group_id,  # 传递group_id给同步函数
            "error": None
        }

    def _generate_graph_image_sync(self, graph_data: Dict[str, Any], layout_style: str) -> str:
        if nx is None:
            logger.error("未安装 networkx, 无法生成图谱")
            return ""

        # 检查是否有错误
        if graph_data.get("error"):
            logger.warning(graph_data["error"])
            return ""

        nodes_data = graph_data.get("nodes", [])
        edges_data = graph_data.get("edges", [])
        group_id = graph_data.get("group_id", "")  # 从graph_data中获取group_id

        if not nodes_data:
            logger.warning("筛选后无节点, 无法生成图谱")
            return ""

        # 构建 NetworkX 图
        G: Any = nx.Graph()
        for node in nodes_data:
            G.add_node(node["id"], name=node["name"], count=node["count"],
                      avg_strength=node["avg_strength"], max_strength=node["max_strength"])

        for edge in edges_data:
            # 使用连接强度作为 weight, 强度越大, spring_layout 越倾向拉近节点
            G.add_edge(edge["from_concept"], edge["to_concept"], weight=edge["strength"])

        # 5) 节点可视参数计算(大小/颜色)
        node_sizes: List[float] = []
        node_colors: List[str] = []
        labels: Dict[str, str] = {}

        # 统计值用于归一化节点大小
        counts = [G.nodes[n]["count"] for n in G.nodes()]
        avg_strengths = [G.nodes[n]["avg_strength"] for n in G.nodes()]
        max_count = max(1, max(counts))
        max_avg_strength = max(0.0001, max(avg_strengths) if avg_strengths else 0.0001)

        # 大小范围(px^2, matplotlib 的 node_size 实际为面积)
        min_area = 300.0
        max_area = 3000.0

        for n in G.nodes():
            name = G.nodes[n]["name"]
            cnt = G.nodes[n]["count"]
            avg_s = float(G.nodes[n]["avg_strength"] or 0.0)
            max_s = float(G.nodes[n]["max_strength"] or 0.0)

            # 大小: 记忆数量占比 + 平均强度占比 + 最大强度占比 的加权
            # 增加最大强度的权重，使重要节点更突出
            max_strengths = [G.nodes[n]["max_strength"] for n in G.nodes()]
            max_max_strength = max(0.0001, max(max_strengths) if max_strengths else 0.0001)
            
            count_factor = cnt / max_count
            avg_strength_factor = avg_s / max_avg_strength
            max_strength_factor = float(G.nodes[n]["max_strength"] or 0.0) / max_max_strength
            
            # 调整权重，更强调记忆强度
            size_factor = 0.5 * count_factor + 0.25 * avg_strength_factor + 0.25 * max_strength_factor
            size = min_area + (max_area - min_area) * max(0.0, min(1.0, size_factor))
            node_sizes.append(size)

            # 颜色:
            #   印象概念: Imprint:<group_id>:<name>  -> 红色系
            #   重要事件: max_strength 高或标签线索不可直接取, 以 max_strength>=0.8 作为"重要"近似 -> 绿色系
            #   其他: 蓝色系
            if name.startswith("Imprint:"):
                node_colors.append("#e57373")  # red 300
                # 对于印象记忆，提取显示名称时考虑群聊隔离
                if group_id and f"Imprint:{group_id}:" in name:
                    # 如果是当前群聊的印象记忆，显示完整名称
                    display = name
                else:
                    # 否则只显示最后一部分
                    display = name.split(":")[-1] if ":" in name else name
            elif max_s >= 0.8:
                node_colors.append("#66bb6a")  # green 400
                display = (name.split(",")[0]).strip()
            else:
                node_colors.append("#64b5f6")  # blue 300
                display = (name.split(",")[0]).strip()

            labels[n] = f"{display}\n{cnt}"

        # 6) 布局: 根据用户选择的风格使用不同的布局算法
        # 自适应布局选择：如果layout_style为"auto"，则根据图的复杂度自动选择
        if layout_style == "auto":
            # 计算图的复杂度指标
            num_nodes = G.number_of_nodes()
            num_edges = G.number_of_edges()
            density = num_edges / (num_nodes * (num_nodes - 1) / 2) if num_nodes > 1 else 0
            
            # 根据复杂度选择最适合的布局
            if num_nodes <= 5:
                # 极少量节点，使用圆形布局
                layout_style = "circular"
            elif num_nodes <= 15 and density <= 0.3:
                # 少量节点且稀疏连接，使用力导向布局
                layout_style = "force_directed"
            elif num_nodes <= 30 and density > 0.5:
                # 中等数量节点且密集连接，使用谱布局
                layout_style = "spectral"
            elif num_nodes <= 30:
                # 中等数量节点且稀疏连接，使用力导向布局
                layout_style = "force_directed"
            elif num_nodes <= 50:
                # 较多节点，使用社区布局（如果可用）或力导向布局
                layout_style = "community" if community_louvain is not None else "force_directed"
            else:
                # 大量节点，使用多层次布局
                layout_style = "hierarchical"
        
        # 预处理：对于大型图，先进行边简化，减少交叉
        if G.number_of_nodes() > 25 and G.number_of_edges() > 30:
            # 创建一个简化版本的图用于布局计算
            G_layout = G.copy()
            
            # 计算每条边的介数中心性，识别关键边
            try:
                edge_betweenness = nx.edge_betweenness_centrality(G_layout, weight='weight')
                # 按介数中心性排序，保留最重要的边
                sorted_edges = sorted(edge_betweenness.items(), key=lambda x: x[1], reverse=True)
                # 保留前70%的边
                keep_edges = [e[0] for e in sorted_edges[:int(len(sorted_edges) * 0.7)]]
                # 移除不重要的边
                edges_to_remove = [e for e in G_layout.edges() if e not in keep_edges]
                G_layout.remove_edges_from(edges_to_remove)
            except:
                # 如果计算失败，使用原始图
                G_layout = G
        else:
            G_layout = G
            
        if layout_style == "force_directed":
            # Force-directed布局，使节点按照关联强度自然分布
            # 策略1: 基于图密度动态调整k值
            num_nodes = G.number_of_nodes()
            num_edges = G.number_of_edges()
            
            if num_nodes > 1:
                max_possible_edges = num_nodes * (num_nodes - 1) / 2
                density = num_edges / max_possible_edges
            else:
                density = 0.0

            # 优化布局参数计算
            base_k = 1.0 / math.sqrt(num_nodes) if num_nodes > 0 else 1.0
            
            # 根据节点数量和密度动态调整参数
            if num_nodes <= 10:
                # 少量节点时，使用较小的k值，使节点更紧密
                density_factor = 0.3 + 1.5 * density
                iterations = 1000
            elif num_nodes <= 30:
                # 中等数量节点，平衡分布
                density_factor = 0.5 + 2.0 * (density ** 1.5)
                iterations = 1500
            else:
                # 大量节点时，使用更大的k值，避免过度拥挤
                density_factor = 0.7 + 3.0 * (density ** 0.8)
                iterations = 2500
            
            k = base_k * density_factor
            
            # 策略2: 多阶段布局优化
            # 第一阶段：使用spectral_layout生成一个基于图结构的初始布局
            # 这比circular_layout更能反映图的连接关系
            try:
                initial_pos = nx.spectral_layout(G_layout, scale=1, weight="weight")
            except:
                # 如果spectral_layout失败，回退到circular_layout
                initial_pos = nx.circular_layout(G_layout, scale=1)
            
            # 第二阶段：使用spring_layout进行精细调整
            # 添加额外的参数来优化布局分布
            pos_layout = nx.spring_layout(
                G_layout,
                pos=initial_pos,  # 使用基于图结构的初始位置
                weight="weight",
                k=k,  # 使用动态计算的k值
                iterations=iterations,
                threshold=1e-5,  # 降低阈值，提高收敛精度
                seed=42,  # 保持seed可复现
                scale=3,  # 增加缩放比例，提供更多空间，必须为整数
                center=(0, 0)
            )
            
            # 将布局位置映射回原始图的所有节点
            pos = {}
            for node in G.nodes():
                if node in pos_layout:
                    pos[node] = pos_layout[node]
                else:
                    # 对于简化图中被移除的节点，将其放置在相关节点附近
                    # 找到与该节点相连的节点
                    neighbors = list(G.neighbors(node))
                    if neighbors:
                        # 计算邻居节点的平均位置
                        avg_x = sum(pos_layout.get(n, (0, 0))[0] for n in neighbors if n in pos_layout) / len(neighbors)
                        avg_y = sum(pos_layout.get(n, (0, 0))[1] for n in neighbors if n in pos_layout) / len(neighbors)
                        # 添加一些随机偏移，避免重叠
                        import random
                        offset_x = (random.random() - 0.5) * 0.3
                        offset_y = (random.random() - 0.5) * 0.3
                        pos[node] = (avg_x + offset_x, avg_y + offset_y)
                    else:
                        # 如果没有邻居，随机放置
                        import random
                        pos[node] = (random.random() * 2 - 1, random.random() * 2 - 1)
            
            # 第三阶段：基于节点大小的碰撞检测和布局优化
            # 计算每个节点的实际显示半径（基于节点大小）
            node_radii = {}
            for i, node in enumerate(G.nodes()):
                # 节点大小是面积，转换为半径
                area = node_sizes[i]
                radius = math.sqrt(area / math.pi) / 100  # 缩放到合适的比例
                node_radii[node] = max(radius, 0.1)  # 最小半径为0.1
            
            # 应用碰撞检测和分离算法
            pos = self._apply_collision_detection(G, pos, node_radii, iterations=50)
        elif layout_style == "circular":
            # 圆形布局，将节点排列在圆周上
            pos = nx.circular_layout(G, scale=3)  # 增加缩放比例，使节点分布更广，必须为整数
            
            # 对圆形布局也应用碰撞检测
            # 计算每个节点的实际显示半径
            node_radii = {}
            for i, node in enumerate(G.nodes()):
                area = node_sizes[i]
                radius = math.sqrt(area / math.pi) / 100
                node_radii[node] = max(radius, 0.1)
            
            # 应用碰撞检测
            pos = self._apply_collision_detection(G, pos, node_radii, iterations=30)
        elif layout_style == "kamada_kawai":
            # Kamada-Kawai布局，基于路径长度的布局算法
            pos = nx.kamada_kawai_layout(G, weight="weight", scale=2)  # 增加缩放比例，必须为整数
            
            # 对Kamada-Kawai布局应用碰撞检测
            node_radii = {}
            for i, node in enumerate(G.nodes()):
                area = node_sizes[i]
                radius = math.sqrt(area / math.pi) / 100
                node_radii[node] = max(radius, 0.1)
            
            pos = self._apply_collision_detection(G, pos, node_radii, iterations=30)
            
        elif layout_style == "spectral":
            # 谱布局，基于图的拉普拉斯矩阵
            pos = nx.spectral_layout(G, weight="weight", scale=2)  # 增加缩放比例，必须为整数
            
            # 对谱布局应用碰撞检测
            node_radii = {}
            for i, node in enumerate(G.nodes()):
                area = node_sizes[i]
                radius = math.sqrt(area / math.pi) / 100
                node_radii[node] = max(radius, 0.1)
            
            pos = self._apply_collision_detection(G, pos, node_radii, iterations=30)
        elif layout_style == "hierarchical":
            # 多层次布局，根据记忆强度和重要性进行分层排列
            # 1. 计算每个节点的重要性分数
            node_importance = {}
            # 获取最大强度值
            max_strengths = [G.nodes[n]["max_strength"] for n in G.nodes()]
            max_max_strength = max(0.0001, max(max_strengths) if max_strengths else 0.0001)
            
            for node in G.nodes():
                # 综合考虑记忆数量、平均强度和最大强度
                count = G.nodes[node]["count"]
                avg_strength = G.nodes[node]["avg_strength"]
                max_strength = G.nodes[node]["max_strength"]
                
                # 计算重要性分数
                importance = 0.4 * (count / max_count) + 0.3 * (avg_strength / max_avg_strength) + 0.3 * (max_strength / max_max_strength)
                node_importance[node] = importance
            
            # 2. 根据重要性分数将节点分为3层
            layers = {"top": [], "middle": [], "bottom": []}
            importance_values = list(node_importance.values())
            if importance_values:
                # 使用三分位数确定层次边界
                importance_values.sort()
                n = len(importance_values)
                bottom_threshold = importance_values[n // 3]
                top_threshold = importance_values[2 * n // 3]
                
                for node, importance in node_importance.items():
                    if importance >= top_threshold:
                        layers["top"].append(node)
                    elif importance >= bottom_threshold:
                        layers["middle"].append(node)
                    else:
                        layers["bottom"].append(node)
            
            # 3. 为每层创建子图并进行布局
            layer_positions = {}
            layer_y_positions = {"top": 1.5, "middle": 0.0, "bottom": -1.5}
            
            for layer_name, nodes in layers.items():
                if not nodes:
                    continue
                    
                # 创建子图
                subgraph = G.subgraph(nodes)
                
                if subgraph.number_of_nodes() == 1:
                    # 单节点直接放置
                    layer_positions[layer_name] = {nodes[0]: (0, layer_y_positions[layer_name])}
                else:
                    # 多节点使用力导向布局
                    # 根据节点数量调整布局参数
                    if subgraph.number_of_nodes() <= 5:
                        k = 0.5
                        scale = 1.0
                    elif subgraph.number_of_nodes() <= 10:
                        k = 0.3
                        scale = 1.5
                    else:
                        k = 0.2
                        scale = 2.0
                    
                    # 计算子图布局
                    sub_pos = nx.spring_layout(
                        subgraph,
                        weight="weight",
                        k=k,
                        iterations=500,
                        seed=42,
                        scale=scale
                    )
                    
                    # 调整y坐标到层次位置
                    layer_positions[layer_name] = {}
                    for node, (x, y) in sub_pos.items():
                        layer_positions[layer_name][node] = (x, layer_y_positions[layer_name] + y * 0.3)
            
            # 4. 合并所有层次的位置
            pos = {}
            for layer_positions_dict in layer_positions.values():
                pos.update(layer_positions_dict)
                
            # 对多层次布局应用碰撞检测
            node_radii = {}
            for i, node in enumerate(G.nodes()):
                area = node_sizes[i]
                radius = math.sqrt(area / math.pi) / 100
                node_radii[node] = max(radius, 0.1)
            
            pos = self._apply_collision_detection(G, pos, node_radii, iterations=40)
                
        elif layout_style == "community":
            # 基于社区检测的布局，先分簇，再布局
            if community_louvain is None:
                logger.warning("未安装 python-louvain，无法使用社区布局，降级为 force_directed")
                # 降级到 force_directed 布局
                num_nodes = G.number_of_nodes()
                num_edges = G.number_of_edges()
                if num_nodes > 1:
                    max_possible_edges = num_nodes * (num_nodes - 1) / 2
                    density = num_edges / max_possible_edges
                else:
                    density = 0.0
                base_k = 1.0 / math.sqrt(num_nodes) if num_nodes > 0 else 1.0
                density_factor = 0.5 + 2.5 * (density ** 2)
                k = base_k * density_factor
                initial_pos = nx.circular_layout(G, scale=1)
                pos = nx.spring_layout(
                    G, pos=initial_pos, weight="weight", k=k, iterations=2000,
                    threshold=1e-4, seed=42, scale=2, center=(0, 0)
                )
            else:
                # 1. 检测社区
                partition = community_louvain.best_partition(G, weight='weight')
                communities = {}
                for node, community_id in partition.items():
                    communities.setdefault(community_id, []).append(node)
                
                # 2. 为每个社区内部进行布局
                community_pos = {}
                intra_community_scale = 1  # 社区内部布局的缩放，必须为整数
                
                for comm_id, nodes_in_comm in communities.items():
                    subgraph = G.subgraph(nodes_in_comm)
                    if subgraph.number_of_nodes() > 1:
                        # 社区内部也使用多阶段布局
                        sub_initial_pos = nx.circular_layout(subgraph, scale=intra_community_scale)
                        sub_pos = nx.spring_layout(
                            subgraph, pos=sub_initial_pos, weight="weight",
                            k=0.5 / math.sqrt(subgraph.number_of_nodes()), # 社区内部k值更小，更紧密
                            iterations=500, seed=42, scale=intra_community_scale
                        )
                        community_pos[comm_id] = sub_pos
                    else: # 单节点社区
                        community_pos[comm_id] = {nodes_in_comm[0]: (0,0)}

                # 3. 将社区视为超级节点，进行社区间布局
                # 创建一个新图，节点是社区，边是社区间的连接权重
                community_graph = nx.Graph()
                for comm_id in communities:
                    community_graph.add_node(comm_id)
                
                # 计算社区间的总连接权重
                inter_comm_weights = {}
                for u, v, data in G.edges(data=True):
                    comm_u = partition[u]
                    comm_v = partition[v]
                    if comm_u != comm_v:
                        key = (min(comm_u, comm_v), max(comm_u, comm_v))
                        inter_comm_weights[key] = inter_comm_weights.get(key, 0) + float(data.get('weight', 1.0))
                
                for (comm_u, comm_v), weight in inter_comm_weights.items():
                    community_graph.add_edge(comm_u, comm_v, weight=weight)
                
                # 对社区图进行布局
                if community_graph.number_of_nodes() > 1:
                    # 社区间布局也使用多阶段布局
                    comm_initial_pos = nx.circular_layout(community_graph, scale=5.0) # 社区间距离更大
                    inter_community_pos = nx.spring_layout(
                        community_graph, pos=comm_initial_pos, weight='weight',
                        k=2.0 / math.sqrt(community_graph.number_of_nodes()), # 社区间k值较大
                        iterations=1000, seed=42, scale=5.0
                    )
                else: # 只有一个社区
                    inter_community_pos = {list(communities.keys())[0]: (0,0)}

                # 4. 合并布局
                final_pos = {}
                for comm_id, nodes_in_comm in communities.items():
                    # 社区的中心位置
                    comm_center_x, comm_center_y = inter_community_pos[comm_id]
                    for node in nodes_in_comm:
                        # 节点在社区内部的相对位置
                        rel_x, rel_y = community_pos[comm_id][node]
                        # 最终位置 = 社区中心 + 相对位置
                        final_pos[node] = (comm_center_x + rel_x, comm_center_y + rel_y)
                pos = final_pos
                
                # 对社区布局应用碰撞检测
                node_radii = {}
                for i, node in enumerate(G.nodes()):
                    area = node_sizes[i]
                    radius = math.sqrt(area / math.pi) / 100
                    node_radii[node] = max(radius, 0.1)
                
                pos = self._apply_collision_detection(G, pos, node_radii, iterations=40)
        else:
            # 默认使用force-directed布局
            num_nodes = G.number_of_nodes()
            num_edges = G.number_of_edges()
            if num_nodes > 1:
                max_possible_edges = num_nodes * (num_nodes - 1) / 2
                density = num_edges / max_possible_edges
            else:
                density = 0.0
            base_k = 1.0 / math.sqrt(num_nodes) if num_nodes > 0 else 1.0
            density_factor = 0.5 + 2.5 * (density ** 2)
            k = base_k * density_factor
            initial_pos = nx.circular_layout(G, scale=1)
            pos = nx.spring_layout(
                G, pos=initial_pos, weight="weight", k=k, iterations=2000,
                threshold=1e-4, seed=42, scale=2, center=(0, 0)
            )

        # 7) 图像尺寸(随节点数量略增)
        base_w, base_h = 10.0, 7.0
        extra = min(6.0, max(0.0, (G.number_of_nodes() - 30) * 0.05))
        fig_w = base_w + extra
        fig_h = base_h + extra * 0.6

        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
        ax.set_axis_off()
        ax.set_title(f"记忆图谱  节点:{G.number_of_nodes()} 边:{G.number_of_edges()}", fontsize=12, pad=12,
                    fontproperties=self.font_prop if hasattr(self, 'font_prop') else None)

        # 8) 画边: 强度越大, 线越粗/越深
        if G.number_of_edges() > 0:
            strengths = [float(G.edges[e].get("weight", 0.0)) for e in G.edges()]
            if strengths:
                s_min, s_max = min(strengths), max(strengths)
                widths = []
                alphas = []
                edge_colors = []
                
                # 计算边的强度中位数，用于区分重要连接
                s_median = sorted(strengths)[len(strengths)//2] if strengths else 0.05
                
                for s in strengths:
                    if s_max > s_min:
                        norm = (s - s_min) / (s_max - s_min)
                    else:
                        norm = 0.5
                    
                    # 根据强度调整边宽，重要连接更粗
                    if s >= s_median:
                        # 中位数以上的连接，使用更粗的线
                        width = 1.0 + 5.0 * norm  # 1.0 ~ 6.0
                        alpha = 0.5 + 0.5 * norm   # 0.5 ~ 1.0，更高透明度
                        # 重要连接使用更明显的颜色，从深蓝到深红
                        red_component = 0.2 + 0.6 * norm
                        blue_component = 0.8 - 0.6 * norm
                        edge_color = (red_component, 0.1, blue_component, alpha)
                    else:
                        # 中位数以下的连接，使用较细的线
                        width = 0.5 + 1.5 * norm  # 0.5 ~ 2.0
                        alpha = 0.2 + 0.3 * norm   # 0.2 ~ 0.5，较低透明度
                        # 次要连接使用灰色系
                        gray_value = 0.3 + 0.4 * norm
                        edge_color = (gray_value, gray_value, gray_value, alpha)
                    
                    widths.append(width)
                    alphas.append(alpha)
                    edge_colors.append(edge_color)
            else:
                widths = [1.5] * G.number_of_edges()  # 默认边宽增加，确保可见
                edge_colors = [(0.4, 0.4, 0.4, 0.6)] * G.number_of_edges()  # 默认颜色更明显

            # 减少边交叉的策略：使用曲线绘制边，并调整连接样式
            # 对于大型图，使用更智能的边绘制策略
            if G.number_of_edges() > 15:
                # 对于边较多的图，使用弧形连接减少交叉
                connectionstyle = "arc3,rad=0.2"
            else:
                # 对于边较少的图，使用直线连接
                connectionstyle = "arc3,rad=0.0"
            
            # 确保边是可见的，使用更高的alpha值
            nx.draw_networkx_edges(
                G, pos, ax=ax, width=widths, edge_color=edge_colors,
                alpha=0.8, connectionstyle=connectionstyle
            )
            
            # 添加边的强度标签，对重要连接显示强度值
            if G.number_of_edges() <= 20:  # 只在边数量较少时显示标签，避免混乱
                edge_labels = {}
                for u, v, data in G.edges(data=True):
                    strength = float(data.get("weight", 0.0))
                    if strength >= s_median:  # 只显示重要连接的强度
                        edge_labels[(u, v)] = f"{strength:.2f}"
                
                if edge_labels:
                    nx.draw_networkx_edge_labels(
                        G, pos, ax=ax, edge_labels=edge_labels,
                        font_size=8, font_color="#d32f2f", font_weight='bold',
                        fontproperties=self.font_prop if hasattr(self, 'font_prop') else None
                    )
        else:
            logger.info("无边可画(无连接或均被过滤)")

        # 9) 画点与标签
        nx.draw_networkx_nodes(G, pos, ax=ax, node_size=node_sizes, node_color=node_colors, linewidths=0.5, edgecolors="#37474f")
        # 增大标签字体，确保文字清晰可见，使用正确的字体
        # 对于节点标签，需要单独绘制每个标签以确保字体正确应用
        for node, (x, y) in pos.items():
            if node in labels:
                label = labels[node]
                ax.text(x, y, label, fontsize=10, fontweight='bold', color="#263238",
                       ha='center', va='center',
                       fontproperties=self.font_prop if hasattr(self, 'font_prop') else None)

        # 10) 图例(用文本方式)
        legend_text = "颜色: 红=印象, 绿=重要(强度高), 蓝=普通\n大小=记忆数量与强度 | 边粗/短=连接强"
        ax.text(0.01, 0.01, legend_text, transform=ax.transAxes, fontsize=8, color="#455a64", va="bottom",
                fontproperties=self.font_prop if hasattr(self, 'font_prop') else None)

        # 11) 保存到数据目录 graphs/
        data_dir = os.path.dirname(self.ms.db_path) if hasattr(self.ms, "db_path") else os.getcwd()
        out_dir = os.path.join(data_dir, "graphs")
        os.makedirs(out_dir, exist_ok=True)
        filename = f"memory_graph_{int(time.time())}.png"
        out_path = os.path.abspath(os.path.join(out_dir, filename))

        plt.tight_layout()
        try:
            fig.savefig(out_path, bbox_inches="tight")
        finally:
            plt.close(fig)

        logger.debug(f"记忆图谱已生成: {out_path}")
        return out_path

    def _apply_collision_detection(self, G: Any, pos: Dict[str, tuple], node_radii: Dict[str, float], iterations: int = 50) -> Dict[str, tuple]:
        """
        应用碰撞检测和分离算法，确保节点不重叠
        
        Args:
            G: NetworkX图对象
            pos: 节点位置字典 {node_id: (x, y)}
            node_radii: 节点半径字典 {node_id: radius}
            iterations: 迭代次数
            
        Returns:
            优化后的节点位置字典
        """
        import random
        
        # 转换为可变字典
        new_pos = {node: list(position) for node, position in pos.items()}
        nodes = list(G.nodes())
        
        # 增加迭代次数，确保充分分离
        iterations = max(iterations, 100)
        
        # 迭代优化
        for iteration in range(iterations):
            has_collision = False
            max_overlap = 0
            
            # 检查所有节点对
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    node_i = nodes[i]
                    node_j = nodes[j]
                    
                    # 计算节点间距离
                    dx = new_pos[node_j][0] - new_pos[node_i][0]
                    dy = new_pos[node_j][1] - new_pos[node_i][1]
                    distance = math.sqrt(dx*dx + dy*dy)
                    
                    # 计算最小安全距离（两个节点半径之和加上更多缓冲）
                    buffer_factor = 0.1  # 增加缓冲空间
                    min_distance = node_radii[node_i] + node_radii[node_j] + buffer_factor
                    
                    # 如果发生碰撞
                    if distance < min_distance and distance > 0:
                        has_collision = True
                        
                        # 计算重叠量
                        overlap = min_distance - distance
                        max_overlap = max(max_overlap, overlap)
                        
                        # 计算单位方向向量
                        dx_norm = dx / distance
                        dy_norm = dy / distance
                        
                        # 使用更强的排斥力，特别是对于严重重叠的节点
                        force_multiplier = 1.5 if overlap > 0.1 else 1.0
                        
                        # 根据节点大小比例分配移动距离
                        # 大节点移动较少，小节点移动较多
                        total_size = node_radii[node_i] + node_radii[node_j]
                        move_i = overlap * force_multiplier * (node_radii[node_j] / total_size)
                        move_j = overlap * force_multiplier * (node_radii[node_i] / total_size)
                        
                        # 应用排斥力，移动节点
                        new_pos[node_i][0] -= dx_norm * move_i
                        new_pos[node_i][1] -= dy_norm * move_i
                        new_pos[node_j][0] += dx_norm * move_j
                        new_pos[node_j][1] += dy_norm * move_j
            
            # 如果没有碰撞，提前结束
            if not has_collision:
                break
                
            # 动态调整阻尼系数
            # 前期使用较小的阻尼，后期使用较大的阻尼
            if iteration < iterations * 0.3:
                # 前期：快速分离
                damping = 1.0
            elif iteration < iterations * 0.7:
                # 中期：逐渐稳定
                damping = 0.95
            else:
                # 后期：精细调整
                damping = 0.98
                
            # 应用阻尼
            for node in nodes:
                new_pos[node][0] *= damping
                new_pos[node][1] *= damping
        
        # 最终检查：如果仍有碰撞，进行最后的强制分离
        final_separation_applied = False
        for _ in range(20):  # 最多尝试20次
            has_collision = False
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    node_i = nodes[i]
                    node_j = nodes[j]
                    
                    dx = new_pos[node_j][0] - new_pos[node_i][0]
                    dy = new_pos[node_j][1] - new_pos[node_i][1]
                    distance = math.sqrt(dx*dx + dy*dy)
                    
                    min_distance = node_radii[node_i] + node_radii[node_j] + 0.05
                    
                    if distance < min_distance and distance > 0:
                        has_collision = True
                        final_separation_applied = True
                        
                        # 强制分离
                        overlap = min_distance - distance
                        dx_norm = dx / distance
                        dy_norm = dy / distance
                        
                        # 平均分配移动距离
                        move = overlap * 0.6  # 强制分离使用更大的移动系数
                        
                        new_pos[node_i][0] -= dx_norm * move
                        new_pos[node_i][1] -= dy_norm * move
                        new_pos[node_j][0] += dx_norm * move
                        new_pos[node_j][1] += dy_norm * move
            
            if not has_collision:
                break
        
        # 将位置转换回元组格式
        return {node: (position[0], position[1]) for node, position in new_pos.items()}