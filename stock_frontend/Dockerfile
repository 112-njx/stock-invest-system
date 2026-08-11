# ---------- 阶段一：构建（node → dist） ----------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- 阶段二：Nginx 托管静态 + 反向代理 /api ----------
FROM nginx:1.27-alpine
# 静态资源
COPY --from=build /app/dist /usr/share/nginx/html
# Nginx 配置模板：容器启动时经官方 envsubst 注入后端上游地址
COPY nginx.conf /etc/nginx/templates/default.conf.template
# 后端 API 上游地址（docker-compose / 运行时 environment 覆盖）
ENV NGINX_PROXY_PASS=http://host.docker.internal:8000
EXPOSE 80
