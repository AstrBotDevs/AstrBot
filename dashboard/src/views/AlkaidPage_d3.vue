<script setup>
// 在较庞大的图下，d3 的性能不如 sigma.js 渲染库，因此我们优先使用 sigma.js 来渲染图。
import * as d3 from "d3"; // npm install d3
</script>


<template>
  <v-card style="height: 100%; width: 100%;">
    <v-card-text class="pa-4" style="height: 100%;">
      <v-container fluid class="d-flex flex-column" style="height: 100%;">
        <div style="margin-bottom: 32px;">
          <h1 class="gradient-text">The Alkaid Project.</h1>
          <small style="color: #a3a3a3;">AstrBot 实验性项目</small>
        </div>

        <div style="display: flex; gap: 8px; margin-bottom: 16px;">
          <v-btn size="large" :variant="activeTab === 'long-term-memory' ? 'flat' : 'tonal'"
            :color="activeTab === 'long-term-memory' ? '#9b72cb' : ''" rounded="lg"
            @click="activeTab = 'long-term-memory'">
            <v-icon start>mdi-dots-hexagon</v-icon>
            长期记忆层
          </v-btn>
          <v-btn size="large" :variant="activeTab === 'other' ? 'flat' : 'tonal'"
            :color="activeTab === 'other' ? '#9b72cb' : ''" rounded="lg" @click="activeTab = 'other'">
            <v-icon start>mdi-dots-horizontal</v-icon>
            其他
          </v-btn>
        </div>

        <div v-if="activeTab === 'long-term-memory'" id="long-term-memory" class="flex-grow-1"
          style="display: flex; flex-direction: row;">
          <div id="graph-container" style="flex-grow: 1; width: 100%; border: 1px solid #eee; border-radius: 8px;">
          </div>
          <div id="graph-control-panel"
            style="min-width: 450px; border: 1px solid #eee; border-radius: 8px; padding: 16px; margin-left: 16px;">
            <div>
              <span style="color: #333333;">可视化</span>
              <div style="margin-top: 8px;">
                <v-autocomplete v-model="searchUserId" :items="userIdList" variant="outlined"
                  label="筛选用户 ID"></v-autocomplete>
                <v-btn color="primary" @click="onNodeSelect" variant="tonal" style="margin-top: 8px;">
                  <v-icon start>mdi-magnify</v-icon>
                  筛选
                </v-btn>
                <v-btn color="secondary" @click="resetFilter" variant="tonal"
                  style="margin-top: 8px; margin-left: 8px;">
                  <v-icon start>mdi-filter-remove</v-icon>
                  重置筛选
                </v-btn>
              </div>
              <div style="margin-top: 16px;">
                <v-btn color="primary" @click="refreshGraph" variant="tonal">
                  <v-icon start>mdi-refresh</v-icon>
                  刷新图形
                </v-btn>
              </div>
            </div>

            <v-divider class="my-4"></v-divider>

            <div v-if="selectedNode" class="mt-4">
              <h3>节点详情</h3>
              <v-card variant="outlined" class="mt-2 pa-3">
                <div v-if="selectedNode.id">
                  <div class="d-flex justify-space-between">
                    <span class="text-subtitle-2">ID:</span>
                    <span>{{ selectedNode.id }}</span>
                  </div>
                </div>
                <div v-if="selectedNode._label">
                  <div class="d-flex justify-space-between">
                    <span class="text-subtitle-2">类型:</span>
                    <span>{{ selectedNode._label }}</span>
                  </div>
                </div>
                <div v-if="selectedNode.name">
                  <div class="d-flex justify-space-between">
                    <span class="text-subtitle-2">名称:</span>
                    <span>{{ selectedNode.name }}</span>
                  </div>
                </div>
                <div v-if="selectedNode.user_id">
                  <div class="d-flex justify-space-between">
                    <span class="text-subtitle-2">用户ID:</span>
                    <span>{{ selectedNode.user_id }}</span>
                  </div>
                </div>
                <div v-if="selectedNode.ts">
                  <div class="d-flex justify-space-between">
                    <span class="text-subtitle-2">时间戳:</span>
                    <span>{{ selectedNode.ts }}</span>
                  </div>
                </div>
                <div v-if="selectedNode.type">
                  <div class="d-flex justify-space-between">
                    <span class="text-subtitle-2">类型:</span>
                    <span>{{ selectedNode.type }}</span>
                  </div>
                </div>
              </v-card>
            </div>

            <div v-if="graphStats" class="mt-4">
              <h3>图形统计</h3>
              <v-card variant="outlined" class="mt-2 pa-3">
                <div class="d-flex justify-space-between">
                  <span class="text-subtitle-2">节点数:</span>
                  <span>{{ graphStats.nodeCount }}</span>
                </div>
                <div class="d-flex justify-space-between">
                  <span class="text-subtitle-2">边数:</span>
                  <span>{{ graphStats.edgeCount }}</span>
                </div>
              </v-card>
            </div>
          </div>
        </div>

        <div v-if="activeTab === 'other'" class="flex-grow-1" style="display: flex; flex-direction: column;">
          <div class="d-flex align-center justify-center"
            style="flex-grow: 1; width: 100%; border: 1px solid #eee; border-radius: 8px;">
            <v-icon size="64" color="grey-lighten-1">mdi-tools</v-icon>
            <p class="text-h6 text-grey ml-4">功能开发中</p>
          </div>
        </div>

      </v-container>
    </v-card-text>
  </v-card>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
export default {
  name: 'AlkaidPage',
  components: {
    AstrBotConfig,
    WaitingForRestart
  },
  data() {
    return {
      simulation: null,
      svg: null,
      zoom: null,
      activeTab: 'long-term-memory',
      node_data: [],
      edge_data: [],
      nodes: [],
      links: [],
      searchUserId: null,
      userIdList: [],
      selectedNode: null,
      graphStats: null,
      nodeColors: {
        'PhaseNode': '#4CAF50',  // 绿色
        'PassageNode': '#2196F3', // 蓝色
        'FactNode': '#FF9800',    // 橙色
        'default': '#9C27B0'      // 紫色作为默认
      },
      edgeColors: {
        '_include_': '#607D8B',
        '_related_': '#9E9E9E',
        'default': '#BDBDBD'
      },
      isLoading: false
    }
  },
  mounted() {
    this.initD3Graph();
    this.ltmGetGraph();
    this.ltmGetUserIds();
  },
  beforeUnmount() {
    if (this.simulation) {
      this.simulation.stop();
    }
  },
  watch: {
    activeTab(newVal) {
      if (newVal === 'long-term-memory') {
        this.$nextTick(() => {
          if (!this.svg) {
            this.initD3Graph();
          }
        });
      } else {
        if (this.simulation) {
          this.simulation.stop();
          this.simulation = null;
        }
        if (this.svg) {
          d3.select("#graph-container svg").remove();
          this.svg = null;
        }
      }
    }
  },
  methods: {
    ltmGetGraph(userId = null) {
      this.isLoading = true;
      const params = userId ? { user_id: userId } : {};

      axios.get('/api/plug/alkaid/ltm/graph', { params })
        .then(response => {
          let nodesRaw = response.data.data.nodes;
          let edgesRaw = response.data.data.edges;

          this.node_data = nodesRaw;
          this.edge_data = edgesRaw;

          // 转换为D3所需的数据格式
          this.nodes = nodesRaw.map(node => {
            const nodeId = node[0];
            const nodeData = node[1];
            const nodeType = nodeData._label || 'default';
            const color = this.nodeColors[nodeType] || this.nodeColors['default'];
            
            return {
              id: nodeId,
              label: nodeData.name || nodeId.split('_')[0],
              color: color,
              originalData: nodeData
            };
          });

          this.links = edgesRaw.map(edge => {
            const sourceId = edge[0];
            const targetId = edge[1];
            const edgeData = edge[2];
            const relationType = edgeData.relation_type || 'default';
            const color = this.edgeColors[relationType] || this.edgeColors['default'];
            
            return {
              source: sourceId,
              target: targetId,
              color: color,
              originalData: edgeData,
              label: relationType
            };
          });

          this.updateD3Graph();
          this.updateGraphStats();
          console.log('Graph initialized with', this.nodes.length, 'nodes and', this.links.length, 'links');
        })
        .catch(error => {
          console.error('Error fetching graph data:', error);
        })
        .finally(() => {
          this.isLoading = false;
        });
    },

    ltmGetUserIds() {
      axios.get('/api/plug/alkaid/ltm/user_ids')
        .then(response => {
          this.userIdList = response.data.data;
        })
        .catch(error => {
          console.error('Error fetching user IDs:', error);
        });
    },

    updateGraphStats() {
      this.graphStats = {
        nodeCount: this.nodes.length,
        edgeCount: this.links.length
      };
    },

    refreshGraph() {
      this.ltmGetGraph(this.searchUserId);
    },

    onNodeSelect() {
      console.log('Selected user ID:', this.searchUserId);
      if (!this.searchUserId) return;

      // 使用API的user_id参数筛选数据
      this.ltmGetGraph(this.searchUserId);
    },

    resetFilter() {
      this.searchUserId = null;
      this.ltmGetGraph();
    },

    initD3Graph() {
      const container = document.getElementById("graph-container");
      if (!container) return;

      // 清除旧的SVG元素
      d3.select("#graph-container svg").remove();

      // 获取容器尺寸
      const width = container.clientWidth;
      const height = container.clientHeight;

      // 创建SVG元素
      const svg = d3.select("#graph-container")
        .append("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", [0, 0, width, height])
        .classed("d3-graph", true);

      // 创建图形元素的容器
      const g = svg.append("g");

      // 添加缩放功能
      const zoom = d3.zoom()
        .scaleExtent([0.1, 10])
        .on("zoom", (event) => {
          g.attr("transform", event.transform);
        });

      svg.call(zoom);
      
      // 初始力导向模拟
      const simulation = d3.forceSimulation()
        .force("link", d3.forceLink().id(d => d.id).distance(100))
        .force("charge", d3.forceManyBody().strength(-300))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(30));

      this.svg = svg;
      this.g = g;
      this.zoom = zoom;
      this.simulation = simulation;
      this.width = width;
      this.height = height;
    },

    updateD3Graph() {
      if (!this.svg || !this.simulation) return;

      const g = this.g;

      // 清除先前的元素
      g.selectAll("*").remove();

      // 创建箭头标记
      g.append("defs").append("marker")
        .attr("id", "arrowhead")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 20)
        .attr("refY", 0)
        .attr("orient", "auto")
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "#999");

      // 创建边
      const link = g.append("g")
        .selectAll("line")
        .data(this.links)
        .join("line")
        .attr("stroke", d => d.color)
        .attr("stroke-width", 1.5)
        .attr("marker-end", "url(#arrowhead)");

      // 创建边上的文本标签
      const edgeLabels = g.append("g")
        .selectAll("text")
        .data(this.links)
        .join("text")
        .text(d => d.label)
        .attr("font-size", "8px")
        .attr("text-anchor", "middle")
        .attr("fill", "#666")
        .attr("dy", -5);

      // 创建节点
      const node = g.append("g")
        .selectAll("circle")
        .data(this.nodes)
        .join("circle")
        .attr("r", 8)
        .attr("fill", d => d.color)
        .style("cursor", "pointer")
        .call(this.dragBehavior());

      // 创建节点标签
      const nodeLabels = g.append("g")
        .selectAll("text")
        .data(this.nodes)
        .join("text")
        .text(d => d.label)
        .attr("font-size", "10px")
        .attr("text-anchor", "middle")
        .attr("fill", "#333")
        .attr("dy", -12);

      // 定义拖拽结束事件
      node.on("click", (event, d) => {
        event.stopPropagation();
        this.selectedNode = d.originalData;
      });

      // 画布点击事件，清除选中节点
      this.svg.on("click", () => {
        this.selectedNode = null;
      });

      // 更新力导向模拟
      this.simulation
        .nodes(this.nodes)
        .on("tick", () => {
          // 更新链接位置
          link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

          // 更新边标签位置
          edgeLabels
            .attr("x", d => (d.source.x + d.target.x) / 2)
            .attr("y", d => (d.source.y + d.target.y) / 2);

          // 更新节点位置
          node
            .attr("cx", d => d.x)
            .attr("cy", d => d.y);

          // 更新节点标签位置
          nodeLabels
            .attr("x", d => d.x)
            .attr("y", d => d.y);
        });

      this.simulation.force("link")
        .links(this.links);

      // 重启模拟
      this.simulation.alpha(1).restart();
    },

    dragBehavior() {
      return d3.drag()
        .on("start", (event, d) => {
          if (!event.active) this.simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) this.simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        });
    },

    getRandomColor() {
      const letters = '0123456789ABCDEF';
      let color = '#';
      for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
      }
      return color;
    }
  },
}

</script>

<style scoped>
.gradient-text {
  background: linear-gradient(74deg, #2abfe1 0, #9b72cb 25%, #b55908 50%, #d93025 100%);

  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: bold;
}

#graph-container {
  position: relative;
  background-color: #f2f6f9;
  overflow: hidden;
  min-height: 200px;
}

#graph-container:hover {
  cursor: pointer;
}

.memory-header {
  padding: 0 8px;
}

#graph-container svg {
  width: 100%;
  height: 100%;
}

.d3-graph {
  background-color: #f2f6f9;
}
</style>