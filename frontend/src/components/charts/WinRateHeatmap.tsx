import ReactECharts from 'echarts-for-react'
import type { WinRateRow } from '@/experiments/types.ts'

export interface WinRateHeatmapProps {
  strategy: string
  matrix: WinRateRow[]
}

/** 胜率矩阵热力图（数据形状见 src/experiment_report.py build_model_comparison）。 */
export function WinRateHeatmap({ strategy, matrix }: WinRateHeatmapProps) {
  const models = matrix.map((row) => row.model)
  const opponents = [
    ...new Set(matrix.flatMap((row) => Object.keys(row.against))),
  ]
  const cells: [number, number, number][] = []
  matrix.forEach((row, rowIndex) => {
    opponents.forEach((opponent, colIndex) => {
      const cell = row.against[opponent]
      if (cell)
        cells.push([colIndex, rowIndex, Math.round(cell.win_rate * 100)])
    })
  })
  return (
    <div data-testid={`win-rate-heatmap-${strategy}`}>
      <ReactECharts
        style={{ height: 320 }}
        notMerge
        option={{
          tooltip: {
            position: 'top',
            formatter: (p: { name: string; value: number[] }) =>
              `${p.name}: ${p.value[2]}%`,
          },
          grid: { height: '50%', top: '10%' },
          xAxis: {
            type: 'category',
            data: opponents,
            splitArea: { show: true },
          },
          yAxis: { type: 'category', data: models, splitArea: { show: true } },
          visualMap: {
            min: 0,
            max: 100,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: '12%',
            inRange: {
              color: ['#313695', '#4575b4', '#ffffbf', '#fdae61', '#d73027'],
            },
          },
          series: [
            {
              type: 'heatmap',
              data: cells,
              label: {
                show: true,
                formatter: (p: { value: number[] }) => `${p.value[2]}%`,
              },
            },
          ],
        }}
      />
    </div>
  )
}
