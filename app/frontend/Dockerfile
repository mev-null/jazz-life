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

# --- prod: nginx で静的配信 + /api を backend に reverse proxy ---
FROM nginx:alpine AS prod
COPY --from=builder /app/dist /usr/share/nginx/html
# nginx:alpine の既定 entrypoint が /etc/nginx/templates/*.template を envsubst で
# 展開してから /etc/nginx/conf.d/ に書き出す。${PORT} と backend 内部接続先と
# ${NGINX_LOCAL_RESOLVERS} を実値に差し替える。NGINX_ENVSUBST_FILTER で展開対象を
# 限定し、nginx 内部変数 ($uri など) を保護する。
#
# NGINX_LOCAL_RESOLVERS は nginx:alpine 同梱の /docker-entrypoint.d/15-local-resolvers.envsh
# が /etc/resolv.conf からスペース区切り (IPv6 は [..] 付き) で組み立てて export する。
# 自分でフォールバック script を書く必要は無い (1.27+ で組み込み)。
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV PORT=80
# Railway 環境では BACKEND_INTERNAL_HOST=backend.railway.internal, _PORT=8080 を
# service 変数で上書きする。デフォルトはローカル docker-compose 用 (backend:8000)。
ENV BACKEND_INTERNAL_HOST=backend
ENV BACKEND_INTERNAL_PORT=8000
ENV NGINX_ENVSUBST_FILTER=^(PORT|BACKEND_INTERNAL_HOST|BACKEND_INTERNAL_PORT|NGINX_LOCAL_RESOLVERS)$
EXPOSE 80
# CMD は nginx:alpine 既定 (envsubst → nginx) に任せる
