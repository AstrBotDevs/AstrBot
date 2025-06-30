<template>
  <div id="long-term-memory" class="flex-grow-1" style="display: flex; flex-direction: row; ">
    <div id="graph-container"
      style="flex-grow: 1; width: 100%; border: 1px solid #eee; border-radius: 8px; max-height: calc(100% - 40px);">
    </div>
    <!-- <div id="graph-container-nonono"
      style="display: flex; justify-content: center; align-items: center; width: 100%; font-weight: 1000; font-size: 24px;">
      加速开发中...
    </div> -->
    <div id="graph-control-panel"
      style="min-width: 450px; border: 1px solid #eee; border-radius: 8px; padding: 16px; padding-bottom: 0px; margin-left: 16px; max-height: calc(100% - 40px);">
      <div>
        <!-- <span style="color: #333333;">可视化</span> -->
        <h3>{{ tm('filters.title') }}</h3>
        <div style="margin-top: 8px;">
          <v-autocomplete v-model="searchUserId" density="compact" :items="userIdList" variant="outlined"
            :label="tm('filters.userIdLabel')"></v-autocomplete>
        </div>
        <div style="display: flex; gap: 8px;">
          <v-btn color="primary" @click="onNodeSelect" variant="tonal">
            <v-icon start>mdi-magnify</v-icon>
            {{ tm('filters.filterButton') }}
          </v-btn>
          <v-btn color="secondary" @click="resetFilter" variant="tonal">
            <v-icon start>mdi-filter-remove</v-icon>
            {{ tm('filters.resetButton') }}
          </v-btn>
          <v-btn color="primary" @click="refreshGraph" variant="tonal">
            <v-icon start>mdi-refresh</v-icon>
            {{ tm('filters.refreshButton') }}
          </v-btn>
        </div>
      </div>

      <!-- 新增搜索记忆功能 -->
      <div class="mt-4">
        <h3>{{ tm('search.title') }}</h3>
        <v-card variant="outlined" class="mt-2 pa-3">
          <div>
            <v-text-field v-model="searchMemoryUserId" :label="tm('search.userIdLabel')" variant="outlined" density="compact" hide-details
              class="mb-2"></v-text-field>
            <v-text-field v-model="searchQuery" :label="tm('search.queryLabel')" variant="outlined" density="compact" hide-details
              @keyup.enter="searchMemory" class="mb-2"></v-text-field>
            <v-btn color="info" @click="searchMemory" :loading="isSearching" variant="tonal">
              <v-icon start>mdi-text-search</v-icon>
              {{ tm('search.searchButton') }}
            </v-btn>
          </div>

          <!-- 新增搜索结果展示区域 -->
          <div v-if="searchResults.length > 0" class="mt-3">
            <v-divider class="mb-3"></v-divider>
            <div class="text-subtitle-1 mb-2">{{ tm('search.resultsTitle') }} ({{ searchResults.length }})</div>
            <v-expansion-panels variant="accordion">
              <v-expansion-panel v-for="(result, index) in searchResults" :key="index">
                <v-expansion-panel-title>
                  <div>
                    <span class="text-truncate d-inline-block" style="max-width: 300px;">{{ result.text.substring(0, 30)
                      }}...</span>
                    <span class="ms-2 text-caption text-grey">({{ tm('search.similarity') }}: {{ (result.score * 100).toFixed(1) }}%)</span>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <div>
                    <div class="mb-2 text-body-1">{{ result.text }}</div>
                    <div class="d-flex">
                      <span class="text-caption text-grey">{{ tm('factDialog.docId') }}: {{ result.doc_id }}</span>
                    </div>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </div>
          <div v-else-if="hasSearched" class="mt-3 text-center text-body-1 text-grey">
            {{ tm('search.noResults') }}
          </div>
        </v-card>
      </div>

      <!-- 新增添加记忆数据的表单 -->
      <div class="mt-4">
        <h3>{{ tm('addMemory.title') }}</h3>
        <v-card variant="outlined" class="mt-2 pa-3">
          <v-form @submit.prevent="addMemoryData">
            <v-textarea v-model="newMemoryText" :label="tm('addMemory.textLabel')" variant="outlined" rows="4" hide-details
              class="mb-2"></v-textarea>

            <v-text-field v-model="newMemoryUserId" :label="tm('addMemory.userIdLabel')" variant="outlined" density="compact"
              hide-details></v-text-field>

            <v-switch v-model="needSummarize" color="primary" :label="tm('addMemory.summarizeLabel')" hide-details></v-switch>

            <v-btn color="success" type="submit" :loading="isSubmitting" :disabled="!newMemoryText || !newMemoryUserId">
              <v-icon start>mdi-plus</v-icon>
              {{ tm('addMemory.addButton') }}
            </v-btn>
          </v-form>
        </v-card>
      </div>

      <div v-if="selectedNode" class="mt-4">
        <h3>{{ tm('nodeDetails.title') }}</h3>
        <v-card variant="outlined" class="mt-2 pa-3">
          <div v-if="selectedNode.id">
            <div class="d-flex justify-space-between">
              <span class="text-subtitle-2">{{ tm('nodeDetails.id') }}:</span>
              <span>{{ selectedNode.id }}</span>
            </div>
          </div>
          <div v-if="selectedNode._label">
            <div class="d-flex justify-space-between">
              <span class="text-subtitle-2">{{ tm('nodeDetails.type') }}:</span>
              <span>{{ selectedNode._label }}</span>
            </div>
          </div>
          <div v-if="selectedNode.name">
            <div class="d-flex justify-space-between">
              <span class="text-subtitle-2">{{ tm('nodeDetails.name') }}:</span>
              <span>{{ selectedNode.name }}</span>
            </div>
          </div>
          <div v-if="selectedNode.user_id">
            <div class="d-flex justify-space-between">
              <span class="text-subtitle-2">{{ tm('nodeDetails.userId') }}:</span>
              <span>{{ selectedNode.user_id }}</span>
            </div>
          </div>
          <div v-if="selectedNode.ts">
            <div class="d-flex justify-space-between">
              <span class="text-subtitle-2">{{ tm('nodeDetails.timestamp') }}:</span>
              <span>{{ selectedNode.ts }}</span>
            </div>
          </div>
          <div v-if="selectedNode.type">
            <div class="d-flex justify-space-between">
              <span class="text-subtitle-2">{{ tm('nodeDetails.type') }}:</span>
              <span>{{ selectedNode.type }}</span>
            </div>
          </div>
        </v-card>
      </div>

      <div v-if="graphStats" class="mt-4">
        <h3>{{ tm('graphStats.title') }}</h3>
        <v-card variant="outlined" class="mt-2 pa-3">
          <div class="d-flex justify-space-between">
            <span class="text-subtitle-2">{{ tm('graphStats.nodeCount') }}:</span>
            <span>{{ graphStats.nodeCount }}</span>
          </div>
          <div class="d-flex justify-space-between">
            <span class="text-subtitle-2">{{ tm('graphStats.edgeCount') }}:</span>
            <span>{{ graphStats.edgeCount }}</span>
          </div>
        </v-card>
      </div>

      <v-dialog v-model="showFactDialog" max-width="550" scrollable>
        <v-card class="fact-detail-card">
          <v-card-title class="d-flex align-center bg-primary text-white px-4 py-3">
            <v-icon class="mr-2" color="white">mdi-memory</v-icon>
            {{ tm('factDialog.title') }}
            <v-spacer></v-spacer>
            <v-btn icon variant="text" color="white" @click="showFactDialog = false">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>
          
          <v-card-text class="px-4 pt-4 pb-0">
            <template v-if="selectedEdgeFactData">
              <v-alert color="primary" variant="tonal" density="compact" class="mb-4">
                <div class="text-body-1 font-weight-medium">{{ selectedEdgeFactData.text }}</div>
              </v-alert>
              
              <v-row>
                <v-col cols="6">
                  <div class="d-flex align-center mb-2">
                    <v-icon size="small" color="primary" class="mr-2">mdi-identifier</v-icon>
                    <div class="text-subtitle-2">{{ tm('factDialog.id') }}</div>
                  </div>
                  <div class="text-body-2 text-grey pa-1">{{ selectedEdgeFactData.id }}</div>
                </v-col>
                <v-col cols="6">
                  <div class="d-flex align-center mb-2">
                    <v-icon size="small" color="primary" class="mr-2">mdi-file-document-outline</v-icon>
                    <div class="text-subtitle-2">{{ tm('factDialog.docId') }}</div>
                  </div>
                  <div class="text-body-2 text-grey pa-1">{{ selectedEdgeFactData.doc_id }}</div>
                </v-col>
              </v-row>
              
              <!-- 时间信息 -->
              <v-row class="mt-2">
                <v-col cols="6">
                  <div class="d-flex align-center mb-2">
                    <v-icon size="small" color="primary" class="mr-2">mdi-calendar-plus</v-icon>
                    <div class="text-subtitle-2">{{ tm('factDialog.createdAt') }}</div>
                  </div>
                  <div class="text-body-2 text-grey pa-1">{{ formatTime(selectedEdgeFactData.created_at) }}</div>
                </v-col>
                <v-col cols="6">
                  <div class="d-flex align-center mb-2">
                    <v-icon size="small" color="primary" class="mr-2">mdi-calendar-edit</v-icon>
                    <div class="text-subtitle-2">{{ tm('factDialog.updatedAt') }}</div>
                  </div>
                  <div class="text-body-2 text-grey pa-1">{{ formatTime(selectedEdgeFactData.updated_at) }}</div>
                </v-col>
              </v-row>

              <!-- 改进元数据展示，解析为键值对 -->
              <div v-if="parsedMetadata && Object.keys(parsedMetadata).length > 0" class="mt-4">
                <div class="d-flex align-center mb-2">
                  <v-icon size="small" color="primary" class="mr-2">mdi-database-cog</v-icon>
                  <div class="text-subtitle-2">{{ tm('factDialog.metadata') }}</div>
                </div>
                <v-card variant="outlined" class="metadata-table">
                  <v-table density="compact" hover>
                    <thead>
                      <tr>
                        <th class="text-left">{{ tm('factDialog.metadataKey') }}</th>
                        <th class="text-left">{{ tm('factDialog.metadataValue') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(value, key) in parsedMetadata" :key="key">
                        <td class="font-weight-medium">{{ key }}</td>
                        <td>{{ formatMetadataValue(value) }}</td>
                      </tr>
                    </tbody>
                  </v-table>
                </v-card>
              </div>
            </template>
            
            <div v-else class="text-center py-6">
              <v-progress-circular indeterminate color="primary" size="50" width="5"></v-progress-circular>
              <div class="mt-3 text-body-1">{{ tm('factDialog.loading') }}</div>
            </div>
          </v-card-text>
          
          <v-divider v-if="selectedEdgeFactData"></v-divider>
          
          <v-card-actions class="pa-4" v-if="selectedEdgeFactData">
            <v-btn block color="primary" variant="tonal" @click="showFactDialog = false">
              {{ tm('factDialog.close') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import * as d3 from "d3"; // npm install d3
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'LongTermMemory',
  setup() {
    const { tm } = useModuleI18n('features/alkaid/memory');
    return { tm };
  },
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

      // 添加边点击相关数据
      selectedEdge: null,
      selectedEdgeFactId: null,
      selectedEdgeFactData: null,
      showFactDialog: false,
      isLoadingFactData: false,

      // 改进元数据展示
      parsedMetadata: null,
    }
  },
  mounted() {
    this.initD3Graph();
    this.ltmGetGraph();
    this.ltmGetUserIds();
  },
  beforeUnmount() {
    // 停止D3仿真
    if (this.simulation) {
      this.simulation.stop();
    }
    
    // 清理DOM元素
    if (this.svg) {
      try {
        this.svg.remove();
      } catch (e) {
        console.warn('Error removing SVG:', e);
      }
    }
    
    // 重置数据
    this.nodes = [];
    this.links = [];
    this.userIdList = [];
    this.searchResults = [];
  },
  methods: {
    // 添加搜索记忆方法
    searchMemory() {
      if (!this.searchQuery.trim()) {
        this.$toast.warning(this.tm('messages.searchQueryRequired'));
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
                text: data[doc_id].text || this.tm('search.noTextContent'),
                score: data[doc_id].score || 0
              };
            });

            if (this.searchResults.length === 0) {
              this.$toast.info(this.tm('messages.searchNoResults'));
            } else {
              this.$toast.success(this.tm('messages.searchSuccess', { count: this.searchResults.length }));
            }
          } else {
            this.$toast.error(this.tm('messages.searchError') + ': ' + response.data.message);
          }
        })
        .catch(error => {
          console.error('搜索记忆数据失败:', error);
          this.$toast.error(this.tm('messages.searchError') + ': ' + (error.response?.data?.message || error.message));
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
          this.$toast.success(this.tm('messages.addSuccess'));
        })
        .catch(error => {
          console.error('添加记忆数据失败:', error);
          this.$toast.error(this.tm('messages.addError') + ': ' + (error.response?.data?.message || error.message));
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
          const data = response.data.data || {};
          // 确保数据是数组类型，并且先检查data是否存在
          let nodesRaw = data && Array.isArray(data.nodes) ? data.nodes : [];
          let edgesRaw = data && Array.isArray(data.edges) ? data.edges : [];

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
          // 出错时重置为空数组
          this.nodes = [];
          this.links = [];
          this.node_data = [];
          this.edge_data = [];
        })
        .finally(() => {
          this.isLoading = false;
        });
    },

    ltmGetUserIds() {
      axios.get('/api/plug/alkaid/ltm/user_ids')
        .then(response => {
          // 确保返回的数据是数组类型
          const data = response.data.data;
          this.userIdList = Array.isArray(data) ? data : [];
        })
        .catch(error => {
          console.error('Error fetching user IDs:', error);
          this.userIdList = []; // 出错时设置为空数组
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

    // 添加获取Fact详情的方法
    getFactDetails(factId) {
      if (!factId) return;
      
      this.isLoadingFactData = true;
      this.selectedEdgeFactData = null;
      this.parsedMetadata = null;
      
      axios.get('/api/plug/alkaid/ltm/graph/fact', { 
        params: { fact_id: factId } 
      })
        .then(response => {
          if (response.data.status === 'ok') {
            this.selectedEdgeFactData = response.data.data;
            // 解析元数据
            this.parsedMetadata = this.parseMetadata(this.selectedEdgeFactData.metadata);
            this.showFactDialog = true;
          } else {
            this.$toast.error(this.tm('messages.factDetailsError') + ': ' + response.data.message);
          }
        })
        .catch(error => {
          console.error('获取记忆详情失败:', error);
          this.$toast.error(this.tm('messages.factDetailsError') + ': ' + (error.response?.data?.message || error.message));
        })
        .finally(() => {
          this.isLoadingFactData = false;
        });
    },

    // 添加元数据解析方法
    parseMetadata(metadata) {
      if (!metadata) return null;
      
      try {
        // 如果是字符串，尝试解析JSON
        if (typeof metadata === 'string') {
          try {
            return JSON.parse(metadata);
          } catch (e) {
            return { value: metadata }; // 如果无法解析为JSON，则作为单个值返回
          }
        }
        
        // 如果已经是对象，直接返回
        if (typeof metadata === 'object') {
          return metadata;
        }
        
        return { value: String(metadata) };
      } catch (e) {
        console.error('解析元数据出错:', e);
        return { error: this.tm('messages.metadataParseError') };
      }
    },
    
    // 格式化元数据值
    formatMetadataValue(value) {
      if (value === null || value === undefined) return this.tm('factDialog.noValue');
      
      if (typeof value === 'object') {
        return JSON.stringify(value);
      }
      
      return String(value);
    },

    // 格式化时间戳的辅助方法
    formatTime(timestamp) {
      if (!timestamp) return this.tm('factDialog.unknown');
      try {
        return new Date(timestamp).toLocaleString();
      } catch (e) {
        return timestamp;
      }
    },

    initD3Graph() {
      const container = document.getElementById("graph-container");
      if (!container) {
        console.warn('Graph container not found');
        return;
      }
      
      // 安全清理现有SVG
      try {
        d3.select("#graph-container svg").remove();
      } catch (e) {
        console.warn('Error removing existing SVG:', e);
      }
      
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 600;
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
      if (!this.svg || !this.simulation || !this.g) {
        console.warn('D3 elements not ready for update');
        return;
      }
      
      const g = this.g;
      try {
        g.selectAll("*").remove();
      } catch (e) {
        console.warn('Error clearing D3 graph:', e);
        return;
      }
      
      // 添加箭头定义
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
      
      // 预处理边数据，标识和处理重复边
      const linkGroups = this.identifyParallelLinks(this.links);
      
      // 使用路径替代直线来绘制边，以便支持曲线
      const link = g.append("g")
        .selectAll("path")
        .data(this.links)
        .join("path")
        .attr("stroke", d => d.color)
        .attr("stroke-width", 1.5)
        .attr("fill", "none")
        .attr("marker-end", "url(#arrowhead)")
        .style("cursor", "pointer");
      
      // 边标签需要相应调整位置
      const edgeLabels = g.append("g")
        .selectAll("text")
        .data(this.links)
        .join("text")
        .text(d => d.label)
        .attr("font-size", "8px")
        .attr("text-anchor", "middle")
        .attr("fill", "#666")
        .style("cursor", "pointer")
        .on("click", (event, d) => {
          event.stopPropagation();
          
          // 检查边数据中是否有fact_id
          const factId = d.originalData?.fact_id;
          if (factId) {
            this.selectedEdge = d;
            this.selectedEdgeFactId = factId;
            this.getFactDetails(factId);
          } else {
            this.$toast.info(this.tm('messages.relationNoMemoryData'));
          }
        });
        
      // 节点绘制部分保持不变
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
      
      // 给SVG添加全局点击事件，用于关闭气泡
      this.svg.on("click", () => {
        this.selectedNode = null;
      });
      
      this.simulation
        .nodes(this.nodes)
        .on("tick", () => {
          // 更新边的路径
          link.attr("d", d => this.generateLinkPath(d));
          
          // 更新边标签位置
          edgeLabels
            .attr("x", d => this.getLinkLabelX(d))
            .attr("y", d => this.getLinkLabelY(d));
            
          // 更新节点位置
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
    
    // 识别并标记平行边（连接相同两个节点的多条边）
    identifyParallelLinks(links) {
      // 创建一个映射来存储连接相同节点对的边
      const linkMap = new Map();
      
      // 遍历所有边，按照起点和终点进行分组
      links.forEach(link => {
        // 创建边的键，确保无论边的方向如何，同一对节点生成的键都相同
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
        const targetId = typeof link.target === 'object' ? link.target.id : link.target;
        
        const forwardKey = `${sourceId}-${targetId}`;
        const reverseKey = `${targetId}-${sourceId}`;
        
        // 判断是从source到target的边还是反向边
        const isForwardLink = sourceId < targetId;
        const key = isForwardLink ? forwardKey : reverseKey;
        
        // 使用方向信息
        if (!linkMap.has(key)) {
          linkMap.set(key, []);
        }
        
        // 存储边和其方向
        linkMap.get(key).push({
          link,
          isForward: isForwardLink
        });
      });
      
      // 处理每一组平行边，为它们分配曲率
      linkMap.forEach((parallels, key) => {
        if (parallels.length > 1) {
          // 有多条平行边，分配不同曲率
          parallels.forEach((item, index) => {
            // 根据边的数量计算适当的曲率
            const totalLinks = parallels.length;
            // 基础曲率，可根据边数调整
            const baseCurvature = 0.45;
            // 根据边的索引计算曲率：中间的边较直，两侧的边较弯
            let curvature;
            
            if (totalLinks % 2 === 1) {
              // 奇数条边，中间的边直线，其他边弯曲
              const middleIndex = Math.floor(totalLinks / 2);
              if (index === middleIndex) {
                curvature = 0; // 中间的边为直线
              } else {
                // 到中间边的距离决定曲率大小
                const distance = Math.abs(index - middleIndex);
                const direction = index < middleIndex ? -1 : 1;
                curvature = direction * baseCurvature * distance;
              }
            } else {
              // 偶数条边，所有边都弯曲
              const middleIndex = totalLinks / 2 - 0.5;
              const distance = Math.abs(index - middleIndex);
              const direction = index < middleIndex ? -1 : 1;
              curvature = direction * baseCurvature * distance;
            }
            
            // 如果是反向边，翻转曲率方向
            if (!item.isForward) {
              curvature = -curvature;
            }
            
            // 存储曲率值到边对象
            item.link.curvature = curvature;
          });
        } else {
          // 只有一条边，不需要弯曲
          parallels[0].link.curvature = 0;
        }
      });
      
      return linkMap;
    },
    
    // 根据曲率生成边的路径
    generateLinkPath(d) {
      // 确保source和target是对象
      const source = typeof d.source === 'object' ? d.source : this.nodes.find(n => n.id === d.source);
      const target = typeof d.target === 'object' ? d.target : this.nodes.find(n => n.id === d.target);
      
      if (!source || !target) return '';
      
      // 如果是直线(无曲率)
      if (!d.curvature || d.curvature === 0) {
        return `M${source.x},${source.y}L${target.x},${target.y}`;
      }
      
      // 计算曲线的控制点
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dr = Math.sqrt(dx * dx + dy * dy);
      
      // 控制点偏移距离，由曲率决定
      const offset = dr * d.curvature;
      
      // 计算中点
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      
      // 计算垂直于连线的方向向量
      const nx = -dy / dr;
      const ny = dx / dr;
      
      // 计算控制点坐标
      const cpx = midX + offset * nx;
      const cpy = midY + offset * ny;
      
      // 创建二次贝塞尔曲线路径
      return `M${source.x},${source.y} Q${cpx},${cpy} ${target.x},${target.y}`;
    },
    
    // 新增方法：计算边标签的X坐标
    getLinkLabelX(d) {
      const source = typeof d.source === 'object' ? d.source : this.nodes.find(n => n.id === d.source);
      const target = typeof d.target === 'object' ? d.target : this.nodes.find(n => n.id === d.target);
      
      if (!source || !target) return 0;
      
      // 如果是直线
      if (!d.curvature || d.curvature === 0) {
        return (source.x + target.x) / 2;
      }
      
      // 计算曲线上的点
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dr = Math.sqrt(dx * dx + dy * dy);
      
      // 中点
      const midX = (source.x + target.x) / 2;
      
      // 垂直向量
      const nx = -dy / dr;
      
      // 曲线路径上的点，使用曲率进行调整
      return midX + d.curvature * dr * nx * 0.5;
    },
    
    // 新增方法：计算边标签的Y坐标
    getLinkLabelY(d) {
      const source = typeof d.source === 'object' ? d.source : this.nodes.find(n => n.id === d.source);
      const target = typeof d.target === 'object' ? d.target : this.nodes.find(n => n.id === d.target);
      
      if (!source || !target) return 0;
      
      // 如果是直线
      if (!d.curvature || d.curvature === 0) {
        return (source.y + target.y) / 2;
      }
      
      // 计算曲线上的点
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dr = Math.sqrt(dx * dx + dy * dy);
      
      // 中点
      const midY = (source.y + target.y) / 2;
      
      // 垂直向量
      const ny = dx / dr;
      
      // 曲线路径上的点，使用曲率进行调整
      return midY + d.curvature * dr * ny * 0.5;
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

/* 为连接线添加交互样式 */
#graph-container line {
  transition: stroke-width 0.2s;
}

#graph-container line:hover {
  stroke-width: 3px;
  cursor: pointer;
}

/* 添加美化详情卡片的样式 */
.fact-detail-card :deep(.v-card-title) {
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.fact-detail-card :deep(.metadata-table) {
  border-radius: 8px;
  overflow: hidden;
}

.fact-detail-card :deep(.v-table) {
  background: transparent;
}

.fact-detail-card :deep(.v-table th) {
  color: var(--v-primary-base);
  font-weight: bold;
  background-color: rgba(var(--v-theme-primary), 0.05);
}

.fact-detail-card :deep(pre) {
  background-color: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
  max-height: 150px;
  overflow: auto;
  font-size: 12px;
}
</style>
