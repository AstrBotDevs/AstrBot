<script setup lang="ts">
import { ref } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import axios from 'axios';
import { md5 } from 'js-md5';
import { useAuthStore } from '@/stores/auth';
import { useCommonStore } from '@/stores/common';

const customizer = useCustomizerStore();
let dialog = ref(false);
let updateStatusDialog = ref(false);
let password = ref('');
let newPassword = ref('');
let newUsername = ref('');
let status = ref('');
let updateStatus = ref('')
let hasNewVersion = ref(false);
let botCurrVersion = ref('');
let dashboardHasNewVersion = ref(false);
let dashboardCurrentVersion = ref('');
let version = ref('');

const open = (link: string) => {
  window.open(link, '_blank');
};

// 账户修改
function accountEdit() {
  // md5加密
  // @ts-ignore
  if (password.value != '') {
    password.value = md5(password.value);
  }
  if (newPassword.value != '') {
    newPassword.value = md5(newPassword.value);
  }
  axios.post('/api/auth/account/edit', {
    password: password.value,
    new_password: newPassword.value,
    new_username: newUsername.value
  })
    .then((res) => {
      if (res.data.status == 'error') {
        status.value = res.data.message;
        password.value = '';
        newPassword.value = '';
        return;
      }
      dialog.value = !dialog.value;
      status.value = res.data.message;
      setTimeout(() => {
        const authStore = useAuthStore();
        authStore.logout();
      }, 1000);
    })
    .catch((err) => {
      console.log(err);
      status.value = err
      password.value = '';
      newPassword.value = '';
    });
}

function checkUpdate() {
  updateStatus.value = '正在检查更新...';
  axios.get('/api/update/check')
    .then((res) => {
      hasNewVersion.value = res.data.data.has_new_version;
      updateStatus.value = res.data.message;
      botCurrVersion.value = res.data.data.version;
      dashboardCurrentVersion.value = res.data.data.dashboard_version;
      dashboardHasNewVersion.value = res.data.data.dashboard_has_new_version;
    })
    .catch((err) => {
      if (err.response.status == 401) {
        console.log("401");
        const authStore = useAuthStore();
        authStore.logout();
        return;
      }
      console.log(err);
      updateStatus.value = err
    });
}

function switchVersion(version: string) {
  updateStatus.value = '正在切换版本...';
  axios.post('/api/update/do', {
    version: version
  })
    .then((res) => {
      updateStatus.value = res.data.message;
      if (res.data.status == 'ok') {
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      }
    })
    .catch((err) => {
      console.log(err);
      updateStatus.value = err
    });
}

function updateDashboard() {
  updateStatus.value = '正在更新...';
  axios.post('/api/update/dashboard')
    .then((res) => {
      updateStatus.value = res.data.message;
      if (res.data.status == 'ok') {
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      }
    })
    .catch((err) => {
      console.log(err);
      updateStatus.value = err
    });
}

checkUpdate();

const commonStore = useCommonStore();
commonStore.createWebSocket();
commonStore.getStartTime();
</script>

<template>
  <v-app-bar elevation="0" height="70">

    <v-btn style="margin-left: 22px;" class="hidden-md-and-down text-secondary" color="lightsecondary" icon rounded="sm"
      variant="flat" @click.stop="customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar)" size="small">
      <v-icon>mdi-menu</v-icon>
    </v-btn>
    <v-btn class="hidden-lg-and-up text-secondary ms-3" color="lightsecondary" icon rounded="sm" variant="flat"
      @click.stop="customizer.SET_SIDEBAR_DRAWER" size="small">
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <span style="margin-left: 16px; font-size: 24px; font-weight: 1000;">Astr<span
        style="font-weight: normal;">Bot</span></span>

    <v-spacer />

    <div class="mr-4">
      <small v-if="hasNewVersion">
        有新版本！
      </small>
    </div>


    <v-dialog v-model="updateStatusDialog" width="700">
      <template v-slot:activator="{ props }">
        <v-btn @click="checkUpdate" class="text-primary mr-4" color="lightprimary" variant="flat" rounded="sm"
          v-bind="props">
          更新 🔄
        </v-btn>
      </template>
      <v-card>
        <v-card-title>
          <span class="text-h5">更新 AstrBot</span>
        </v-card-title>
        <v-card-text>
          <v-container>
            <h3 class="mb-4">升级到项目最新版本</h3>
            <small>当前版本 {{ botCurrVersion }}</small>
            <div class="mb-4">
              <small>会同时尝试更新机器人主程序和管理面板。如果您正在使用 Docker 部署，也可以重新拉取镜像或者使用 <a
                  href="https://containrrr.dev/watchtower/usage-overview/">watchtower</a> 来自动监控拉取。</small>
            </div>
            <p>{{ updateStatus }}</p>
            <v-btn class="mt-4 mb-4" @click="switchVersion('latest')" color="primary" style="border-radius: 10px;"
              :disabled="!hasNewVersion">
              更新到最新版本
            </v-btn>
            <v-divider></v-divider>
            <div style="margin-top: 16px;">
              <h3 class="mb-4">切换到项目指定版本或指定提交</h3>
              <div class="mb-4">
                <small>跳到旧版本不会重新下载管理面板文件，这可能会造成部分数据显示错误。您可在 <a href="https://github.com/Soulter/AstrBot/releases">此处</a>
                  找到对应的面板文件 dist.zip，解压后替换 data/dist 文件夹即可。</small>
              </div>
              <v-text-field label="输入版本号或 master 分支下的 commit hash。" v-model="version" required
                variant="outlined"></v-text-field>
              <div class="mb-4">
                <small>如 v3.3.16 (不带 SHA) 或 42e5ec5d80b93b6bfe8b566754d45ffac4c3fe0b</small>
                <br>
                <a href="https://github.com/Soulter/AstrBot/commits/master"><small>查看 master 分支提交记录（点击右边的 copy
                    即可复制）</small></a>
              </div>
              <v-btn color="error" style="border-radius: 10px;" @click="switchVersion(version)">
                确定切换
              </v-btn>
            </div>

            <v-divider></v-divider>
            <div style="margin-top: 16px;">
              <h3 class="mb-4">更新管理面板到最新版本</h3>
              <div class="mb-4">
                <small>当前版本 {{ dashboardCurrentVersion }}</small>
                <br>

              </div>

              <div class="mb-4">
                <p v-if="dashboardHasNewVersion">
                  有新版本！
                </p>
                <p v-else="dashboardHasNewVersion">
                  已经是最新版本了。
                </p>
              </div>

              <v-btn color="primary" style="border-radius: 10px;" @click="updateDashboard()">
                下载并更新
              </v-btn>
            </div>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue-darken-1" variant="text" @click="updateStatusDialog = false">
            关闭
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="dialog" persistent width="700">
      <template v-slot:activator="{ props }">
        <v-btn class="text-primary mr-4" color="lightprimary" variant="flat" rounded="sm" v-bind="props">
          账户 📰
        </v-btn>
      </template>
      <v-card>
        <v-card-title>
          <span class="text-h5">账户</span>
        </v-card-title>
        <v-card-text>
          <v-container>
            <v-row>
              <v-col cols="12">
                <v-text-field label="原密码*" type="password" v-model="password" required
                  variant="outlined"></v-text-field>

                <v-text-field label="新用户名" v-model="newUsername" required variant="outlined"></v-text-field>

                <v-text-field label="新密码" type="password" v-model="newPassword" required
                  variant="outlined"></v-text-field>
              </v-col>
            </v-row>
          </v-container>
          <small>默认用户名和密码是 astrbot。</small>
          <br>
          <small>{{ status }}</small>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue-darken-1" variant="text" @click="dialog = false">
            关闭
          </v-btn>
          <v-btn color="blue-darken-1" variant="text" @click="accountEdit">
            提交
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app-bar>
</template>
