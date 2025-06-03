<template>
  <div id="long-term-memory" class="flex-grow-1" style="display: flex; flex-direction: row; ">
    <!-- <div id="graph-container"
      style="flex-grow: 1; width: 100%; border: 1px solid #eee; border-radius: 8px; max-height: calc(100% - 40px);">
    </div> -->
    <div id="graph-container-nonono"
      style="display: flex; justify-content: center; align-items: center; width: 100%; font-weight: 1000; font-size: 24px;">
      加速开发中...
    </div>
    <div id="graph-control-panel"
      style="min-width: 450px; border: 1px solid #eee; border-radius: 8px; padding: 16px; padding-bottom: 0px; margin-left: 16px; max-height: calc(100% - 40px);">
      <div>
        <!-- <span style="color: #333333;">可视化</span> -->
        <h3>筛选</h3>
        <div style="margin-top: 8px;">
          <v-autocomplete v-model="searchUserId" density="compact" :items="userIdList" variant="outlined"
            label="筛选用户 ID"></v-autocomplete>
        </div>
        <div style="display: flex; gap: 8px;">
          <v-btn color="primary" @click="onNodeSelect" variant="tonal">
            <v-icon start>mdi-magnify</v-icon>
            筛选
          </v-btn>
          <v-btn color="secondary" @click="resetFilter" variant="tonal">
            <v-icon start>mdi-filter-remove</v-icon>
            重置筛选
          </v-btn>
          <v-btn color="primary" @click="refreshGraph" variant="tonal">
            <v-icon start>mdi-refresh</v-icon>
            刷新图形
          </v-btn>
        </div>
      </div>

      <!-- 新增搜索记忆功能 -->
      <div class="mt-4">
        <h3>搜索记忆</h3>
        <v-card variant="outlined" class="mt-2 pa-3">
          <div>
            <v-text-field v-model="searchMemoryUserId" label="用户 ID" variant="outlined" density="compact" hide-details
              class="mb-2"></v-text-field>
            <v-text-field v-model="searchQuery" label="输入关键词" variant="outlined" density="compact" hide-details
              @keyup.enter="searchMemory" class="mb-2"></v-text-field>
            <v-btn color="info" @click="searchMemory" :loading="isSearching" variant="tonal">
              <v-icon start>mdi-text-search</v-icon>
              搜索
            </v-btn>
          </div>

          <!-- 新增搜索结果展示区域 -->
          <div v-if="searchResults.length > 0" class="mt-3">
            <v-divider class="mb-3"></v-divider>
            <div class="text-subtitle-1 mb-2">搜索结果 ({{ searchResults.length }})</div>
            <v-expansion-panels variant="accordion">
              <v-expansion-panel v-for="(result, index) in searchResults" :key="index">
                <v-expansion-panel-title>
                  <div>
                    <span class="text-truncate d-inline-block" style="max-width: 300px;">{{ result.text.substring(0, 30)
                      }}...</span>
                    <span class="ms-2 text-caption text-grey">(相关度: {{ (result.score * 100).toFixed(1) }}%)</span>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <div>
                    <div class="mb-2 text-body-1">{{ result.text }}</div>
                    <div class="d-flex">
                      <span class="text-caption text-grey">文档ID: {{ result.doc_id }}</span>
                    </div>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </div>
          <div v-else-if="hasSearched" class="mt-3 text-center text-body-1 text-grey">
            未找到相关记忆内容
          </div>
        </v-card>
      </div>

      <!-- 新增添加记忆数据的表单 -->
      <div class="mt-4">
        <h3>添加记忆数据</h3>
        <v-card variant="outlined" class="mt-2 pa-3">
          <v-form @submit.prevent="addMemoryData">
            <v-textarea v-model="newMemoryText" label="输入文本内容" variant="outlined" rows="4" hide-details
              class="mb-2"></v-textarea>

            <v-text-field v-model="newMemoryUserId" label="用户 ID" variant="outlined" density="compact"
              hide-details></v-text-field>

            <v-switch v-model="needSummarize" color="primary" label="需要摘要" hide-details></v-switch>

            <v-btn color="success" type="submit" :loading="isSubmitting" :disabled="!newMemoryText || !newMemoryUserId">
              <v-icon start>mdi-plus</v-icon>
              添加数据
            </v-btn>
          </v-form>
        </v-card>
      </div>

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
</template>

<script>
import axios from 'axios';
import * as d3 from "d3"; // npm install d3

export default {
  name: 'LongTermMemory',
  data() {
    return {
      simulation: null,
      svg: null,
      zoom: null,
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
      isLoading: false,
      // 添加新的数据属性
      newMemoryText: '',
      newMemoryUserId: null,
      needSummarize: false,
      isSubmitting: false,
      // 搜索记忆相关属性
      searchMemoryUserId: null,
      searchQuery: '',
      isSearching: false,
      searchResults: [],
      hasSearched: false,
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
  methods: {
    // 添加搜索记忆方法
    searchMemory() {
      if (!this.searchQuery.trim()) {
        this.$toast.warning('请输入搜索关键词');
        return;
      }

      this.isSearching = true;
      this.hasSearched = true;
      this.searchResults = [];

      // 构建查询参数
      const params = {
        query: this.searchQuery
      };

      // 如果有选择用户ID，也加入查询参数
      if (this.searchMemoryUserId) {
        params.user_id = this.searchMemoryUserId;
      }

      axios.get('/api/plug/alkaid/ltm/graph/search', { params })
        .then(response => {
          if (response.data.status === 'ok') {
            const data = response.data.data;

            // 处理返回的文档数组
            this.searchResults = Object.keys(data).map(doc_id => {
              return {
                doc_id: doc_id,
                text: data[doc_id].text || '无文本内容',
                score: data[doc_id].score || 0
              };
            });

            if (this.searchResults.length === 0) {
              this.$toast.info('未找到相关记忆内容');
            } else {
              this.$toast.success(`找到 ${this.searchResults.length} 条相关记忆`);
            }
          } else {
            this.$toast.error('搜索失败: ' + response.data.message);
          }
        })
        .catch(error => {
          console.error('搜索记忆数据失败:', error);
          this.$toast.error('搜索失败: ' + (error.response?.data?.message || error.message));
        })
        .finally(() => {
          this.isSearching = false;
        });
    },

    // 添加新方法，用于提交记忆数据
    addMemoryData() {
      if (!this.newMemoryText || !this.newMemoryUserId) {
        return;
      }

      this.isSubmitting = true;

      // 准备提交数据
      const payload = {
        text: this.newMemoryText,
        user_id: this.newMemoryUserId,
        need_summarize: this.needSummarize
      };

      axios.post('/api/plug/alkaid/ltm/graph/add', payload)
        .then(response => {
          // 成功添加后刷新图表
          this.refreshGraph();

          // 重置表单
          // this.newMemoryText = '';
          // this.needSummarize = false;

          // 显示成功消息
          this.$toast.success('记忆数据添加成功！');
        })
        .catch(error => {
          console.error('添加记忆数据失败:', error);
          this.$toast.error('添加记忆数据失败: ' + (error.response?.data?.message || error.message));
        })
        .finally(() => {
          this.isSubmitting = false;
        });
    },

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
      this.searchQuery = '';  // 重置搜索关键词
      this.searchResults = []; // 清空搜索结果
      this.hasSearched = false; // 重置搜索状态
      this.ltmGetGraph();
    },

    initD3Graph() {
      const container = document.getElementById("graph-container");
      if (!container) return;
      d3.select("#graph-container svg").remove();
      const width = container.clientWidth;
      const height = container.clientHeight;
      const svg = d3.select("#graph-container")
        .append("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", [0, 0, width, height])
        .classed("d3-graph", true);
      const g = svg.append("g");
      const zoom = d3.zoom()
        .scaleExtent([0.1, 10])
        .on("zoom", (event) => {
          g.attr("transform", event.transform);
        });

      svg.call(zoom);
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
      g.selectAll("*").remove();
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
      const link = g.append("g")
        .selectAll("line")
        .data(this.links)
        .join("line")
        .attr("stroke", d => d.color)
        .attr("stroke-width", 1.5)
        .attr("marker-end", "url(#arrowhead)");
      const edgeLabels = g.append("g")
        .selectAll("text")
        .data(this.links)
        .join("text")
        .text(d => d.label)
        .attr("font-size", "8px")
        .attr("text-anchor", "middle")
        .attr("fill", "#666")
        .attr("dy", -5);
      const node = g.append("g")
        .selectAll("circle")
        .data(this.nodes)
        .join("circle")
        .attr("r", 8)
        .attr("fill", d => d.color)
        .style("cursor", "pointer")
        .call(this.dragBehavior());
      const nodeLabels = g.append("g")
        .selectAll("text")
        .data(this.nodes)
        .join("text")
        .text(d => d.label)
        .attr("font-size", "10px")
        .attr("text-anchor", "middle")
        .attr("fill", "#333")
        .attr("dy", -12);
      node.on("click", (event, d) => {
        event.stopPropagation();
        this.selectedNode = d.originalData;
      });
      this.svg.on("click", () => {
        this.selectedNode = null;
      });
      this.simulation
        .nodes(this.nodes)
        .on("tick", () => {
          link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);
          edgeLabels
            .attr("x", d => (d.source.x + d.target.x) / 2)
            .attr("y", d => (d.source.y + d.target.y) / 2);
          node
            .attr("cx", d => d.x)
            .attr("cy", d => d.y);
          nodeLabels
            .attr("x", d => d.x)
            .attr("y", d => d.y);
        });

      this.simulation.force("link")
        .links(this.links);

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
  }
}
</script>

<style scoped>
#long-term-memory {
  height: 100%;
  max-height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: row;
}

#graph-container {
  position: relative;
  background-color: #f2f6f9;
  overflow: hidden;
  height: 100%;
  flex-grow: 1;
}

#graph-control-panel {
  overflow-y: auto;
  /* 让控制面板可滚动而不是整个页面滚动 */
  min-width: 450px;
  max-width: 450px;
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
