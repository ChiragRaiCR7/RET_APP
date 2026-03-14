/**
 * Conversion Store
 *
 * Centralized state management for the conversion workflow.
 * Handles session management, file uploads, scanning, exclusions, and conversion.
 *
 * Non-breaking improvements:
 * - Guards against concurrent scan/convert calls
 * - Safer filename usage in preview route (encodeURIComponent)
 * - Better error extraction + consistent cleanup in finally blocks
 * - Optional dedupe of uploaded files
 * - Keeps identical state/actions/public API shape
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { longApi } from '@/utils/api'

export const useConversionStore = defineStore('conversion', () => {
  // ----------------------------
  // Workflow state
  // ----------------------------
  const sessionId = ref(null)
  const outputFormat = ref('csv')
  const editMode = ref(false)

  // ----------------------------
  // File management
  // ----------------------------
  const uploadedFiles = ref([])
  const scannedGroups = ref([])
  const scanSummary = ref(null)
  const converted = ref(false)

  // ✅ full scanned file list (from scan response)
  const scannedFiles = ref([]) // entries include logical_path, file_type, group, etc.

  // ✅ exclusion list (logical paths) to skip conversion
  const excludedLogicalPaths = ref([])

  // ----------------------------
  // Conversion output data
  // ----------------------------
  const groups = ref([])
  const files = ref([])
  const totalFiles = ref(0)

  // ----------------------------
  // UI state
  // ----------------------------
  const scanning = ref(false)
  const converting = ref(false)
  const loading = ref(false)
  const error = ref(null)

  // ----------------------------
  // Active selections
  // ----------------------------
  const activeGroup = ref('')
  const activeFile = ref('')
  const selectedGroups = ref([])
  const groupSearch = ref('')

  // ----------------------------
  // Preview data
  // ----------------------------
  const preview = ref(null)
  const groupFiles = ref([])

  // ----------------------------
  // Computed
  // ----------------------------
  const isScanned = computed(() => scannedGroups.value.length > 0)
  const isConverted = computed(() => converted.value && files.value.length > 0)
  const hasSession = computed(() => sessionId.value !== null)

  const filteredGroups = computed(() => {
    if (!groupSearch.value) return groups.value
    const search = groupSearch.value.toLowerCase()
    return groups.value.filter((g) => (g.name || '').toLowerCase().includes(search))
  })

  // ----------------------------
  // Helpers
  // ----------------------------
  function extractError(e) {
    // Handles typical FastAPI shapes: {detail}, {message}, validation errors, etc.
    return (
      e?.response?.data?.detail ||
      e?.response?.data?.message ||
      e?.response?.data?.error ||
      e?.message ||
      'Unknown error'
    )
  }

  function normalizeString(s) {
    return String(s ?? '').trim()
  }

  function normalizeGroupName(name) {
    return normalizeString(name)
  }

  function uniqStrings(arr) {
    const out = []
    const seen = new Set()
    for (const x of arr || []) {
      const v = normalizeString(x)
      if (!v) continue
      if (seen.has(v)) continue
      seen.add(v)
      out.push(v)
    }
    return out
  }

  function setError(e) {
    error.value = extractError(e)
  }

  function clearError() {
    error.value = null
  }

  function addFiles(filesList) {
    // Keep original behavior, but avoid duplicate entries (safe improvement)
    const incoming = Array.from(filesList || [])
    if (!incoming.length) return

    const existingKeys = new Set(
      uploadedFiles.value.map((f) => `${f?.name}|${f?.size}|${f?.lastModified}`)
    )

    for (const f of incoming) {
      const key = `${f?.name}|${f?.size}|${f?.lastModified}`
      if (!existingKeys.has(key)) {
        uploadedFiles.value.push(f)
        existingKeys.add(key)
      }
    }
  }

  // ----------------------------
  // ✅ SCAN (use longApi + params)
  // ----------------------------
  async function scanZip() {
    if (!uploadedFiles.value.length) {
      throw new Error('No files to scan')
    }
    // Guard against concurrent scan
    if (scanning.value) {
      return { success: false, message: 'Scan already in progress' }
    }

    scanning.value = true
    clearError()

    try {
      const formData = new FormData()
      formData.append('file', uploadedFiles.value[0])

      // ✅ Increase scan limits to prevent "Stopping: write would exceed max bytes"
      const params = {
        max_unzipped_mb: 5000, // 5 GB
        max_files: 200000,
        max_depth: 25
      }

      const res = await longApi.post('/conversion/scan', formData, {
        params,
        timeout: 15 * 60 * 1000 // 15 minutes safety for huge zips
      })

      const data = res?.data || {}
      sessionId.value = data.session_id

      scannedGroups.value = (data.groups || []).map((g) => ({
        name: g.name,
        file_count: g.file_count || 0,
        size: g.size || 0
      }))

      // ✅ store scanned file list (needed for exclusion UI)
      scannedFiles.value = data.files || []

      scanSummary.value = data.summary || {
        totalGroups: scannedGroups.value.length,
        totalFiles: data.file_count || data.xml_count || 0
      }

      // Default selection: select all scanned groups
      selectedGroups.value = scannedGroups.value.map((g) => g.name)

      // reset exclusions on new scan
      excludedLogicalPaths.value = []

      return { success: true, groups: scannedGroups.value, files: scannedFiles.value }
    } catch (e) {
      setError(e)
      throw e
    } finally {
      scanning.value = false
    }
  }

  // ----------------------------
  // ✅ Exclusions (skip conversion)
  // ----------------------------
  function toggleExcludeByLogicalPath(logicalPath) {
    const lp = normalizeString(logicalPath)
    if (!lp) return
    const idx = excludedLogicalPaths.value.indexOf(lp)
    if (idx >= 0) excludedLogicalPaths.value.splice(idx, 1)
    else excludedLogicalPaths.value.push(lp)
  }

  function clearExclusions() {
    excludedLogicalPaths.value = []
  }

  // Load exclusions from backend (optional)
  async function loadExclusions() {
    if (!sessionId.value) return
    try {
      const res = await api.get(`/conversion/exclusions/${sessionId.value}`)
      excludedLogicalPaths.value = uniqStrings(res.data?.excluded || [])
    } catch (e) {
      console.warn('Failed to load exclusions:', e)
    }
  }

  // Apply exclusions to backend BEFORE conversion
  async function applyExclusions() {
    if (!sessionId.value) throw new Error('No session')

    const list = uniqStrings(excludedLogicalPaths.value || [])

    // Backend expects form field "excluded" repeated
    const fd = new FormData()
    list.forEach((x) => fd.append('excluded', x))

    await longApi.post(`/conversion/exclusions/${sessionId.value}`, fd, {
      timeout: 2 * 60 * 1000
    })

    // Keep local list normalized
    excludedLogicalPaths.value = list
    return { success: true, excluded_count: list.length }
  }

  // ----------------------------
  // ✅ CONVERT (longApi + don’t fail on post-load timeout)
  // ----------------------------
  async function convert() {
    if (!sessionId.value) {
      throw new Error('No session to convert')
    }
    // Guard against concurrent convert
    if (converting.value) {
      return { success: false, message: 'Conversion already in progress' }
    }

    converting.value = true
    clearError()

    try {
      // ✅ Persist exclusions first (so backend skips them)
      if (excludedLogicalPaths.value?.length) {
        await applyExclusions()
      }

      const formData = new FormData()
      formData.append('session_id', sessionId.value)
      formData.append('output_format', outputFormat.value)

      // If user picked groups, append them. If empty, convert ALL.
      const sel = uniqStrings(selectedGroups.value)
        .map(normalizeGroupName)
        .filter(Boolean)

      if (sel.length) {
        sel.forEach((g) => formData.append('groups', g))
        selectedGroups.value = sel
      }

      const res = await longApi.post('/conversion/convert', formData, {
        timeout: 60 * 60 * 1000 // ✅ 60 minutes for huge conversions
      })

      if (res.data?.success) {
        converted.value = true

        // ✅ IMPORTANT: do NOT fail conversion if listing takes too long.
        try {
          await loadConvertedFiles({ long: true })
        } catch (listErr) {
          console.warn('Conversion succeeded but loading file list timed out:', listErr)
        }

        return { success: true, stats: res.data.stats }
      }

      throw new Error(res.data?.message || 'Conversion failed')
    } catch (e) {
      setError(e)
      throw e
    } finally {
      converting.value = false
    }
  }

  // ----------------------------
  // ✅ Load output file list (use longApi for huge sessions)
  // ----------------------------
  async function loadConvertedFiles({ long = false } = {}) {
    if (!sessionId.value) return

    loading.value = true
    try {
      const client = long ? longApi : api
      const res = await client.get(`/conversion/files/${sessionId.value}`, {
        timeout: long ? 15 * 60 * 1000 : 30_000
      })

      groups.value = res.data.groups || []
      files.value = res.data.files || []
      totalFiles.value = res.data.total_files || 0

      if (groups.value.length > 0) {
        activeGroup.value = groups.value[0].name
        await loadGroupFiles()
      }
    } catch (e) {
      console.error('Failed to load converted files:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadGroupFiles() {
    if (!activeGroup.value) return

    groupFiles.value = files.value.filter((f) => f.group === activeGroup.value)
    if (groupFiles.value.length > 0) {
      activeFile.value = groupFiles.value[0].filename
      await loadFilePreview()
    } else {
      activeFile.value = ''
      preview.value = null
    }
  }

  async function loadFilePreview() {
    if (!activeFile.value || !sessionId.value) return

    try {
      // ✅ Safety: encode filename so route doesn't break for spaces/slashes
      const safeName = encodeURIComponent(activeFile.value)

      const res = await api.get(`/conversion/preview/${sessionId.value}/${safeName}`, {
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
    const res = await api.get(`/conversion/download/${sessionId.value}`, { responseType: 'blob' })
    downloadBlob(res.data, 'converted_output.zip')
  }

  async function downloadModified() {
    if (!sessionId.value || !editMode.value) return
    const res = await api.get(`/conversion/download-modified/${sessionId.value}`, { responseType: 'blob' })
    downloadBlob(res.data, 'modified_output.zip')
  }

  async function downloadFile(filename) {
    if (!sessionId.value) return
    const res = await api.get(`/conversion/download-file/${sessionId.value}/${filename}`, { responseType: 'blob' })
    downloadBlob(res.data, filename)
  }

  async function downloadGroup(groupName) {
    if (!sessionId.value) return

    const formData = new FormData()
    formData.append('output_format', outputFormat.value || 'csv')
    formData.append('preserve_structure', 'false')
    formData.append('groups', groupName)

    const res = await longApi.post(`/conversion/download-custom/${sessionId.value}`, formData, {
      responseType: 'blob',
      timeout: 30 * 60 * 1000
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
    selectedGroups.value = groups.value.map((g) => g.name)
  }

  function clearGroupSelection() {
    selectedGroups.value = []
  }

  function toggleGroup(name) {
    const n = normalizeGroupName(name)
    const idx = selectedGroups.value.indexOf(n)
    if (idx >= 0) selectedGroups.value.splice(idx, 1)
    else selectedGroups.value.push(n)
  }

  function reset() {
    sessionId.value = null
    uploadedFiles.value = []
    scannedGroups.value = []
    scanSummary.value = null
    converted.value = false
    scannedFiles.value = []
    excludedLogicalPaths.value = []
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
    uploadedFiles,
    scannedGroups,
    scanSummary,
    scannedFiles,
    excludedLogicalPaths,
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

    // Exclusion actions
    toggleExcludeByLogicalPath,
    clearExclusions,
    loadExclusions,
    applyExclusions,

    reset
  }
})
