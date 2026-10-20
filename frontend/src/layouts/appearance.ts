import { theme, type ThemeConfig } from 'antd'
import type { AppearanceVariant, ColorScheme } from '../store/ui.ts'
const tokens = {
  orbit: {
    light: {
      colorPrimary: '#2168b0',
      colorBgContainer: '#f8fbff',
      colorBgElevated: '#edf3fa',
      colorText: '#172b41',
      colorTextSecondary: '#50677f',
      colorBorder: '#7d91a8',
      colorBgLayout: '#e9f0f7',
    },
    dark: {
      colorPrimary: '#7bcaff',
      colorBgContainer: '#101c2c',
      colorBgElevated: '#16263a',
      colorText: '#e5effa',
      colorTextSecondary: '#a4b7cc',
      colorBorder: '#6b84a0',
      colorBgLayout: '#0b1320',
    },
  },
  precision: {
    light: {
      colorPrimary: '#245edb',
      colorBgContainer: '#fff',
      colorBgElevated: '#f4f6f9',
      colorText: '#182334',
      colorTextSecondary: '#58687d',
      colorBorder: '#7f8da1',
      colorBgLayout: '#f5f6f8',
    },
    dark: {
      colorPrimary: '#8daeff',
      colorBgContainer: '#1b222d',
      colorBgElevated: '#242e3e',
      colorText: '#e8edf5',
      colorTextSecondary: '#a9b7cc',
      colorBorder: '#71839b',
      colorBgLayout: '#141922',
    },
  },
  studio: {
    light: {
      colorPrimary: '#3159d5',
      colorBgContainer: '#f8f7f3',
      colorBgElevated: '#f0eee8',
      colorText: '#252b34',
      colorTextSecondary: '#636970',
      colorBorder: '#8a8c8e',
      colorBgLayout: '#e9e6e0',
    },
    dark: {
      colorPrimary: '#8daeff',
      colorBgContainer: '#22252b',
      colorBgElevated: '#2c3037',
      colorText: '#f0efeb',
      colorTextSecondary: '#b5b6b7',
      colorBorder: '#7f858e',
      colorBgLayout: '#181a1f',
    },
  },
}
export function appearanceTheme(
  variant: AppearanceVariant,
  scheme: ColorScheme,
  reducedMotion = false,
): ThemeConfig {
  return {
    algorithm: scheme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      ...tokens[variant][scheme],
      motion: !reducedMotion,
      colorTextPlaceholder: tokens[variant][scheme].colorTextSecondary,
      fontFamily:
        '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
      fontSize: 14,
      controlHeight: 40,
      borderRadius: variant === 'precision' ? 3 : 6,
    },
  }
}
