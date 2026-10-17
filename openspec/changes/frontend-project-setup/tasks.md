## 1. 工程骨架

- [x] 1.1 在 `frontend/` 初始化 Vite + React 18 + TypeScript 工程，建立 issue 约定的目录骨架和 `@` 路径别名，并在根 `.gitignore` 忽略 `node_modules`。验证：`frontend/package.json`、`frontend/tsconfig.json`、`frontend/vite.config.ts` 和 `frontend/src/main.tsx` 存在，且 `node_modules` 被忽略。
- [ ] 1.2 添加开发、测试、生产环境文件和类型化读取模块。必填变量缺失时抛出带变量名的错误。验证：读取模块对缺失 `VITE_API_BASE_URL` 失败，对三套环境文件能读到 API Base URL、WebSocket URL、应用名和功能开关。

## 2. 构建与规范

- [ ] 2.1 配置开发服务器端口 3000、`/api` 到 `http://localhost:8000` 的代理（含 WebSocket），以及路由级懒加载。验证：配置中存在该代理，且六个页面入口使用懒加载。
- [ ] 2.2 配置 ESLint、Prettier、EditorConfig，以及只检查 `frontend/` 暂存文件的 husky + lint-staged。验证：`npm run lint` 与格式校验在初始工程上成功退出，钩子脚本不扫描仓库其他目录。

## 3. 应用外壳

- [ ] 3.1 安装 Ant Design、Zustand、React Router、Axios、socket.io-client、ECharts、TanStack Table、Monaco、React Hook Form 和 dayjs，并配置 Tailwind 的响应式断点与 class 深色模式。验证：这些依赖出现在 `frontend/package.json`，Tailwind 启用 `darkMode: "class"`。
- [ ] 3.2 实现外壳导航和六个占位页：仪表盘、题目、评估、结果、实验、设置。未知路径回到仪表盘；深色开关在本次浏览中保持；窄屏仍可到达六个入口。验证：路由表包含这六个路径和未知路径回退，占位页不发起后端请求。

## 4. 集成验证

- [ ] 4.1 运行类型检查、代码检查、格式校验和生产构建。验证：四条命令都成功退出，生产产物包含按路由分割的代码块。
