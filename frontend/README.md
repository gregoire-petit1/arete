# Arete frontend

React 19 + Vite + Tailwind 4 + TanStack Query. PWA via `vite-plugin-pwa`.

```bash
npm ci           # or `make dev` from the repo root: API + this dev server together
npm run dev      # http://localhost:5173, proxies /api -> http://localhost:8000 (strips /api)
VITE_API_TARGET=http://localhost:8001 npm run dev   # backend on another port
npm run lint     # eslint
npm run build    # tsc -b && vite build -> dist/
```

- `@/` aliases `src/` (see `vite.config.ts`, `tsconfig.app.json`).
- All backend calls go through `src/lib/api.ts` with `API_BASE = "/api"`; in production nginx proxies `/api/` to the backend (see `../nginx.conf`).
- Pages live in `src/pages`, shared UI in `src/components`, API types in `src/types`.
