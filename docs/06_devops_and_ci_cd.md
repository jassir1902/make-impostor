# DevOps, CI/CD y Estrategia de Despliegue

Este documento define las prácticas de Integración Continua y Despliegue Continuo (CI/CD), la gestión del código fuente, y la topología de la infraestructura para el entorno de producción de "El Impostor".

## 1. Topología de Infraestructura (Fase 1 - 4)

El entorno de producción reside en una única instancia virtual (VPS) de Oracle Cloud bajo la arquitectura ARM64, gestionada íntegramente mediante la filosofía de Infraestructura como Código (IaC) utilizando Docker Compose.

### 1.1 Orquestación de Servicios (Docker Compose)

El archivo `docker-compose.yml` de producción define los siguientes servicios aislados en una red interna virtual:

- **`api` (FastAPI):** Construido a partir de un `Dockerfile` Multi-Etapa optimizado para `linux/arm64`. La imagen de producción excluye dependencias de desarrollo (`pytest`, `black`) para minimizar la superficie de ataque y el peso del contenedor.
- **`redis`:** Contenedor oficial de Redis (Alpine), ejecutado con persistencia activada (`--appendonly yes --appendfsync everysec`) y un volumen montado en el _host_ para preservar el estado ante reinicios.
- **`proxy` (Caddy):** Servidor web expuesto a internet (Puertos 80 y 443).

**Nota de Compatibilidad de Esquemas:** Dado que Redis preserva el estado, si un despliegue introduce un cambio que rompe la retrocompatibilidad del modelo Pydantic `GameRoom` (ej. renombrar un campo obligatorio), el nuevo contenedor fallará al intentar deserializar las partidas en curso. Los cambios destructivos de esquema deben manejarse haciendo los campos opcionales inicialmente, o programando el despliegue en ventanas de mantenimiento sin partidas activas.

### 1.2 Proxy Inverso y Terminación SSL (Caddy)

Caddy actúa como el único punto de entrada público. Sus responsabilidades exclusivas son:

- Resolver automáticamente la emisión y renovación de certificados TLS vía Let's Encrypt.
- Redirigir el tráfico HTTP a HTTPS de forma automática.
- Interceptar las conexiones seguras y enrutarlas internamente al puerto expuesto por el contenedor de FastAPI, facilitando tanto el tráfico REST (`https://`) como la mejora (_upgrade_) a WebSockets (`wss://`).

## 2. Gestión del Código Fuente (Git Flow Simplificado)

Para mantener el rigor en un entorno de desarrollo individual, se adopta un modelo de ramas (branching) estricto que emula un entorno de equipo corporativo.

- **`main`:** Rama de producción. El código aquí es inmutable, está 100% probado y coincide exactamente con lo que se está ejecutando en el servidor VPS. Nunca se sube código directamente a esta rama.
- **`develop`:** Rama de integración. Contiene el código listo para la siguiente versión.
- **Ramas Efímeras (Trabajo diario):**
  - `feature/*`: Para nuevas funcionalidades (ej. `feature/websocket-auth`).
  - `fix/*`: Para corregir errores en desarrollo o producción.
  - `test/*`: Para aislar la escritura de pruebas automatizadas.
  - `ops/*`: Para actualizaciones de infraestructura, Dockerfiles o flujos de GitHub Actions.

## 3. Convención de Commits (Semantic Commits)

El historial de Git debe ser autoexplicativo y legible por máquinas para posibles automatizaciones de versionado (SemVer). Todo commit debe seguir la convención:
`<tipo>(<alcance>): <descripción breve>`

**Tipos permitidos:**

- `feat`: Nueva funcionalidad.
- `fix`: Corrección de un error.
- `chore`: Tareas de mantenimiento, actualización de dependencias.
- `docs`: Cambios exclusivos en la documentación.
- `ci`: Modificaciones en pipelines o scripts de despliegue.
- `test`: Adición o modificación de pruebas.

_Ejemplo:_ `feat(socket): implementar rehidratación de estado en reconexión`

## 4. Pipeline de Integración y Despliegue (GitHub Actions)

La automatización de la calidad y la entrega se delega a GitHub Actions, dividido en flujos de trabajo principales:

### 4.1 Flujo de Integración Continua (CI)

**Gatillo:** Creación o actualización de un _Pull Request_ hacia las ramas `develop` y `main`.
**Pasos:**

1. Inicializar el entorno de Python.
2. Ejecutar linters y formateadores (`flake8`, `black`) para garantizar el estilo del código.
3. Analizar tipado estático con `mypy`.
4. Levantar un entorno de pruebas efímero (incluyendo Redis local) y ejecutar la suite completa de pruebas unitarias y de integración mediante `pytest`.
5. **Prueba de Compilación (_Dry-Run_):** Ejecutar `docker buildx build` para la arquitectura `linux/arm64` sin hacer _push_. Esto garantiza que no haya errores de dependencias incompatibles con ARM antes de llegar a producción.
   _Bloqueo:_ El PR no puede ser fusionado (_merged_) si alguno de estos pasos falla.

### 4.2 Flujo de Despliegue Continuo (CD)

**Gatillo:** Cierre de un _Pull Request_ (Merge) hacia la rama `main`.
**Pasos:**

1. Hacer _checkout_ del código validado.
2. Configurar QEMU y Docker Buildx para permitir la compilación multiplataforma.
3. Compilar la imagen de Docker para la arquitectura objetivo (`linux/arm64`).
4. Autenticarse nativamente utilizando `GITHUB_TOKEN` y subir (_push_) la imagen al **GitHub Container Registry (GHCR)**. La imagen se etiqueta explícitamente con `latest` y con el **SHA del commit** (`${{ github.sha }}`) para permitir versionado.
5. **Conexión Segura Restringida:** Iniciar conexión SSH hacia el VPS. Por seguridad, la clave inyectada en el _runner_ no tiene acceso de consola libre. Se conecta mediante un usuario sin privilegios de _root_, y la clave pública en `~/.ssh/authorized_keys` del servidor VPS utiliza el prefijo `command="..."` para limitar su ejecución única y exclusivamente al _script_ de despliegue.
6. Ejecutar el _script_ remoto que descarga la imagen (`docker compose pull`) y reinicia los contenedores (`docker compose up -d`).
   - **Expectativa de Disponibilidad:** Este comando detiene el contenedor viejo antes de levantar el nuevo. Esto provoca un corte abrupto de todos los WebSockets activos. El sistema asimila esto como una degradación breve: la arquitectura de rehidratación del frontend reconectará automáticamente a todos los jugadores y restaurará el estado desde Redis de forma transparente.

### 4.3 Estrategia de Rollback

Ante un despliegue defectuoso en `main`, la reversión no requiere ejecutar todo el pipeline de CI/CD de nuevo. Se accede al VPS y se edita el `docker-compose.yml` para apuntar el tag de la imagen al SHA del commit anterior y estable (ej. `ghcr.io/.../api:a1b2c3d`), ejecutando nuevamente `docker compose up -d`.

## 5. Estrategia de Monitoreo

Para garantizar la visibilidad operativa sin incurrir en costos de infraestructura adicionales en la Fase 1, se implementará **Uptime Kuma** (desplegado como un contenedor de bajo consumo adicional en el VPS).

- **Verificación de Salud:** Uptime Kuma enviará pulsos (_pings_) periódicos al endpoint `/api/rooms/health` para validar que FastAPI y Redis están comunicándose correctamente.
- **Alertas:** En caso de que el backend o el proxy inverso rechacen la conexión, se disparará una alerta automatizada a través de un _webhook_ (ej. hacia un bot de Telegram o un canal de Discord privado) para asegurar una respuesta proactiva ante caídas.
