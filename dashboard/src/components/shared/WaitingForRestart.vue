<template>
    <v-dialog v-model="visible" persistent max-width="400">
        <v-card>
            <v-card-title>{{ t('core.common.restart.waiting') }}</v-card-title>
            <v-card-text>
                <v-progress-linear indeterminate color="primary"></v-progress-linear>
            </v-card-text>
        </v-card>
    </v-dialog>
</template>

<script>
import axios from 'axios'
import { useCommonStore } from '@/stores/common';
import { useI18n } from '@/i18n/composables';


export default {
    name: 'WaitingForRestart',
    setup() {
        const { t } = useI18n();
        return { t };
    },
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
                    this.status = this.t('core.common.restart.maxRetriesReached')
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
                this.visible = false
                // reload 
                window.location.reload()
            }
            return this.newStartTime
        }
    }
}
</script>