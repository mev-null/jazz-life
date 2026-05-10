FROM node:20-alpine

WORKDIR /app

# 依存解決を先に：package.json と lockfile を先にコピーしてレイヤキャッシュを効かせる
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# アプリ本体
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
