# Frontend: Handle HTTP 429 (Rate Limit) on Vue 3

Add this to your Vue frontend project (the Vite + Vue 3 app).

---

## 1. Axios Interceptor (`src/services/api.js` or `src/lib/axios.js`)

```js
import axios from 'axios'
import { ref } from 'vue'

// Reactive state that components can watch
export const rateLimitError = ref(null)

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  headers: {
    'X-API-KEY': import.meta.env.VITE_API_KEY,
  },
})

// Response interceptor to catch 429
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 429) {
      const retryAfter = error.response.headers['retry-after'] || 60
      rateLimitError.value = {
        message: 'Terlalu banyak permintaan. Silakan tunggu sebentar.',
        retryAfter: Number(retryAfter),
      }

      // Auto-clear after retryAfter seconds
      setTimeout(() => {
        rateLimitError.value = null
      }, Number(retryAfter) * 1000)
    }

    return Promise.reject(error)
  }
)

export default apiClient
```

---

## 2. Toast/Banner Component (`src/components/RateLimitBanner.vue`)

```vue
<script setup>
import { rateLimitError } from '@/services/api'
</script>

<template>
  <Transition name="fade">
    <div v-if="rateLimitError" class="rate-limit-banner">
      <span>⚠️ {{ rateLimitError.message }}</span>
      <small>Coba lagi dalam {{ rateLimitError.retryAfter }} detik.</small>
    </div>
  </Transition>
</template>

<style scoped>
.rate-limit-banner {
  position: fixed;
  top: 1rem;
  left: 50%;
  transform: translateX(-50%);
  background: #fef3cd;
  border: 1px solid #ffc107;
  color: #856404;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  z-index: 9999;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
```

---

## 3. Usage in `App.vue`

```vue
<script setup>
import RateLimitBanner from '@/components/RateLimitBanner.vue'
</script>

<template>
  <RateLimitBanner />
  <RouterView />
</template>
```

---

## 4. Handling in a specific composable/page (optional per-call handling)

```js
import apiClient from '@/services/api'

export async function fetchCafes(params) {
  try {
    const { data } = await apiClient.get('/api/cafes', { params })
    return data
  } catch (err) {
    if (err.response?.status === 429) {
      // Already handled globally by interceptor + banner
      // But you can also disable the button here:
      return { rateLimited: true }
    }
    throw err
  }
}
```

---

## Summary

| Layer | What it does |
|-------|-------------|
| Axios interceptor | Catches ALL 429s globally, sets reactive state |
| `RateLimitBanner.vue` | Shows a user-friendly warning banner |
| Per-call handling | Optionally disable buttons / show inline messages |
