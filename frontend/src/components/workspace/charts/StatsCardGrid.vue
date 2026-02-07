<template>
  <div class="stats-card-grid">
    <div 
      v-for="(stat, idx) in stats" 
      :key="idx" 
      class="stat-card"
      :class="stat.trend ? `trend-${stat.trend}` : ''"
    >
      <div class="stat-icon" v-if="stat.icon">{{ stat.icon }}</div>
      <div class="stat-content">
        <div class="stat-value">{{ formatValue(stat.value, stat.format) }}</div>
        <div class="stat-label">{{ stat.label }}</div>
        <div v-if="stat.change" class="stat-change" :class="`change-${stat.trend || 'neutral'}`">
          <span class="change-icon">{{ getTrendIcon(stat.trend) }}</span>
          <span>{{ stat.change }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  stats: {
    type: Array,
    required: true,
    validator: (value) => {
      return value.every(stat => stat.label && stat.value !== undefined)
    }
  }
})

function formatValue(value, format) {
  if (format === 'number') {
    return Number(value).toLocaleString()
  }
  if (format === 'percentage') {
    return (Number(value) * 100).toFixed(1) + '%'
  }
  if (format === 'currency') {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
  }
  if (format === 'decimal') {
    return Number(value).toFixed(2)
  }
  return String(value)
}

function getTrendIcon(trend) {
  if (trend === 'up') return '↗'
  if (trend === 'down') return '↘'
  return '→'
}
</script>

<style scoped>
.stats-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.25rem;
  margin: 1.5rem 0;
}

.stat-card {
  background: var(--bg-elevated, #2a2a3e);
  border: 1px solid var(--border-color, #3a3a4e);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  gap: 1rem;
  transition: all 0.3s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(255, 192, 0, 0.15);
  border-color: #FFC000;
}

.stat-card.trend-up {
  border-left: 3px solid #4CAF50;
}

.stat-card.trend-down {
  border-left: 3px solid #F44336;
}

.stat-card.trend-neutral {
  border-left: 3px solid #FFC000;
}

.stat-icon {
  font-size: 2.5rem;
  line-height: 1;
  opacity: 0.8;
}

.stat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary, #fff);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 0.9rem;
  color: var(--text-secondary, #b0b0b0);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.85rem;
  font-weight: 600;
  margin-top: 0.5rem;
}

.change-up {
  color: #4CAF50;
}

.change-down {
  color: #F44336;
}

.change-neutral {
  color: #FFC000;
}

.change-icon {
  font-size: 1.1em;
}
</style>
