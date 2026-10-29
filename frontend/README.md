# RET v4 Frontend (Vue 3 + Vite)

This frontend is the Vue 3 single-page application for RET v4. It drives the login flow, the main XML-to-CSV/XLSX conversion workspace, the Business Structure graph, the comparison experience, and the AI/RAG chat workflow.

## What this frontend does

- authenticates users through the FastAPI backend
- orchestrates upload → scan → convert → preview → download workflows
- renders the **Business Structure** tab from converted CSV contents
- provides comparison and drilldown navigation
- opens AI indexing and chat actions after conversion is complete
- supports theme-aware enterprise UI styling in light and dark mode

## Main runtime flow

### `src/views/LoginView.vue`

- hosts authentication and reset-password flows
- works with `src/components/auth/` components and `src/stores/authStore.ts`

### `src/views/MainView.vue`

- main user workspace with four tabs:
	- `Utility`
	- `Business Structure`
	- `Compare`
	- `AI`
- owns session state for the active conversion workflow
- starts async conversion jobs and polling
- fetches converted file listings and previews
- fetches Business Structure data after conversion finishes

### `src/views/AdminView.vue`

- admin-only area for user, session, log, and AI administration workflows

### `src/views/ComparisonDrilldownView.vue`

- detailed comparison review view for row/cell-level inspection

## Updated Business Structure feature

The Business Structure tab is no longer derived from scanned archive paths. It now uses converted CSV contents returned by the backend:

- `FUN_BUSINESS_UNIT.CSV`
- `INVENTORYORGANIZATIONMASTER.CSV`
- `INVENTORYORGANIZATIONCHILD.CSV`

The frontend component responsible for this is `src/components/workspace/BusinessStructurePanel.vue`.

### What the panel does

- waits until conversion is complete
- accepts the backend hierarchy payload via props
- renders a 5-layer graph:
	- Business Group
	- Ledger
	- Legal Entity
	- Operating Unit
	- Inventory Organization
- supports search, depth control, refresh, pan, and zoom
- shows diagnostics when required CSV files or columns are missing

## File and folder guide

### App shell and routing

| Path | Purpose |
|---|---|
| `src/main.ts` | Bootstraps Vue, Pinia, and Vue Router. |
| `src/App.vue` | Root application shell. |
| `src/router/index.ts` | App routes plus auth/admin navigation guards. |

### Stores and composables

| Path | Purpose |
|---|---|
| `src/stores/authStore.ts` | In-memory access token, user identity, login/logout, single-flight refresh. The token is never written to Web Storage; a reload restores the session through the HttpOnly refresh cookie. |
| `src/stores/toastStore.ts` | Toast notification state and helpers. |
| `src/composable/useTheme.ts` | Follows the OS theme; stores an override only while it differs from the OS setting. |

### Shared utilities

| Path | Purpose |
|---|---|
| `src/utils/api.ts` | The single HTTP layer: default and long-running Axios clients, 401 refresh-and-retry, `apiCall`, job polling. |
| `src/utils/groups.ts` | Group name comparison/normalization helpers. |
| `src/utils/oracleApps.ts` | Oracle application catalog helpers/constants used by the workspace. |
| `src/utils/sanitize.ts` | DOMPurify wrapper; every `v-html` that shows chat or model output goes through it. |

### Workspace components

| Path | Purpose |
|---|---|
| `src/components/workspace/FileUploader.vue` | Upload and scan entry point for ZIP/XML workflows. |
| `src/components/workspace/EditModeToggle.vue` | Enables or disables session-only output editing. |
| `src/components/workspace/EditModePanel.vue` | Add/update/remove output files during edit mode. |
| `src/components/workspace/BusinessStructurePanel.vue` | Searchable Mermaid graph for the converted Business Structure hierarchy. |
| `src/components/workspace/ComparisonPanel.vue` | Comparison launch and summary UI. |
| `src/components/workspace/AIPanel.vue` | AI indexing, chat launch, and transcript actions. |

### Chart and message rendering

| Path | Purpose |
|---|---|
| `src/components/workspace/charts/ChartRenderer.vue` | Renders charts returned by AI workflows. |
| `src/components/workspace/charts/DataTable.vue` | Renders AI or comparison-related tables. |
| `src/components/workspace/charts/MessageRenderer.vue` | Formats rich AI responses. |
| `src/components/workspace/charts/StatsCardGrid.vue` | Displays stat-card summaries. |

## Development commands

```powershell
cd frontend
npm install
npm run dev
```

### Production build

```powershell
cd frontend
npm run build
npm run preview
```

## Vue + Vite references

RET v4 uses Vue 3 `<script setup>` SFCs and Vite for development/build tooling. For framework reference:

- [Vue `<script setup>` docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup)
- [Vue tooling guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support)
