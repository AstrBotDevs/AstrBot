<script setup>
//
</script>

<template>
  <v-card elevation="0">
    <v-card variant="outlined">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="7">
            <span class="text-subtitle-2 text-disabled font-weight-bold">总消息趋势</span>
            <!-- <h3 class="text-h3 mt-1">{{ total_cnt }}</h3> -->
          </v-col>
          <v-col cols="12" sm="5">
            <v-select color="primary" variant="outlined" hide-details v-model="select" :items="items" item-title="state"
              item-value="abbr" label="Select" persistent-hint return-object single-line>
            </v-select>
          </v-col>
        </v-row>
        <div class="mt-4">
          <apexchart type="area" height="280" :options="chartOptions1" :series="lineChart1.series" ref="rtchart">
          </apexchart>
        </div>
      </v-card-text>
    </v-card>
  </v-card>
</template>

<script>

export default {
  name: 'MessageStat',
  components: {
  },
  props: ['stat'],
  data: () => ({
    total_cnt: 0,
    select: { state: 'Today', abbr: 'FL' },
    items: [
      { state: '过去 1 天', abbr: 'FL' },
    ],
    chartOptions1: {
      chart: {
        type: 'area',
        height: 400,
        fontFamily: `inherit`,
        foreColor: '#a1aab2',
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
        fixed: {
          enabled: false
        },
        x: {
          show: true,
          format: 'yyyy-MM-dd HH:mm'
        },
        y: {
          title: {
            formatter: () => '消息条数 '
          }
        },
      },
      xaxis: {
        type: 'datetime',
        title: {
          text: '时间'
        },
        labels: {
          formatter: function (value) {
            return new Date(value).toLocaleString();
          }
        }
      },
      yaxis: {
        title: {
          text: '消息条数'
        }
      },
      grid: {
        show: true
      }
    },
    
    lineChart1: {
      series: [
        {
          name: '消息条数',
          data: []
        }
      ]
    },

  }),

  watch: {
    stat: {
      handler: function (val, oldVal) {
        val = val.message_time_series
        // this.total_cnt = val.message_count
        // [[timestamp, cnt], ...]
        this.lineChart1.series[0].data = val.map((item) => {
          return [new Date(item[0]*1000).getTime(), item[1]];
        });
        
      },
      deep: true
    }
  },
};

</script>