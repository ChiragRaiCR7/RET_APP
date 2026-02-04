/**
 * Conversion Store
 * 
 * Centralized state management for the conversion workflow.
 * Handles session management, file uploads, scanning, and conversion.
 */

import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import api from '@/utils/api'

export const useConversionStore = defineStore('conversion', () => {
  // Workflow state
  const sessionId = ref(null)
  const outputFormat = ref('csv')
  const editMode = ref(false)
  const fastParser = ref(true)
  const customPrefixes = ref('')
  
  // File management
  const uploadedFiles = ref([])
  const scannedGroups = ref([])
  const scanSummary = ref(null)
  const converted = ref(false)
  
  // Conversion data
  const groups = ref([])
  const files = ref([])
  const totalFiles = ref(0)
  
  // UI state
  const scanning = ref(false)
  const converting = ref(false)
  const loading = ref(false)
  const error = ref(null)
  
  // Active selections
  const activeGroup = ref('')
  const activeFile = ref('')
  const selectedGroups = ref([])
  const groupSearch = ref('')
  
  // Preview data
  const preview = ref(null)
  const groupFiles = ref([])

  // Computed
  const isScanned = computed(() => scannedGroups.value.length > 0)
  const isConverted = computed(() => converted.value && files.value.length > 0)
  const hasSession = computed(() => sessionId.value !== null)
  
  const filteredGroups = computed(() => {
    if (!groupSearch.value) return groups.value
    const search = groupSearch.value.toLowerCase()
    return groups.value.filter(g => g.name.toLowerCase().includes(search))
  })

  // Actions
  function addFiles(filesList) {
    uploadedFiles.value.push(...filesList)
  }

  async function scanZip() {
    if (!uploadedFiles.value.length) {
      throw new Error('No files to scan')
    }
    
    scanning.value = true
    error.value = null
    
    try {
      const formData = new FormData()
      formData.append('file', uploadedFiles.value[0])
      
      const res = await api.post('/conversion/scan', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      
      sessionId.value = res.data.session_id
      scannedGroups.value = (res.data.groups || []).map(g => ({
        name: g.name,
        file_count: g.file_count || 0,
        size: g.size || 0
      }))
      scanSummary.value = res.data.summary || { 
        totalGroups: scannedGroups.value.length, 
        totalFiles: res.data.xml_count || 0
      }
      
      return { success: true, groups: scannedGroups.value }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      scanning.value = false
    }
  }

  async function convert() {
    if (!sessionId.value) {
      throw new Error('No session to convert')
    }
    
    converting.value = true
    error.value = null
    
    try {
      const formData = new FormData()
      formData.append('session_id', sessionId.value)
      formData.append('output_format', outputFormat.value)
      scannedGroups.value.forEach(g => formData.append('groups', g.name))
      
      const res = await api.post('/conversion/convert', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      
      if (res.data.success) {
        converted.value = true
        await loadConvertedFiles()
        return { success: true, stats: res.data.stats }
      }
      
      throw new Error('Conversion failed')
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      converting.value = false
    }
  }

  async function loadConvertedFiles() {
    if (!sessionId.value) return
    
    loading.value = true
    try {
      const res = await api.get(`/conversion/files/${sessionId.value}`)
      groups.value = res.data.groups || []
      files.value = res.data.files || []
      totalFiles.value = res.data.total_files || 0
      
      if (groups.value.length > 0) {
        activeGroup.value = groups.value[0].name
        await loadGroupFiles()
      }
    } catch (e) {
      console.error('Failed to load converted files:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadGroupFiles() {
    if (!activeGroup.value) return
    
    groupFiles.value = files.value.filter(f => f.group === activeGroup.value)
    if (groupFiles.value.length > 0) {
      activeFile.value = groupFiles.value[0].filename
      await loadFilePreview()
    }
  }

  async function loadFilePreview() {
    if (!activeFile.value || !sessionId.value) return
    
    try {
      const res = await api.get(`/conversion/preview/${sessionId.value}/${activeFile.value}`, {
        params: { max_rows: 100 }
      })
      preview.value = res.data
    } catch (e) {
      console.error('Failed to load preview:', e)
      preview.value = null
    }
  }

  async function downloadAll() {
    if (!sessionId.value) return
    
    const res = await api.get(`/conversion/download/${sessionId.value}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, 'converted_output.zip')
  }

  async function downloadModified() {
    if (!sessionId.value || !editMode.value) return
    
    const res = await api.get(`/conversion/download-modified/${sessionId.value}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, 'modified_output.zip')
  }

  async function downloadFile(filename) {
    if (!sessionId.value) return
    
    const res = await api.get(`/conversion/download-file/${sessionId.value}/${filename}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, filename)
  }

  async function downloadGroup(groupName) {
    if (!sessionId.value) return
    
    const res = await api.get(`/conversion/download-group/${sessionId.value}/${groupName}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, `${groupName}_group.zip`)
  }

  function downloadBlob(data, filename) {
    const url = window.URL.createObjectURL(new Blob([data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  async function cleanup() {
    if (!sessionId.value) return
    
    await api.post(`/conversion/cleanup/${sessionId.value}`)
    reset()
  }

  function selectAllGroups() {
    selectedGroups.value = groups.value.map(g => g.name)
  }

  function clearGroupSelection() {
    selectedGroups.value = []
  }

  function toggleGroup(name) {
    const idx = selectedGroups.value.indexOf(name)
    if (idx >= 0) {
      selectedGroups.value.splice(idx, 1)
    } else {
      selectedGroups.value.push(name)
    }
  }

  function reset() {
    sessionId.value = null
    uploadedFiles.value = []
    scannedGroups.value = []
    scanSummary.value = null
    converted.value = false
    groups.value = []
    files.value = []
    totalFiles.value = 0
    activeGroup.value = ''
    activeFile.value = ''
    preview.value = null
    groupFiles.value = []
    selectedGroups.value = []
    error.value = null
  }

  return {
    // State
    sessionId,
    outputFormat,
    editMode,
    fastParser,
    customPrefixes,
    uploadedFiles,
    scannedGroups,
    scanSummary,
    converted,
    groups,
    files,
    totalFiles,
    scanning,
    converting,
    loading,
    error,
    activeGroup,
    activeFile,
    selectedGroups,
    groupSearch,
    preview,
    groupFiles,
    
    // Computed
    isScanned,
    isConverted,
    hasSession,
    filteredGroups,
    
    // Actions
    addFiles,
    scanZip,
    convert,
    loadConvertedFiles,
    loadGroupFiles,
    loadFilePreview,
    downloadAll,
    downloadModified,
    downloadFile,
    downloadGroup,
    cleanup,
    selectAllGroups,
    clearGroupSelection,
    toggleGroup,
    reset,
  }
})
