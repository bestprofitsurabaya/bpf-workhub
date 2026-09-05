<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { loadIdentity } from './stores/identity'
import StepUpModal from './components/StepUpModal.vue'

const router = useRouter()
const auth = useAuthStore()

onMounted(() => {
  loadIdentity()
  window.addEventListener('bpf:unauthorized', () => {
    auth.user = null
    localStorage.removeItem('bpf_csrf')
    router.push({ name: 'login' })
  })
})
</script>

<template>
  <router-view />
  <StepUpModal />
</template>
