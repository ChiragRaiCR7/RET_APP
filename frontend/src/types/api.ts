/**
 * Response shapes of the RET v4 API, mirroring the Pydantic models in
 * backend/api/schemas/. Keep field names and optionality in step with the backend.
 */

/** Oracle module enrichment the backend attaches to files and groups. */
export interface OracleEnrichment {
  oracle_module_code?: string | null
  oracle_module_name?: string | null
  oracle_business_domain?: string | null
  oracle_is_canonical?: boolean | null
  oracle_is_obsolete?: boolean | null
}

// --- conversion.py -------------------------------------------------------

export interface ScannedFileEntry extends OracleEnrichment {
  filename: string
  path: string
  group: string
  size: number
  abs_path?: string | null
  logical_path?: string | null
  file_type?: string | null
  business_zip?: string | null
  folder_path?: string | null
  root_folder?: string | null
  zip_chain?: string[]
}

export interface ScanGroupEntry extends OracleEnrichment {
  name: string
  file_count: number
  size: number
  auto_embed_eligible?: boolean | null
  auto_embed_reason?: string | null
}

export interface ScanSummary {
  totalFiles: number
  totalGroups: number
  totalSize: number
  typeCounts?: Record<string, number> | null
}

/** Built in conversion_service.scan (typed loosely as a dict in the schema). */
export interface OracleScanSummary {
  canonical_count: number
  custom_count: number
  domain_breakdown: Record<string, number>
  canonical_groups: string[]
}

export interface ZipScanResponse {
  session_id: string
  xml_count: number
  group_count: number
  file_count?: number | null
  files: ScannedFileEntry[]
  groups: ScanGroupEntry[]
  summary: ScanSummary
  oracle_summary?: OracleScanSummary | null
  /** Not in the schema; some scan paths add it through extra fields. */
  warnings?: string[]
}

export interface ConversionFileEntry extends OracleEnrichment {
  filename: string
  group: string
  rows: number
  columns: number
  size: string
  file_type?: string | null
  logical_path?: string | null
}

export interface ConversionGroupEntry extends OracleEnrichment {
  name: string
  file_count: number
  total_rows: number
  total_size: number
}

export interface ConversionFilesResponse {
  session_id: string
  total_files: number
  total_groups: number
  excluded_count?: number | null
  groups: ConversionGroupEntry[]
  files: ConversionFileEntry[]
}

export interface ColumnMeta {
  header: string
  classification: 'high_value' | 'low_value' | string
  reason: string
}

export interface FilePreviewResponse {
  filename: string
  headers: string[]
  rows: string[][]
  total_rows: number
  preview_rows: number
  columns: number
  column_meta?: ColumnMeta[] | null
  simplified_order?: number[] | null
}

// --- comparison.py ---------------------------------------------------------

/** One row of a drilldown delta: column values plus the diff markers the backend adds. */
export interface DeltaRow {
  _kind_?: 'MODIFIED' | 'ADDED' | 'REMOVED' | string
  _changed_cols_?: (number | string)[]
  [column: string]: unknown
}

export interface DeltaFrame {
  headers: string[]
  rows: DeltaRow[]
}

/** POST /comparison/drilldown (serialized by alias: deltaA/deltaB, row_count_A/B). */
export interface DrilldownResponse {
  filename?: string
  group?: string
  header: string[]
  stats: Record<string, number>
  truncated: boolean
  deltaA?: DeltaFrame
  deltaB?: DeltaFrame
  row_count_A?: number
  row_count_B?: number
  col_count?: number
  error?: string
}

// --- rag_router.py (/v2/ai/*) -----------------------------------------------

/** A retrieved chunk as the chat endpoint returns it (field names vary by retriever). */
export interface RawChatSource {
  file?: string
  source?: string
  doc?: string
  group?: string | null
  score?: number | null
  snippet?: string
}

export interface ChatResponse {
  answer?: string
  sources?: RawChatSource[]
  response_type?: string
  responseType?: string
  visualizations?: unknown[]
}

export interface ChatHistoryResponse {
  messages?: {
    role?: 'user' | 'assistant'
    content?: string
    timestamp?: string
    response_type?: string
    responseType?: string
    sources?: RawChatSource[]
  }[]
}

export interface EmbeddingGroup {
  name: string
  indexed?: boolean
  chunk_count?: number
}

export interface EmbeddingGroupsResponse {
  all_groups?: (string | EmbeddingGroup)[]
  groups?: (string | EmbeddingGroup)[]
  auto_embedded_groups?: string[]
  excluded_groups?: string[]
}

export interface IndexGroupsResponse {
  status?: 'queued' | 'success' | string
  task_id?: string
  embedded_groups?: string[]
  message?: string
}

export interface EmbeddingTaskStatus {
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | string
  groups?: string[]
  error?: string
}

export interface StopEmbeddingResponse {
  stopped?: boolean
  message?: string
  worker_tasks_cancelled?: number
  auto_embed_suppressed?: boolean
}

// --- business_structure.py -------------------------------------------------

export type BusinessNodeType =
  | 'business_group'
  | 'ledger'
  | 'legal_entity'
  | 'operating_unit'
  | 'inventory_org'

export interface BusinessStructureNode {
  name: string
  node_type: BusinessNodeType
  children: BusinessStructureNode[]
}

export interface BusinessStructureResponse {
  status: 'ready' | 'not_converted' | 'missing_files' | 'missing_columns' | 'no_data'
  nodes: BusinessStructureNode[]
  diagnostics: string[]
  source_files: string[]
  pruned_summary?: Record<string, unknown> | null
}
