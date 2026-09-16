# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=22-alpine
ARG NGINX_VERSION=1.28-alpine

FROM node:${NODE_VERSION} AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY public ./public
COPY src ./src
COPY babel.config.cjs tsconfig.json webpack.config.cjs ./

ARG API_BASE_URL=""
ENV API_BASE_URL=${API_BASE_URL}

RUN npm run build

FROM nginxinc/nginx-unprivileged:${NGINX_VERSION} AS runtime

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder --chown=101:101 /build/dist /usr/share/nginx/html

USER 101

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/"]
