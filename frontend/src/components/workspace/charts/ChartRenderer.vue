
<template>
  <div class="chart-renderer" :class="`chart-type-${chartConfig.type}`">
    <div v-if="chartConfig.title" class="chart-title">
      <h4>{{ chartConfig.title }}</h4>
      <span v-if="chartConfig.subtitle" class="chart-subtitle">{{ chartConfig.subtitle }}</span>
    </div>
    
    <div class="chart-container">
      <component 
        :is="chartComponent" 
        v-if="chartComponent"
        :data="chartData" 
        :options="mergedOptions" 
        :key="chartKey"
      />
      <div v-else class="chart-error">
        <span class="error-icon">⚠️</span>
        <p>Unsupported chart type: {{ chartConfig.type }}</p>
      </div>
    </div>
    
    <div v-if="chartConfig.description" class="chart-description">
      {{ chartConfig.description }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { Bar, Line, Pie, Doughnut, Radar, PolarArea, Scatter } from 'vue-chartjs'
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  ArcElement,
  RadialLinearScale,
  Filler
} from 'chart.js'
import { useTheme } from '@/composable/useTheme'

ChartJS.register(
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  ArcElement,
  RadialLinearScale,
  Filler
)

type PlainObject = Record<string, unknown>

/** Chart definition parsed from a model answer; every field is untrusted input. */
export interface ChartConfig {
  type: string
  data: { labels?: unknown[]; datasets?: PlainObject[] } & PlainObject
  title?: string
  subtitle?: string
  description?: string
  aspectRatio?: number
  showLegend?: boolean
  legendPosition?: string
  options?: PlainObject
}

const props = defineProps<{ chartConfig: ChartConfig }>()

const { theme } = useTheme()
const isDark = computed(() => theme.value === 'dark')
const chartKey = ref(0)

const chartComponents: Record<string, Component> = {
  bar: Bar,
  line: Line,
  pie: Pie,
  doughnut: Doughnut,
  radar: Radar,
  polarArea: PolarArea,
  scatter: Scatter
}

const chartComponent = computed(() => chartComponents[String(props.chartConfig.type ?? '').toLowerCase()])

const chartData = computed(() => {
  const src = props.chartConfig?.data
  if (!src) return { labels: [], datasets: [] }
  const count = src.labels?.length || 10
  // Return a new object; never mutate the prop.
  return {
    ...src,
    datasets: (src.datasets || []).map((dataset, index) => ({
      ...dataset,
      backgroundColor: dataset.backgroundColor || generateColors(count, 0.7, index),
      borderColor: dataset.borderColor || generateColors(count, 1, index),
      borderWidth: dataset.borderWidth ?? 2
    }))
  }
})

const baseOptions = computed<PlainObject>(() => {
  const dark = isDark.value
  return {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: props.chartConfig.aspectRatio || 2,
    plugins: {
      legend: {
        display: props.chartConfig.showLegend !== false,
        position: props.chartConfig.legendPosition || 'top',
        labels: {
          color: dark ? '#e0e0e0' : '#333',
          font: { size: 12, family: "'Verdana', sans-serif" },
          padding: 15
        }
      },
      tooltip: {
        enabled: true,
        backgroundColor: dark ? 'rgba(50, 50, 50, 0.95)' : 'rgba(255, 255, 255, 0.95)',
        titleColor: dark ? '#fff' : '#000',
        bodyColor: dark ? '#e0e0e0' : '#333',
        borderColor: '#FFC000',
        borderWidth: 1,
        padding: 12,
        displayColors: true
      },
      title: { display: false } // rendered by the template instead
    },
    scales: generateScales(props.chartConfig.type, dark)
  }
})

const mergedOptions = computed(() => deepMerge(baseOptions.value, props.chartConfig.options || {}))

const BASE_COLORS: ReadonlyArray<readonly [number, number, number]> = [
  [255, 192, 0], // brand gold
  [66, 165, 245],
  [102, 187, 106],
  [239, 83, 80],
  [171, 71, 188],
  [255, 167, 38],
  [38, 198, 218],
  [233, 30, 99],
  [121, 134, 203],
  [0, 150, 136]
]

function generateColors(count: number, alpha: number, seed = 0): string[] {
  return Array.from({ length: count }, (_, i) => {
    const [r, g, b] = BASE_COLORS[(i + seed) % BASE_COLORS.length]!
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  })
}

function generateScales(chartType: string | undefined, dark: boolean): PlainObject {
  if (['pie', 'doughnut', 'polararea', 'radar'].includes(String(chartType ?? '').toLowerCase())) return {}
  const axis = {
    ticks: { color: dark ? '#b0b0b0' : '#666', font: { size: 11 } },
    grid: { color: dark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)', drawBorder: false }
  }
  return { x: axis, y: { ...axis, beginAtZero: true } }
}

const UNSAFE_KEYS = new Set(['__proto__', 'constructor', 'prototype'])

function isObject(item: unknown): item is PlainObject {
  return !!item && typeof item === 'object' && !Array.isArray(item)
}

/** Overlays model-supplied chart options on the defaults, skipping prototype keys. */
function deepMerge(target: PlainObject, source: PlainObject): PlainObject {
  const output: PlainObject = { ...target }
  for (const key of Object.keys(source)) {
    if (UNSAFE_KEYS.has(key)) continue
    const value = source[key]
    const current = target[key]
    output[key] = isObject(value) && isObject(current) ? deepMerge(current, value) : value
  }
  return output
}

// Chart.js reads colors once at mount, so re-create the chart when the theme flips.
watch(isDark, () => {
  chartKey.value++
})
</script>

<style scoped>
.chart-renderer {
  margin: 1rem 0;
  padding: 1.25rem;
  background: var(--surface-elevated);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md, 12px);
  box-shadow: var(--shadow-sm);
}

.chart-title {
  margin-bottom: 1rem;
  text-align: center;
}

.chart-title h4 {
  margin: 0 0 0.35rem 0;
  color: var(--text-heading);
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.chart-subtitle {
  display: block;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-style: italic;
}

.chart-container {
  position: relative;
  min-height: 280px;
  padding: 0.5rem 0;
}

.chart-description {
  margin-top: 0.875rem;
  padding-top: 0.875rem;
  border-top: 1px solid var(--border-light);
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;
  text-align: center;
}

.chart-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-tertiary);
  gap: 0.5rem;
}

.error-icon {
  font-size: 2.5rem;
}

/* Chart type–specific sizing */
.chart-type-pie .chart-container,
.chart-type-doughnut .chart-container,
.chart-type-polararea .chart-container {
  max-width: 500px;
  margin: 0 auto;
}

.chart-type-line .chart-container,
.chart-type-bar .chart-container {
  min-height: 320px;
}

.chart-type-radar .chart-container {
  max-width: 580px;
  margin: 0 auto;
}
</style>
