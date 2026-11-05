FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# empty = call the api on the same origin, through the gateway
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build


# nginx serves the app and is the gateway to the api
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY gateway/*.template /etc/nginx/templates/
COPY gateway/security-headers.inc /etc/nginx/snippets/

# filled into the templates at start; override per environment
ENV API_UPSTREAM=http://api:8000 \
    RESOLVER=127.0.0.11 \
    GATEWAY_TOKEN="" \
    MAX_BODY_SIZE=51m \
    TRUSTED_PROXIES=127.0.0.1 \
    TRUSTED_PROXIES_V6=::1 \
    REAL_IP_HEADER=X-Real-IP \
    NGINX_ENVSUBST_FILTER="^(API_UPSTREAM|RESOLVER|GATEWAY_TOKEN|MAX_BODY_SIZE|TRUSTED_PROXIES|TRUSTED_PROXIES_V6|REAL_IP_HEADER)$"

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz || exit 1
