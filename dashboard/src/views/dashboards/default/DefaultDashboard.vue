<template>
  <v-row style="margin: 2px;">
    <v-alert
      :type="noticeType"
      :text="noticeContent"
      :title="noticeTitle"
      v-if="noticeTitle && noticeContent"
      closable
    ></v-alert>
  </v-row>
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
    noticeTitle: '',
    noticeContent: '',
    noticeType: '',
  }),

  mounted() {
    axios.get('/api/stat/get').then((res) => {
      this.stat = res.data.data;
    });

    axios.get('https://api.soulter.top/astrbot-announcement').then((res) => {
      let data = res.data.data;
      // 如果 dashboard-notice 在其中
      if (data['dashboard-notice']) {
        this.noticeTitle = data['dashboard-notice'].title;
        this.noticeContent = data['dashboard-notice'].content;
        this.noticeType = data['dashboard-notice'].type;
      }
    });
  },
};

</script>
