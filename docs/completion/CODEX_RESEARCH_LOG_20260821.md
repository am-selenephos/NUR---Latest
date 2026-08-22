# NUR Research Log - 2026-08-21

This log records only decisions that depended on current external guidance.
Repository facts and test results live in the closure ledger and test evidence
index.

| Question | Source | Date checked | Source class | Finding | Decision affected |
| --- | --- | --- | --- | --- | --- |
| Can Vite preview be the production web server? | [Vite static deployment guide](https://vite.dev/guide/static-deploy.html) | 2026-08-21 | Official | `vite build` produces the deployable static output; `vite preview` is for local preview and is not a production server. | Replaced the web runtime image with an Nginx static stage and retained Vite only in the build stage. |
| How should static NUR routes fall back to the canonical host document? | [Nginx `try_files` directive](https://nginx.org/en/docs/http/ngx_http_core_module.html#try_files) | 2026-08-21 | Official | `try_files` can check static paths in order and internally redirect to a final URI. | Native V197 routes fall back to generated `/index.html` without introducing a React shell. |
| How should the same-origin API be forwarded? | [Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) | 2026-08-21 | Official | `proxy_pass` and explicit forwarded headers preserve the public request boundary; buffering can be disabled for streaming responses. | `/api/`, health, readiness, and metrics proxy to FastAPI; Talk streaming has proxy buffering disabled. |
| What proxy trust boundary does FastAPI expect? | [FastAPI behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) | 2026-08-21 | Official | Forwarded headers describe the original public request, but the application must trust only its known proxy boundary. | Nginx sets host/proto/client forwarding headers while FastAPI remains the application trust boundary. |

## Local infrastructure note

The workstation Docker daemon could not resolve `registry.npmjs.org` through
its default build network (`EAI_AGAIN`). A one-time local image build used
`docker build --network host`; no host-network mode was added to the committed
runtime or Compose topology.
