<template>
  <v-row>
    <v-col cols="12" md="4">
      <TotalMessage :stat="stat" />
    </v-col>
    <v-col cols="12" md="4">
      <OnlinePlatform :stat="stat" />
    </v-col>
    <v-col cols="12" md="4">
      <OnlineTime :stat="stat" />
    </v-col>
    <v-col cols="12" lg="8">
      <MessageStat :stat="stat" />
    </v-col>
    <v-col cols="12" lg="4">
      <PlatformStat :stat="stat" />
    </v-col>
  </v-row>
</template>


<script>
import TotalMessage from './components/TotalMessage.vue';
import OnlinePlatform from './components/OnlinePlatform.vue';
import OnlineTime from './components/OnlineTime.vue';
import MessageStat from './components/MessageStat.vue';
import PlatformStat from './components/PlatformStat.vue';
import axios from 'axios';

export default {
  name: 'DefaultDashboard',
  components: {
    TotalMessage,
    OnlinePlatform,
    OnlineTime,
    MessageStat,
    PlatformStat,
  },
  data: () => ({
    stat: {},
  }),

  mounted() {
    axios.get('/api/stat/get').then((res) => {
      this.stat = res.data.data;
    });
  }
};

</script>
