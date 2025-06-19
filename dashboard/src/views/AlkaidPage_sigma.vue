<script setup>
import Graph from "graphology";
import Sigma from "sigma";
import ForceSupervisor from "graphology-layout-force/worker";
</script>


<template>
  <v-card style="height: 100%; width: 100%;">
    <v-card-text class="pa-4" style="height: 100%;">
      <v-container fluid class="d-flex flex-column" style="height: 100%;">
        <div style="margin-bottom: 32px;">
          <h1 class="gradient-text">The Alkaid Project.</h1>
                      <small style="color: #a3a3a3;">{{ tm('features.alkaid.index.sigma.subtitle') }}</small>
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
              <span style="color: #333333;">{{ tm('features.alkaid.index.sigma.visualization') }}</span>
              <div style="margin-top: 8px;">
                                  <v-autocomplete v-model="searchUserId" :items="userIdList" variant="outlined"
                    :label="tm('features.alkaid.index.sigma.filterUserId')"></v-autocomplete>
                                  <v-btn color="primary" @click="onNodeSelect" variant="tonal" style="margin-top: 8px;">
                    <v-icon start>mdi-magnify</v-icon>
                    {{ tm('features.alkaid.index.sigma.filter') }}
                  </v-btn>
                                  <v-btn color="secondary" @click="resetFilter" variant="tonal"
                    style="margin-top: 8px; margin-left: 8px;">
                    <v-icon start>mdi-filter-remove</v-icon>
                    {{ tm('features.alkaid.index.sigma.resetFilter') }}
                  </v-btn>
              </div>
              <div style="margin-top: 16px;">
                <v-btn color="primary" @click="refreshGraph" variant="tonal">
                  <v-icon start>mdi-refresh</v-icon>
                  {{ tm('features.alkaid.index.sigma.refreshGraph') }}
                </v-btn>
              </div>
            </div>

            <v-divider class="my-4"></v-divider>

            <div v-if="selectedNode" class="mt-4">
              <h3>{{ tm('features.alkaid.index.sigma.nodeDetails') }}</h3>
              <v-card variant="outlined" class="mt-2 pa-3">
                                  <div v-if="selectedNode.id">
                    <div class="d-flex justify-space-between">
                      <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.id') }}:</span>
                      <span>{{ selectedNode.id }}</span>
                    </div>
                  </div>
                  <div v-if="selectedNode._label">
                    <div class="d-flex justify-space-between">
                      <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.type') }}:</span>
                      <span>{{ selectedNode._label }}</span>
                    </div>
                  </div>
                  <div v-if="selectedNode.name">
                    <div class="d-flex justify-space-between">
                      <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.name') }}:</span>
                      <span>{{ selectedNode.name }}</span>
                    </div>
                  </div>
                  <div v-if="selectedNode.user_id">
                    <div class="d-flex justify-space-between">
                      <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.userId') }}:</span>
                      <span>{{ selectedNode.user_id }}</span>
                    </div>
                  </div>
                  <div v-if="selectedNode.ts">
                    <div class="d-flex justify-space-between">
                      <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.timestamp') }}:</span>
                      <span>{{ selectedNode.ts }}</span>
                    </div>
                  </div>
                  <div v-if="selectedNode.type">
                    <div class="d-flex justify-space-between">
                      <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.type') }}:</span>
                      <span>{{ selectedNode.type }}</span>
                    </div>
                  </div>
              </v-card>
            </div>

            <div v-if="graphStats" class="mt-4">
              <h3>{{ tm('features.alkaid.index.sigma.graphStats') }}</h3>
              <v-card variant="outlined" class="mt-2 pa-3">
                <div class="d-flex justify-space-between">
                  <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.nodeCount') }}:</span>
                  <span>{{ graphStats.nodeCount }}</span>
                </div>
                <div class="d-flex justify-space-between">
                  <span class="text-subtitle-2">{{ tm('features.alkaid.index.sigma.edgeCount') }}:</span>
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
            <p class="text-h6 text-grey ml-4">{{ tm('features.alkaid.index.sigma.inDevelopment') }}</p>
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
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'AlkaidPage',
  components: {
    AstrBotConfig,
    WaitingForRestart
  },
  setup() {
    const { tm } = useModuleI18n('features/alkaid/index');
    return { tm };
  },
  data() {
    return {
      renderer: null,
      graph: null,
      layout: null,
      activeTab: 'long-term-memory',
      node_data: [],
      edge_data: [],
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
    this.initSigma();
    this.ltmGetGraph();
    this.ltmGetUserIds();
  },
  beforeUnmount() {
    if (this.renderer) {
      this.renderer.kill();
    }
    if (this.layout) {
      this.layout.stop();
    }
  },
  watch: {
    activeTab(newVal) {
      if (newVal === 'long-term-memory') {
        this.$nextTick(() => {
          if (!this.renderer) {
            this.initSigma();
          }
        });
      } else {
        if (this.renderer) {
          this.renderer.kill();
          this.renderer = null;
        }
        if (this.layout) {
          this.layout.stop();
          this.layout = null;
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
          let nodes = response.data.data.nodes;
          let edges = response.data.data.edges;

          this.node_data = nodes;
          this.edge_data = edges;

          if (this.graph) {
            this.graph.clear();
          }



          nodes.forEach(node => {
            const nodeId = node[0];
            const nodeData = node[1];

            if (!this.graph.hasNode(nodeId)) {
              const nodeType = nodeData._label || 'default';
              const color = this.nodeColors[nodeType] || this.nodeColors['default'];

              this.graph.addNode(nodeId, {
                x: Math.random(),
                y: Math.random(),
                size: 5,
                label: nodeData.name || nodeId.split('_')[0],
                color: color,
                originalData: nodeData
              });
            }
          });

          // 添加边
          edges.forEach(edge => {
            const sourceId = edge[0];
            const targetId = edge[1];
            const edgeData = edge[2];

            if (this.graph.hasNode(sourceId) && this.graph.hasNode(targetId)) {
              const edgeId = `${sourceId}->${targetId}`;
              const relationType = edgeData.relation_type || 'default';
              const color = this.edgeColors[relationType] || this.edgeColors['default'];
              this.graph.addEdge(sourceId, targetId, {
                size: 1,
                color: color,
                originalData: edgeData,
                label: relationType,
                type: "line"
              });
            } else {
              console.warn(`Edge ${sourceId} -> ${targetId} has missing nodes.`);
            }
          });

          this.updateGraphStats();

          console.log('Graph initialized with', nodes.length, 'nodes and', edges.length, 'edges');
        })
        .catch(error => {
          console.error('Error fetching graph data:', error);
        })
        .finally(() => {
          this.isLoading = false;
        });

      if (this.layout) {
        this.layout.start();
      }

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
      if (this.graph) {
        this.graphStats = {
          nodeCount: this.graph.order,
          edgeCount: this.graph.size
        };
      }
    },

    refreshGraph() {
      this.ltmGetGraph(this.searchUserId);
    },

    onNodeSelect() {
      console.log('Selected user ID:', this.searchUserId);
      if (!this.searchUserId || !this.graph) return;

      // 使用API的user_id参数筛选数据
      this.ltmGetGraph(this.searchUserId);
    },

    resetFilter() {
      this.searchUserId = null;
      this.ltmGetGraph();
    },

    initSigma() {
      const container = document.getElementById("graph-container");
      if (!container) return;

      if (this.renderer) {
        this.renderer.kill();
        this.renderer = null;
      }
      if (this.layout) {
        this.layout.stop();
        this.layout = null;
      }

      const graph = new Graph({
        multi: true,
      });

      const layout = new ForceSupervisor(graph, {
        isNodeFixed: (_, attr) => attr.highlighted, settings: {
          gravity: 0.0001,
          repulsion: 0.001
        }
      });
      layout.start();

      this.layout = layout;
      this.graph = graph;
      const renderer = new Sigma(graph, container, {
        minCameraRatio: 0.01,
        maxCameraRatio: 2,
        labelRenderedSizeThreshold: 1,
        renderLabels: true,
        renderEdgeLabels: true,
        labelSize: 14,
        labelColor: "#333333",
      });
      this.renderer = renderer;

      let draggedNode = null;
      let isDragging = false;

      renderer.on("downNode", (e) => {
        isDragging = true;
        draggedNode = e.node;
        graph.setNodeAttribute(draggedNode, "highlighted", true);
        if (!renderer.getCustomBBox()) renderer.setCustomBBox(renderer.getBBox());
      });

      renderer.on("moveBody", ({ event }) => {
        if (!isDragging || !draggedNode) return;
        const pos = renderer.viewportToGraph(event);

        graph.setNodeAttribute(draggedNode, "x", pos.x);
        graph.setNodeAttribute(draggedNode, "y", pos.y);
        event.preventSigmaDefault();
        event.original.preventDefault();
        event.original.stopPropagation();
      });
      const handleUp = () => {
        if (draggedNode) {
          graph.removeNodeAttribute(draggedNode, "highlighted");
        }
        isDragging = false;
        draggedNode = null;
      };
      renderer.on("upNode", handleUp);
      renderer.on("upStage", handleUp);

      renderer.on("clickNode", (e) => {
        const nodeId = e.node;
        const nodeAttributes = graph.getNodeAttributes(nodeId);
        this.selectedNode = nodeAttributes.originalData;
      });

      renderer.on("clickStage", () => {
        this.selectedNode = null;
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
</style>