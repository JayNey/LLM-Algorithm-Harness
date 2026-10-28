import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import ReactECharts from 'echarts-for-react'

export interface ScatterPlotProps {
  points: { label: string; x: number; y: number }[]
  xName: string
  yName: string
  highlightIds?: string[]
}

/** 散点图（帕累托/成本效益）。highlight 的点单独着色。 */
export function ScatterPlot({
  points,
  xName,
  yName,
  highlightIds = [],
}: ScatterPlotProps) {
  useTranslation()

  const normal = points.filter((p) => !highlightIds.includes(p.label))
  const highlighted = points.filter((p) => highlightIds.includes(p.label))
  return (
    <ReactECharts
      style={{ height: 320 }}
      notMerge
      option={{
        tooltip: { type: 'item' },
        legend: {},
        xAxis: { type: 'value', name: xName },
        yAxis: { type: 'value', name: yName },
        series: [
          {
            name: yName,
            type: 'scatter',
            data: normal.map((p) => ({ name: p.label, value: [p.x, p.y] })),
          },
          ...(highlighted.length
            ? [
                {
                  name: t('{{value1}}（前沿）', { value1: yName }),
                  type: 'scatter',
                  symbolSize: 14,
                  data: highlighted.map((p) => ({
                    name: p.label,
                    value: [p.x, p.y],
                  })),
                },
              ]
            : []),
        ],
      }}
    />
  )
}

export interface RadarChartProps {
  labels: string[]
  datasets: { label: string; values: number[] }[]
}

export function RadarChart({ labels, datasets }: RadarChartProps) {
  useTranslation()

  return (
    <ReactECharts
      style={{ height: 320 }}
      notMerge
      option={{
        tooltip: {},
        legend: {},
        radar: {
          indicator: labels.map((name) => ({ name })),
          data: datasets.length,
        },
        series: [
          {
            type: 'radar',
            data: datasets.map((dataset) => ({
              name: dataset.label,
              value: dataset.values,
            })),
          },
        ],
      }}
    />
  )
}

export interface BarCompareProps {
  labels: string[]
  series: { name: string; values: number[] }[]
  yName?: string
}

export function BarCompare({ labels, series, yName }: BarCompareProps) {
  useTranslation()

  return (
    <ReactECharts
      style={{ height: 320 }}
      notMerge
      option={{
        tooltip: { trigger: 'axis' },
        legend: {},
        xAxis: { type: 'category', data: labels },
        yAxis: { type: 'value', ...(yName ? { name: yName } : {}) },
        series: series.map((item) => ({
          name: item.name,
          type: 'bar',
          data: item.values,
        })),
      }}
    />
  )
}

export interface TrendLineProps {
  series: {
    model: string
    points: {
      timestamp: string | null
      accuracy: number | null
      cost_usd: number | null
    }[]
  }[]
  metric: 'accuracy' | 'cost_usd'
}

/** 学习曲线折线：按模型分组的准确率/成本序列（时间升序）。 */
export function TrendLine({ series, metric }: TrendLineProps) {
  useTranslation()

  const yName = metric === 'accuracy' ? t('准确率') : t('成本（USD）')
  return (
    <ReactECharts
      style={{ height: 360 }}
      notMerge
      option={{
        tooltip: { trigger: 'axis' },
        legend: {},
        xAxis: { type: 'time', name: t('完成时间') },
        yAxis: { type: 'value', name: yName },
        series: series.map((group) => ({
          name: group.model,
          type: 'line',
          connectNulls: true,
          data: group.points
            .filter(
              (point) => point.timestamp !== null && point[metric] !== null,
            )
            .map((point) => [point.timestamp, point[metric]]),
        })),
      }}
    />
  )
}
