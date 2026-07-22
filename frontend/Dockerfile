# syntax=docker/dockerfile:1

FROM node:22-alpine AS builder
WORKDIR /app

COPY package*.json .npmrc ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.31.3-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.d/40-attenly-runtime-config.sh
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/node_modules/tinymce /usr/share/nginx/html/tinymce

RUN sed -i 's/\r$//' /docker-entrypoint.d/40-attenly-runtime-config.sh \
 && chmod +x /docker-entrypoint.d/40-attenly-runtime-config.sh

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/health || exit 1
