<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore, ROLE_META } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(() => {
  router.replace(auth.role ? (ROLE_META[auth.role]?.home || '/dashboard') : '/login')
})
</script>

<template><div /></template>
