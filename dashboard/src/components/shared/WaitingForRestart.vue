<template>
    <v-dialog v-model="visible" persistent max-width="400">
        <v-card>
            <v-card-title>正在等待 AstrBot 重启...</v-card-title>
            <v-card-text>
                <v-progress-linear indeterminate color="primary"></v-progress-linear>
                <div style="margin-top: 16px;">
                    <div class="py-12 text-center" v-if="newStartTime != -1">
                        <v-icon class="mb-6" color="success" icon="mdi-check-circle-outline" size="128"></v-icon>
                        <p>重启成功！</p>
                    </div>
                    <small v-if="startTime != -1" style="display: block;">当前实例标识：{{ startTime }}</small>
                    <small v-if="newStartTime != -1" style="display: block;">检查到新实例：{{ newStartTime }}，即将自动刷新页面</small>
                    <small v-if="status" style="display: block;">{{ status }}</small>
                    <small style="display: block;">尝试次数：{{ cnt }} / 60</small>
                </div>

            </v-card-text>
        </v-card>
    </v-dialog>
</template>

<script>
import axios from 'axios'

import { useCommonStore } from '@/stores/common';


export default {
    name: 'WaitingForRestart',
    data() {
        return {
            visible: false,
            startTime: -1,
            newStartTime: -1,
            status: '',
            cnt: 0,
        }
    },
    methods: {
        async check() {
            this.newStartTime = -1
            this.startTime = useCommonStore().getStartTime()
            this.visible = true
            this.status = ""
            console.log('start wfr')
            setTimeout(() => {
                this.timeoutInternal()
            }, 1000)
        },
        timeoutInternal() {
            console.log('wfr: timeoutInternal', this.newStartTime, this.startTime)
            if (this.newStartTime === -1 && this.cnt < 60 && this.visible) {
                this.checkStartTime()
                this.cnt++
                setTimeout(() => {
                    this.timeoutInternal()
                }, 1000)
            } else {
                if (this.cnt == 10) {
                    this.status = '拉取状态达到最大次数，请手动检查。'
                }
                this.cnt = 0
                setTimeout(() => {
                    this.visible = false
                }, 1000)
            }
        },
        async checkStartTime() {
            let res = await axios.get('/api/stat/start-time', { timeout: 3000 })
            let newStartTime = res.data.data.start_time
            console.log('wfr: checkStartTime', this.newStartTime, this.startTime)
            if (this.newStartTime !== this.startTime) {
                this.newStartTime = newStartTime
                console.log('wfr: restarted')
                setTimeout(() => {
                    this.visible = false
                    // reload 
                    window.location.reload()
                }, 2000)
            }
            return this.newStartTime
        }
    }
}
</script>