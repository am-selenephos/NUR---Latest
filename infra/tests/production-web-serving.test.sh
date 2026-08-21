#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="$ROOT/apps/web/Dockerfile"
NGINX_CONFIG="$ROOT/apps/web/nginx.conf"
COMPOSE="$ROOT/docker-compose.yml"

[[ -f "$NGINX_CONFIG" ]]

grep -Fq 'RUN npm ci' "$DOCKERFILE"
grep -Fq 'RUN npm run build --workspace apps/web' "$DOCKERFILE"
grep -Eq '^FROM nginx:[^[:space:]]+ AS runtime$' "$DOCKERFILE"
grep -Fq 'RUN rm -rf /usr/share/nginx/html/*' "$DOCKERFILE"
grep -Fq 'COPY --from=build /srv/nur/apps/web/dist/ /usr/share/nginx/html/' "$DOCKERFILE"

grep -Fq 'listen 5173;' "$NGINX_CONFIG"
grep -Fq 'absolute_redirect off;' "$NGINX_CONFIG"
grep -Fq 'try_files $uri $uri/ /index.html;' "$NGINX_CONFIG"
grep -Fq 'proxy_pass http://api:8000;' "$NGINX_CONFIG"
grep -Fq 'proxy_set_header X-Forwarded-Proto $scheme;' "$NGINX_CONFIG"
grep -Fq 'proxy_buffering off;' "$NGINX_CONFIG"
grep -Fq 'location ~ ^/(healthz|readyz|metrics)$' "$NGINX_CONFIG"
grep -Fq 'proxy_pass http://api:8000$request_uri;' "$NGINX_CONFIG"
grep -Fq 'location ~ ^/universe/(research|experts|web-signals)(/|$)' "$NGINX_CONFIG"
grep -Fq 'return 302 /systems;' "$NGINX_CONFIG"
grep -Fq 'location ~ ^/community/(people|saved|notifications|moderation)$' "$NGINX_CONFIG"
grep -Fq 'return 302 /universe/community;' "$NGINX_CONFIG"

! grep -Fq 'npm", "run", "dev' "$DOCKERFILE"
! grep -Fq 'npm", "run", "dev' "$COMPOSE"

printf 'production web serving contract passed.\n'
