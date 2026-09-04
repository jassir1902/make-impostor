# Estrategia de Pruebas y Aseguramiento de Calidad (QA)

Este documento establece el marco estratégico, las herramientas oficiales y la taxonomía de pruebas automatizadas y manuales para asegurar la integridad, seguridad y correcto manejo de concurrencia en "El Impostor".

## 1. El Paradigma de Calidad: Pruebas como Código (Test-as-Code)

El proyecto rechaza la burocracia de los casos de prueba manuales documentados en plantillas externas. Se adopta la filosofía _Test-as-Code_: **el código de la prueba automatizada constituye su propia documentación técnica**. La suite de pruebas debe ser autoexplicativa, reproducible en cualquier entorno local y ejecutada de forma mandatoria en el pipeline de Integración Continua (CI).

## 2. La Pirámide de Pruebas del Proyecto

Para optimizar el tiempo de cómputo en el CI y maximizar la confianza en los despliegues, la estrategia se distribuye bajo una estructura piramidal ampliada:

### 2.1 Pruebas Unitarias (Backend - Pytest)

- **Objetivo:** Validar la lógica pura de negocio y las mutaciones de estado aisladas de la infraestructura.
- **Alcance:** Pruebas exhaustivas sobre `game_service.py` (cálculo de victorias, resolución de índices de turnos, y la lógica matemática de desempates).
- **Características:** No requieren conexiones reales a red ni a base de datos; utilizan _mocks_ de datos locales.

### 2.2 Pruebas de Integración Distribuidas (Pytest + Redis)

- **Objetivo:** Garantizar la atomicidad, el enrutamiento de _Redis Streams_ y la robustez frente a condiciones de carrera entre _múltiples workers_.
- **Entorno Multi-Instancia Obligatorio:** Las pruebas de integración en el CI no se ejecutan contra un solo proceso. El entorno de pruebas levantará **al menos dos contenedores de FastAPI** conectados al mismo contenedor de Redis. Se verificará explícitamente que un evento emitido al socket de la Instancia A sea consumido y transmitido (vía _stream broadcast_) a un socket conectado a la Instancia B.
- **Prueba de Compatibilidad Cluster (No Bloqueante):** En un _job_ separado del CI, la suite de integración correrá contra un **Redis en modo Cluster**. Esto garantiza que la convención de _Hash Tags_ (`room:{ABCD}:...`) esté correctamente implementada y captura cualquier error `CROSSSLOT` de operaciones multi-clave antes de la migración en la Fase 6.

### 2.3 Pruebas de Extremo a Extremo / End-to-End (Frontend - Playwright)

- **Objetivo:** Validar los flujos de experiencia de usuario (UX), el ciclo de vida de los WebSockets y la sincronización multi-jugador interactuando desde navegadores independientes.
- **Alcance:** Flujos críticos de interfaz, validación de renderizado seguro condicional (ocultación de palabras de impostores) y control de ciclos de conexión del singleton `RoomSocket`.

### 2.4 Pruebas de Carga y Rendimiento (k6)

- **Objetivo:** Validar el comportamiento de la infraestructura bajo concurrencia masiva (throughput, latencia y contención de cerrojos).
- **Alcance:** Se utilizará **k6** para simular ráfagas de WebSockets de cientos de salas en paralelo. Esta prueba no se ejecutará en cada PR, sino como un control de calidad pre-lanzamiento (Pre-Release) para medir si el VPS único puede sostener la latencia objetivo, y para calibrar los topes del limitador de tasa de mensajes.

## 3. Stack Tecnológico de QA

| Capa / Componente       | Herramienta Oficial | Razón Estratégica                                                                                                                                  |
| :---------------------- | :------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backend Framework**   | `pytest`            | Soporta nativamente pruebas asíncronas y orquestación multi-instancia en fixtures (`pytest-asyncio`).                                              |
| **Frontend Framework**  | `Playwright`        | Permite instanciar múltiples contextos de navegador (`BrowserContext`) en paralelo para simular Anfitriones e Impostores actuando simultáneamente. |
| **Rendimiento**         | `k6`                | Herramienta moderna basada en Go y scripting en JS, excelente para estrés de WebSockets.                                                           |
| **Validación de Tipos** | `mypy`              | Análisis estático estricto.                                                                                                                        |

## 4. Escenarios Críticos de Prueba Automática (Foco de Inversión)

### 4.1 Pruebas de Concurrencia y Competencia por Turno (Backend)

- **Caso:** Emitir un `send_word` y expirar forzosamente la clave `room:{ABCD}:timeout` exactamente en el mismo milisegundo, forzando la competencia por `room:{ABCD}:lock`.
- **Aserción:** Validar mediante el _script_ Lua que solo una mutación tenga éxito y que la otra sea abortada silenciosamente, previniendo dobles avances de turno.

### 4.2 Multi-Pestaña y Expulsión Definitiva (Ping-Pong Loop)

- **Caso:** Playwright abrirá dos pestañas (A y B) inyectando el mismo `secret_token` en `localStorage`. La Pestaña B se conectará después de la A.
- **Aserción:** Verificar que la Pestaña A sea expulsada por el servidor con el código `4009 (Session Duplicated)`. Validar crucialmente que la lógica del frontend en la Pestaña A **transicione a estado `rejected` y no intente reconectar**, confirmando la ausencia de un bucle infinito de expulsiones.

### 4.3 Pruebas de Resiliencia ante Corte de Red

- **Caso:** Forzar el cierre de un socket activo en fase de votación con el código de bajo nivel `1006` (caída de red) y reconectar tras 5 segundos.
- **Aserción:** Validar que el _backoff_ automático actúe, reenvíe el _handshake_ de identidad, y rehidrate el estado actual sin ejecutar intenciones obsoletas que quedaron en la cola.

### 4.4 Límite de Tasa (Rate Limiting 4029)

- **Caso:** Un _script_ enviará 10 intenciones de `vote` consecutivas en menos de 1 segundo a través de una conexión WebSocket legítima.
- **Aserción:** El servidor debe cerrar el socket con el código `4029`. Adicionalmente, verificar un "caso de uso rápido" (ej. votar e inmediatamente enviar un emoji en un futuro chat) para asegurar que el uso normal no detone falsos positivos.

## 5. Criterios de Aceptación y Políticas de Cobertura (Políticas de PR)

El pipeline en GitHub Actions aplicará reglas combinadas (Volumen + Riesgo):

1. **Bloqueo por Volumen (80%):** Ningún PR que modifique código será integrado si reduce la cobertura general por debajo del 80%.
2. **Lista Obligatoria de Riesgo (Concurrency Checklist):** Alcanzar el 80% de cobertura sobre código trivial no es suficiente. Cualquier PR que modifique `game_service.py`, `redis_client.py` o `websockets.py` será bloqueado a menos que la ejecución del CI demuestre que **los escenarios de concurrencia y cerrojo multi-instancia (Secciones 4.1 y 4.4) se ejecutaron y pasaron exitosamente**.
3. **Inmutabilidad:** Si una prueba falla, el botón de _Merge_ queda deshabilitado (Status Checks estrictos).
4. **Casos Terminales:** Todo nuevo evento agregado al contrato de red debe implementar pruebas tanto para su _Happy Path_ como para sus códigos de error designados en el documento de Arquitectura de Eventos.
