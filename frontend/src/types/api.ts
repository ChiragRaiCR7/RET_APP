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
