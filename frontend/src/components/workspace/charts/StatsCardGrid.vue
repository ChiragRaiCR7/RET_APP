<template>
  <div class="stats-card-grid">
    <div
      v-for="(stat, idx) in stats"
      :key="idx"
      class="stat-card"
      :class="stat.trend ? `trend-${stat.trend}` : 'trend-neutral'"
    >
      <div class="stat-card__accent"></div>
      <div class="stat-icon" v-if="stat.icon">{{ stat.icon }}</div>
      <div class="stat-content">
        <div class="stat-value">{{ formatValue(stat.value, stat.format) }}</div>
        <div class="stat-label">{{ stat.label }}</div>
        <div v-if="stat.change" class="stat-change" :class="`change-${stat.trend || 'neutral'}`">
          <span class="change-icon" aria-hidden="true">{{ getTrendIcon(stat.trend) }}</span>
          <span>{{ stat.change }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type Trend = 'up' | 'down' | 'neutral'

/** One KPI tile parsed from a model answer. */
export interface StatCard {
  label: string
  value: number | string
  format?: 'number' | 'percentage' | 'currency' | 'decimal'
  icon?: string
  change?: string
  trend?: Trend
}

defineProps<{ stats: StatCard[] }>()

function formatValue(value: StatCard['value'], format?: StatCard['format']): string {
  if (format === 'number') {
    return Number(value).toLocaleString()
  }
  if (format === 'percentage') {
    return (Number(value) * 100).toFixed(1) + '%'
  }
  if (format === 'currency') {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))
  }
  if (format === 'decimal') {
    return Number(value).toFixed(2)
  }
  return String(value)
}

function getTrendIcon(trend?: Trend): string {
  if (trend === 'up') return '↗'
  if (trend === 'down') return '↘'
  return '→'
}
</script>

<style scoped>
.stats-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}

.stat-card {
  position: relative;
  background: var(--surface-elevated);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md, 12px);
  padding: 1.25rem 1.25rem 1.25rem 1.5rem;
  display: flex;
  gap: 0.9rem;
  align-items: flex-start;
  transition: box-shadow var(--transition-base, 200ms), border-color var(--transition-base, 200ms),
              transform var(--transition-base, 200ms);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--brand-primary);
}

/* Left accent bar */
.stat-card__accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: var(--radius-md, 12px) 0 0 var(--radius-md, 12px);
  background: var(--brand-primary);
}

.stat-card.trend-up    .stat-card__accent { background: var(--success, #118a5a); }
.stat-card.trend-down  .stat-card__accent { background: var(--error, #dc2626); }
.stat-card.trend-neutral .stat-card__accent { background: var(--brand-primary); }

.stat-icon {
  font-size: 2rem;
  line-height: 1;
  opacity: 0.85;
  flex-shrink: 0;
  padding-top: 0.1rem;
}

.stat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}

.stat-value {
  font-size: 1.75rem;
  font-weight: 800;
  color: var(--text-heading);
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat-label {
  font-size: var(--text-xs, 0.75rem);
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.07em;
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: var(--text-xs, 0.75rem);
  font-weight: 700;
  margin-top: 0.35rem;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-full, 9999px);
  width: fit-content;
}

.change-up {
  color: var(--success, #118a5a);
  background: var(--success-bg, rgba(17, 138, 90, 0.12));
}
.change-down {
  color: var(--error, #dc2626);
  background: var(--error-bg, rgba(220, 38, 38, 0.1));
}
.change-neutral {
  color: var(--brand-secondary);
  background: var(--brand-subtle);
}

.change-icon {
  font-size: 1.05em;
}
</style>
