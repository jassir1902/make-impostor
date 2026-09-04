# Estado actual

**Última actualización: 2026-09-04**

Este es el primer archivo que hay que leer al volver al proyecto. El resto de
`docs/` describe cómo **debería** comportarse el sistema; este describe cómo se
comporta **hoy**.

Se actualiza en todo commit que cambie qué funciona (`AGENTS.md` §7). Un
documento de estado desactualizado es peor que no tenerlo, porque se le cree.

---

## En una línea

El juego está escrito de punta a punta y las pruebas pasan, pero **nunca se ha
jugado una partida real** con backend y frontend corriendo juntos, y hay
defectos conocidos que cuelgan partidas. No hay nada desplegado.

---

## Qué funciona

- **Lógica de juego** (`backend/app/services/game_service.py`): reparto de
  roles, orden de turnos, empates y doble empate, condiciones de victoria,
  puntaje efímero, migración de Host. Cubierta por 35 pruebas unitarias.
- **Ciclo de vida del cerrojo distribuido**: adquisición, escritura y
  liberación, todas con *fencing*. Cubierto por 10 pruebas con doble de Redis.
- **Frontend completo**: las cuatro pantallas (lobby, turnos, votación,
  resumen) y las dos páginas de Next.js. `tsc --noEmit` limpio.
- **Arranque local**: `docker compose` levanta `api` + `redis` con AOF y
  `notify-keyspace-events Ex`.
- **Control de versiones**: repositorio publicado en
  `github.com/jassir1902/make-impostor` (público).

Suite completa: **45 pruebas en verde** (`python -m pytest -q`).

## Qué está roto

Hallazgos de la auditoría del 2026-09-04. Los dos primeros ya se arreglaron.

### Cuelgan una partida

| # | Defecto | Estado |
|---|---|---|
| 1 | El cerrojo se fugaba en los 17 caminos de salida, y la liberación no comprobaba el token | ✅ MI-2 |
| 4 | La fase `voting` no tiene reloj: un jugador vivo que se desconecta sin salir la congela para siempre | 📋 **Bloqueado por decisión de negocio** |
| 5 | `leave_room` durante `voting` no vuelve a evaluar el umbral de votos, y el voto de quien se fue sigue contando | 📋 Pendiente |

### Rompen el juego o filtran información

| # | Defecto | Estado |
|---|---|---|
| 3 | `GET /api/topics/official` devuelve el vocabulario completo con pistas. Cualquier jugador, incluido el impostor, puede leerlo | 📋 Pendiente |
| 7 | `Topic.id` es un `uuid4()` que se regenera en cada arranque: tras un redeploy, `start_game` responde `TOPIC_NOT_FOUND` y el filtro anti-repetición queda apuntando a ids muertos | 📋 Pendiente |
| 2 | Ninguna sala se destruye nunca: `SET` sin `EX`, sin recolector, `join_order` sin limpiar. Fuga no acotada tras un endpoint público sin rate limiting | 📋 Pendiente |
| 6 | El backend emite `SERVER_BUSY` e `INVALID_FORMAT`; el enum de Zod no los tiene, así que el mensaje se descarta y el usuario ve un botón que no responde | 📋 Pendiente |
| 11 | `turn_deadline` no se rearma al abrir ronda nueva: en el primer turno de cada ronda a partir de la 2ª no se ve cuenta regresiva, pero la penalización sí ocurre | 📋 Pendiente |

### Menores

| # | Defecto | Estado |
|---|---|---|
| 8 | `anonymous_voting` se acepta, se persiste y nunca se lee. `RoomView` no expone `votes` en ningún modo | 📋 Pendiente |
| 9 | Nada impide arrancar con `--workers 4`, lo que rompe el broadcast en silencio | 📋 Pendiente |
| 12 | `start_game` cuenta jugadores desconectados, contra `01` §4 | 📋 Pendiente |
| 13 | `backend/dockerignore` sin el punto inicial: no ignora nada | 📋 Pendiente |

### En la documentación

- `06` §5 dice que el health check es `/api/rooms/health`; el real es
  `/api/health`, y `03` §1.4 lo dice bien. Dos documentos se contradicen.
- `03` §4.3 describe un TTL de salas y una gracia de 15 minutos que no existen.
- `03` §4.2 declara un «enum de lista cerrada» al que le faltan dos códigos.
- `01` §5 no define qué pasa si un jugador vivo no vota.

## Qué no existe todavía

- **Despliegue.** No hay VPS, ni Caddy, ni dominio. `06` describe la topología
  completa como si existiera.
- **CI/CD.** No hay `.github/workflows/`. Todo `06` §4 es aspiracional.
- **Pruebas de integración y E2E.** `tests/integration/` y `tests/e2e/` están
  vacías. Ninguna prueba toca un Redis real ni un navegador; la política de
  cobertura de `07` §5 no se está aplicando.
- **Partida de humo.** Nadie ha jugado una partida completa de verdad.
- **Fases 2 a 6.** Ver `04_roadmap_and_phases.md`.

## Decisiones pendientes

**Qué pasa cuando un jugador vivo no vota** (hallazgo 4). Es una regla ausente
en `01` §5, no solo un bug. Las dos salidas razonables:

- *Deadline de votación con abstención automática*, simétrico con el reloj de
  turno. Más trabajo, resuelve el caso de raíz.
- *Contar solo a los votantes con `is_online: true`*. Más barato, pero el
  problema reaparece en cuanto alguien abandona sin cerrar sesión.

Hasta decidirlo no se puede implementar ni el hallazgo 4 ni el 5.

## Siguiente paso

1. Decidir la regla de votación de arriba.
2. Hallazgos 4 y 5 juntos, con la regla ya documentada en `01`.
3. Hallazgos 3, 6 y 7 (contrato y filtración): baratos y de riesgo bajo.
4. Hallazgo 2 (ciclo de vida de las salas).
5. Pruebas de integración contra un Redis real (`07` §4.1), que es lo que
   habría atrapado casi todo lo anterior.
6. Recién entonces, la partida de humo y el bloque de DevOps de la Fase 1.
