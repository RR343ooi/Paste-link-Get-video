<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only recreates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# freemediadownloader

Two independent apps: Next.js frontend (root, port 3000, still `create-next-app` boilerplate) and Flask downloader backend (`server/`, port 5000, actual product). No proxy/wiring between them.

## Commands

- `npm run dev` — Next.js dev (3000); `npm run build` / `npm run start` — prod
- `npm run lint` — ESLint (no `--fix`); `npx tsc --noEmit` for typecheck (no `typecheck` script)
- No test framework or test script configured
- `cd server && pip install -r requirements.txt && python app.py` — Flask dev (5000, `debug=True`)
- `cd server && docker compose up` or `docker build -t freemediadownloader . && docker run -p 5000:5000 -v ./downloads:/app/downloads freemediadownloader`

## Next.js quirks (root)

- Next.js 16.3.5 + React 19.2.8 + TypeScript 5 + Tailwind 4 + ESLint 9 flat config
- `eslint.config.mjs` flat config with `eslint-config-next/core-web-vitals` + `typescript`; ignores `.next/**`, `out/**`, `build/**`, `next-env.d.ts`
- Tailwind 4 via `@import "tailwindcss"` + `@theme inline` in `app/globals.css` — no `tailwind.config.js`
- App Router entrypoints: `app/layout.tsx` / `app/page.tsx`; path alias `@/*` → `./*`
- Generated/gitignored: `.next/`, `next-env.d.ts`, `*.tsbuildinfo`; `CLAUDE.md` is `@AGENTS.md` — keep in sync
- Skill installed: `anthropics/skills@frontend-design` (see `skills-lock.json` / `.agents/skills/`)

## Flask quirks (`server/`)

- `server/app.py` — Flask + `flask-cors` + `yt-dlp==2025.1.15`; downloads to `server/downloads/` (gitignored via `downloads/`)
- `ffmpeg` required for MP3 extraction (not in `requirements.txt`; Dockerfile installs via `apt` on `python:3.12-slim`)
- Downloads run in daemon threads (`_active_downloads` dict + `_download_lock`); poll `GET /api/download/status/<task_id>`
- API: `POST /api/analyze`, `POST /api/download/video|audio|all`, `GET /api/download/status/<id>`, `GET /api/downloads`, `GET /api/downloads/<filename>`
- `server/templates/index.html` + `server/static/{app.js,style.css}` is the served UI (vanilla JS), separate from Next.js app
