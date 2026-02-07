<template>
  <div class="chart-renderer" :class="`chart-type-${chartConfig.type}`">
    <div v-if="chartConfig.title" class="chart-title">
      <h4>{{ chartConfig.title }}</h4>
      <span v-if="chartConfig.subtitle" class="chart-subtitle">{{ chartConfig.subtitle }}</span>
    </div>
    
    <div class="chart-container" ref="chartContainer">
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

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
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

// Register Chart.js components
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

const props = defineProps({
  chartConfig: {
    type: Object,
    required: true,
    validator: (value) => {
      return value && value.type && value.data
    }
  }
})

const chartContainer = ref(null)
const chartKey = ref(0)

// Map chart types to components
const chartComponents = {
  bar: Bar,
  line: Line,
  pie: Pie,
  doughnut: Doughnut,
  radar: Radar,
  polarArea: PolarArea,
  scatter: Scatter
}

const chartComponent = computed(() => {
  return chartComponents[props.chartConfig.type?.toLowerCase()]
})

const chartData = computed(() => {
  const data = props.chartConfig.data
  
  // Apply color schemes if not provided
  if (data.datasets) {
    data.datasets = data.datasets.map((dataset, index) => ({
      ...dataset,
      backgroundColor: dataset.backgroundColor || generateColors(data.labels?.length || 10, 0.7, index),
      borderColor: dataset.borderColor || generateColors(data.labels?.length || 10, 1, index),
      borderWidth: dataset.borderWidth ?? 2
    }))
  }
  
  return data
})

const baseOptions = computed(() => {
  const isDark = document.documentElement.classList.contains('dark') || 
                 window.matchMedia('(prefers-color-scheme: dark)').matches
  
  return {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: props.chartConfig.aspectRatio || 2,
    plugins: {
      legend: {
        display: props.chartConfig.showLegend !== false,
        position: props.chartConfig.legendPosition || 'top',
        labels: {
          color: isDark ? '#e0e0e0' : '#333',
          font: {
            size: 12,
            family: "'Verdana', sans-serif"
          },
          padding: 15
        }
      },
      tooltip: {
        enabled: true,
        backgroundColor: isDark ? 'rgba(50, 50, 50, 0.95)' : 'rgba(255, 255, 255, 0.95)',
        titleColor: isDark ? '#fff' : '#000',
        bodyColor: isDark ? '#e0e0e0' : '#333',
        borderColor: '#FFC000',
        borderWidth: 1,
        padding: 12,
        displayColors: true,
        callbacks: props.chartConfig.tooltipCallbacks || {}
      },
      title: {
        display: false // We handle title separately
      }
    },
    scales: generateScales(props.chartConfig.type, isDark)
  }
})

const mergedOptions = computed(() => {
  return deepMerge(baseOptions.value, props.chartConfig.options || {})
})

function generateColors(count, alpha, seed = 0) {
  const baseColors = [
    [255, 192, 0],   // Brand gold
    [66, 165, 245],  // Blue
    [102, 187, 106], // Green
    [239, 83, 80],   // Red
    [171, 71, 188],  // Purple
    [255, 167, 38],  // Orange
    [38, 198, 218],  // Cyan
    [233, 30, 99],   // Pink
    [121, 134, 203], // Indigo
    [0, 150, 136]    // Teal
  ]
  
  const colors = []
  for (let i = 0; i < count; i++) {
    const baseColor = baseColors[(i + seed) % baseColors.length]
    colors.push(`rgba(${baseColor[0]}, ${baseColor[1]}, ${baseColor[2]}, ${alpha})`)
  }
  
  return colors
}

function generateScales(chartType, isDark) {
  const textColor = isDark ? '#b0b0b0' : '#666'
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
  
  if (['pie', 'doughnut', 'polarArea', 'radar'].includes(chartType?.toLowerCase())) {
    return {}
  }
  
  return {
    x: {
      ticks: {
        color: textColor,
        font: { size: 11 }
      },
      grid: {
        color: gridColor,
        drawBorder: false
      }
    },
    y: {
      ticks: {
        color: textColor,
        font: { size: 11 }
      },
      grid: {
        color: gridColor,
        drawBorder: false
      },
      beginAtZero: true
    }
  }
}

function deepMerge(target, source) {
  const output = { ...target }
  if (isObject(target) && isObject(source)) {
    Object.keys(source).forEach(key => {
      if (isObject(source[key])) {
        if (!(key in target)) {
          Object.assign(output, { [key]: source[key] })
        } else {
          output[key] = deepMerge(target[key], source[key])
        }
      } else {
        Object.assign(output, { [key]: source[key] })
      }
    })
  }
  return output
}

function isObject(item) {
  return item && typeof item === 'object' && !Array.isArray(item)
}

// Force re-render on theme change
watch(() => document.documentElement.classList.contains('dark'), () => {
  chartKey.value++
})
</script>

<style scoped>
.chart-renderer {
  margin: 1.5rem 0;
  padding: 1.5rem;
  background: var(--bg-elevated, #2a2a3e);
  border: 1px solid var(--border-color, #3a3a4e);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.chart-title {
  margin-bottom: 1.25rem;
  text-align: center;
}

.chart-title h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #fff);
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.chart-subtitle {
  display: block;
  color: var(--text-secondary, #b0b0b0);
  font-size: 0.9rem;
  font-style: italic;
}

.chart-container {
  position: relative;
  min-height: 300px;
  padding: 1rem;
}

.chart-description {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color, #3a3a4e);
  color: var(--text-secondary, #b0b0b0);
  font-size: 0.9rem;
  line-height: 1.5;
  text-align: center;
}

.chart-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-secondary, #b0b0b0);
}

.error-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

/* Chart type specific styles */
.chart-type-pie .chart-container,
.chart-type-doughnut .chart-container,
.chart-type-polararea .chart-container {
  max-width: 500px;
  margin: 0 auto;
}

.chart-type-line .chart-container,
.chart-type-bar .chart-container {
  min-height: 350px;
}

.chart-type-radar .chart-container {
  max-width: 600px;
  margin: 0 auto;
}
</style>
