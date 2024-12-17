<script setup>
import { ref, computed } from 'vue';

// chart 1
const chartOptions1 = computed(() => {
  return {
    chart: {
      type: 'area',
      height: 95,
      fontFamily: `inherit`,
      foreColor: '#a1aab2',
      sparkline: {
        enabled: true
      }
    },
    colors: ['#5e35b1'],
    dataLabels: {
      enabled: false
    },
    stroke: {
      curve: 'smooth',
      width: 1
    },
    tooltip: {
      theme: 'dark',
      fixed: {
        enabled: false
      },
      x: {
        show: false
      },
      y: {
        title: {
          formatter: () => '消息条数 '
        }
      },
      marker: {
        show: false
      }
    }
  };
});

// chart 1
const lineChart1 = {
  series: [
    {
      data: [0, 15, 10, 50, 30, 40, 25]
    }
  ]
};

</script>

<template>
  <v-card elevation="0">
    <v-card variant="outlined">
      <v-card-text>
        <div class="d-flex align-center">
          <h4 class="text-h4 mt-1">各平台消息数</h4>
        </div>
        <div class="mt-4">
          <v-list lines="two" class="py-0" style="height: 270px;">
            
            <v-list-item v-for="(platform, i) in platforms" :key="i" :value="platform" color="secondary" rounded="sm">
              <div class="d-inline-flex align-center justify-space-between w-100">
                <div>
                  <h6 class="text-subtitle-1 text-medium-emphasis font-weight-bold">
                    {{ platform.name }}
                  </h6>
                </div>

                <div class="ml-auto text-subtitle-1 text-medium-emphasis font-weight-bold">{{ platform.count }} 条</div>
              </div>
            </v-list-item>
          </v-list>

          <div class="text-center mt-3">
            <v-btn color="primary" variant="text"
              >详情
              <template v-slot:append>
                <ChevronRightIcon stroke-width="1.5" width="20" />
              </template>
            </v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </v-card>
</template>


<script>

export default {
  name: 'PlatformStat',
  components: {
  },
  props: ['stat'],
  watch: {
    stat: {
      handler: function (val, oldVal) {
        this.platforms = val.platform
      },
      deep: true,
    }
  },
  data: () => ({
    platforms: [
    ]
  }),

  mounted() {
  }
};
</script>