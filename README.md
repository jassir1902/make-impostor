# El Impostor — Arranque local

## Backend + Redis (Docker Compose)

```bash
docker compose up --build
```

Esto levanta:

- `redis` en el puerto `6379`, con AOF y `notify-keyspace-events Ex` ya
  configurados (ver `docker-compose.yml`).
- `api` (FastAPI) en `http://localhost:8000`, conectado a `redis` por la
  red interna del compose.

Verificar que quedó arriba:

```bash
curl http://localhost:8000/api/health
# {"status": "ok", "redis": "connected"}
```

## Frontend (Next.js, sin Docker)

El frontend **no** corre en contenedor — se despliega en Vercel, que
nunca usa un Dockerfile, y en desarrollo el *hot-reload* de Next.js
dentro de Docker es más lento y menos confiable sin configurar
*polling* explícito. Se corre directo en la máquina:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Con el backend arriba (`docker compose up`) y el frontend en
`http://localhost:3000`, `.env.local` ya apunta al backend correcto por
defecto (`NEXT_PUBLIC_API_URL=http://localhost:8000`,
`NEXT_PUBLIC_WS_URL=ws://localhost:8000`).

## Notas

- `docker-compose.yml` es la misma topología (`api` + `redis`) que se
  usará en el VPS de producción (ver `06_devops_and_ci_cd.md`) — el
  Dockerfile del backend sí es el mismo artefacto real, a diferencia
  del frontend.
- Si cambias el puerto de `redis` o `api` en `docker-compose.yml`,
  actualiza también `.env.local` del frontend.
