FROM node:22-slim AS build
WORKDIR /srv/nur
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/shared-types/package.json ./packages/shared-types/
RUN npm ci
COPY packages/shared-types ./packages/shared-types
COPY apps/web ./apps/web
ARG VITE_NUR_ENABLE_OMEGA_RESEARCH=true
ENV VITE_NUR_ENABLE_OMEGA_RESEARCH=${VITE_NUR_ENABLE_OMEGA_RESEARCH}
RUN npm run build --workspace apps/web

FROM nginx:1.30.4-alpine AS runtime
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -rf /usr/share/nginx/html/*
COPY --from=build /srv/nur/apps/web/dist/ /usr/share/nginx/html/
EXPOSE 5173
HEALTHCHECK --interval=10s --timeout=3s --retries=12 \
  CMD wget -q -O /dev/null http://127.0.0.1:5173/ || exit 1
