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
# nginx:1.27-alpine で固定。組み込み /docker-entrypoint.d/15-local-resolvers.envsh
# (/etc/resolv.conf から NGINX_LOCAL_RESOLVERS を組み立てて export) を確実に含む
# バージョンを保証する。alpine タグだと minor 更新で挙動が変わるリスクがある。
FROM nginx:1.27-alpine AS prod
COPY --from=builder /app/dist /usr/share/nginx/html
# nginx:alpine の既定 entrypoint が /etc/nginx/templates/*.template を envsubst で
# 展開してから /etc/nginx/conf.d/ に書き出す。${PORT} と backend 内部接続先のみを
# envsubst で展開し、resolver は別途 25-patch-resolver.sh が sed 置換する。
# (PR #20 / #21 で envsubst 経由の ${NGINX_LOCAL_RESOLVERS} 展開が動かず 2 回事故
# 発生。原因が確定できないので envsubst から外す。)
COPY nginx.conf /etc/nginx/templates/default.conf.template
# --chmod=755 で実行権限を確実に付与 (git の +x bit に依らない)。
COPY --chmod=755 docker-entrypoint.d/25-patch-resolver.sh /docker-entrypoint.d/25-patch-resolver.sh
ENV PORT=80
# Railway 環境では BACKEND_INTERNAL_HOST=backend.railway.internal, _PORT=8080 を
# service 変数で上書きする。デフォルトはローカル docker-compose 用 (backend:8000)。
ENV BACKEND_INTERNAL_HOST=backend
ENV BACKEND_INTERNAL_PORT=8000
# NGINX_ENVSUBST_FILTER の末尾 $ は BuildKit が変数開始記号として誤認しうるため
# \$ で escape する。Dockerfile のこの ENV 行で末尾を quote / escape しないと
# regex anchor が脱落して PORT_X など余計な env まで envsubst の対象になる。
ENV NGINX_ENVSUBST_FILTER=^(PORT|BACKEND_INTERNAL_HOST|BACKEND_INTERNAL_PORT)\$
EXPOSE 80
# CMD は nginx:alpine 既定 (envsubst → nginx) に任せる
