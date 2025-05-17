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
                <v-autocomplete v-model="searchText" variant="outlined" label="筛选用户 ID"
                  @change="onNodeSelect"></v-autocomplete>
              </div>
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
      renderer: null,
      graph: null,
      layout: null,
      activeTab: 'long-term-memory'
    }
  },
  mounted() {
    this.initSigma();
    this.ltmGetGraph();
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
    ltmGetGraph() {
      axios.get('/api/plug/alkaid/ltm/graph')
        .then(response => {
          console.log('Graph data:', response.data);
        })
        .catch(error => {
          console.error('Error fetching graph data:', error);
        });
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

      const graph = new Graph();

      graph.addNode("user", {
        x: 0, y: 0,
        size: 15,
        color: "#4B96FF",
        label: "用户"
      });
      graph.addNode("preference", {
        x: -5, y: 5,
        size: 10,
        color: "#FF9F48",
        label: "偏好"
      });
      graph.addNode("history", {
        x: 5, y: 5,
        size: 10,
        color: "#FF9F48",
        label: "历史对话"
      });
      graph.addNode("knowledge", {
        x: 0, y: 10,
        size: 12,
        color: "#48CFFF",
        label: "知识库"
      });

      graph.addEdge("user", "preference", { size: 2, label: "拥有" });
      graph.addEdge("user", "history", { size: 2, label: "参与" });
      graph.addEdge("history", "knowledge", { size: 1, label: "关联" });
      graph.addEdge("preference", "knowledge", { size: 1, label: "影响" });

      const layout = new ForceSupervisor(graph, { isNodeFixed: (_, attr) => attr.highlighted });
      layout.start();
      this.layout = layout;
      this.graph = graph;
      const renderer = new Sigma(graph, container, {
        minCameraRatio: 0.5,
        maxCameraRatio: 2,
        labelRenderedSizeThreshold: 1, // 使标签更容易显示
        renderLabels: true, // 显示标签
        labelSize: 14, // 标签大小
        labelColor: "#333333", // 标签颜色
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