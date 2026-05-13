# Multi-stage build for both dev and prod.
#
# Local (docker-compose): `target: dev` で Vite dev server を起動。HMR + bind mount。
# Railway 等の本番: `target: prod` で build → nginx static 配信。
#
# `VITE_API_BASE` などの VITE_* 環境変数は Vite が build 時に dist に埋め込むため、
# prod build では --build-arg で渡す必要がある (Railway の build-time 変数で設定)。

# --- base: 依存解決 (dev と builder の共通土台) ---
FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# --- dev: Vite dev server (ローカル開発用) ---
FROM base AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- builder: 本番用 dist/ を生成 ---
FROM base AS builder
ARG VITE_API_BASE=""
ARG VITE_USE_MOCK="false"
ARG VITE_ALLOWED_HOSTS=""
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_USE_MOCK=${VITE_USE_MOCK}
ENV VITE_ALLOWED_HOSTS=${VITE_ALLOWED_HOSTS}
COPY . .
RUN npm run build

# --- prod: nginx で静的配信 ---
FROM nginx:alpine AS prod
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
