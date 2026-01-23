<template>
  <div>
    <div class="file-upload-zone" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop" :class="{ dragging }" @click="open">
      <div class="file-upload-icon" aria-hidden="true">📦</div>
      <div><strong>Drop ZIP files here, or click to upload</strong></div>
      <div class="form-hint">Supports bulk ZIP. Max 200MB. We'll scan and show a preview.</div>
    </div>
    <input ref="input" type="file" multiple @change="onFiles" style="display:none" accept=".zip,application/zip" />
    <div v-if="files.length" style="margin-top: var(--space-md)">
      <div v-for="(f, i) in files" :key="i" class="info-item">
        <div style="display:flex; justify-content:space-between;">
          <div>
            <div style="font-weight:800">{{ f.name }}</div>
            <div class="form-hint">{{ prettySize(f.size) }} • {{ f.type || 'zip' }}</div>
          </div>
          <div style="display:flex; gap:8px; align-items:center">
            <button class="btn btn-sm btn-primary" @click="uploadFile(f)">Scan</button>
            <button class="btn btn-sm" @click="remove(i)">Remove</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'

const input = ref(null)
const files = ref([])
const dragging = ref(false)

function open() {
  input.value?.click()
}

function onFiles(e) {
  const list = Array.from(e.target.files || [])
  files.value.push(...list)
}

function onDrop(e) {
  dragging.value = false
  const list = Array.from(e.dataTransfer.files || [])
  files.value.push(...list)
}

function remove(i) {
  files.value.splice(i, 1)
}

function prettySize(n) {
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

async function uploadFile(file) {
  // simple scan endpoint; change path to your backend
  const data = new FormData()
  data.append('file', file)
  try {
    const resp = await api.post('/files/scan', data, { headers: { 'Content-Type': 'multipart/form-data' } })
    // emit result (scan summary)
    // bubble event
    const event = new CustomEvent('uploaded', { detail: resp.data.files || [file] })
    window.dispatchEvent(event)
  } catch (e) {
    alert('Failed to upload: ' + (e.response?.data?.message || e.message))
  }
}
</script>
