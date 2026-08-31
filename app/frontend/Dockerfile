# Multi-stage build for both dev and prod.
#
# Local (docker-compose): `target: dev` runs the Vite dev server. HMR + bind mount.
# Production (Railway etc.): `target: prod` builds and serves the static files via nginx.
#
# Vite embeds VITE_* env vars such as `VITE_API_BASE` into dist at build time, so the
# prod build must receive them via --build-arg (set as Railway build-time variables).

# --- base: dependency install (shared by dev and builder) ---
FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# --- dev: Vite dev server (local development) ---
FROM base AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- builder: produce the production dist/ ---
FROM base AS builder
ARG VITE_API_BASE=""
ARG VITE_USE_MOCK="false"
ARG VITE_ALLOWED_HOSTS=""
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_USE_MOCK=${VITE_USE_MOCK}
ENV VITE_ALLOWED_HOSTS=${VITE_ALLOWED_HOSTS}
COPY . .
RUN npm run build

# --- prod: nginx serves static files + reverse-proxies /api to the backend ---
# Pinned to nginx:1.27-alpine to guarantee a version that ships the built-in
# /docker-entrypoint.d/15-local-resolvers.envsh (builds NGINX_LOCAL_RESOLVERS from
# /etc/resolv.conf and exports it). The bare alpine tag could change behaviour on a
# minor bump.
FROM nginx:1.27-alpine AS prod
COPY --from=builder /app/dist /usr/share/nginx/html
# The default nginx:alpine entrypoint expands /etc/nginx/templates/*.template with
# envsubst and writes the result to /etc/nginx/conf.d/. Only ${PORT} and the backend
# internal address go through envsubst; the resolver is patched separately by
# 25-patch-resolver.sh with sed. (An earlier approach that expanded
# ${NGINX_LOCAL_RESOLVERS} via envsubst failed twice on Railway; the root cause was
# never pinned down, so it was taken out of envsubst.)
COPY nginx.conf /etc/nginx/templates/default.conf.template
# --chmod=755 guarantees the execute bit (does not rely on git's +x bit).
COPY --chmod=755 docker-entrypoint.d/25-patch-resolver.sh /docker-entrypoint.d/25-patch-resolver.sh
ENV PORT=80
# On Railway, BACKEND_INTERNAL_HOST=backend.railway.internal and _PORT=8080 are set
# via service variables. The defaults target local docker-compose (backend:8000).
ENV BACKEND_INTERNAL_HOST=backend
ENV BACKEND_INTERNAL_PORT=8000
# The trailing $ in NGINX_ENVSUBST_FILTER must be escaped as \$ because BuildKit may
# read it as the start of a variable. Without quoting/escaping it on this ENV line the
# regex anchor is lost and extra env vars such as PORT_X get picked up by envsubst.
ENV NGINX_ENVSUBST_FILTER=^(PORT|BACKEND_INTERNAL_HOST|BACKEND_INTERNAL_PORT)\$
EXPOSE 80
# CMD is left to the nginx:alpine default (envsubst -> nginx)
