# 0001 — Cerrojo distribuido con fencing como autoridad de escritura

- **Estado:** Aceptado
- **Fecha:** 2026-09-04
- **Relacionado:** MI-2, `docs/02_architecture.md` §4.3, `docs/04_roadmap_and_phases.md` (Fase 1), `docs/07_testing_and_qa_strategy.md` §4.1

> ADR rescatado. La decisión se tomó al construir la Fase 1 y nunca se
> registró; se documenta ahora, al arreglar dos defectos derivados de ella
> (MI-2). Se escribe con el contexto de entonces, no con el de hoy.

## Contexto

El estado de una sala vive en Redis como un único blob JSON en
`room:{ABCD}:state`. Todo cambio es un ciclo leer → deserializar → mutar →
serializar → escribir. Ese ciclo **no es atómico**: entre la lectura y la
escritura hay `await`s.

Sobre ese mismo estado hay dos escritores que no se coordinan entre sí:

1. **La acción del jugador.** Llega por WebSocket y la procesa el *event loop*
   de `asyncio`.
2. **La expiración del turno.** No la dispara el servidor: la dispara Redis. Al
   empezar un turno se crea `room:{ABCD}:timeout:{ronda}:{índice}` con TTL de
   20 s, y al expirar Redis emite una *keyspace notification* que despierta al
   listener del backend.

Estos dos pueden ocurrir en el mismo milisegundo: el jugador envía su palabra
justo cuando su tiempo se acaba. Sin coordinación, ambos leen el mismo estado,
ambos avanzan el turno, y el turno avanza **dos veces** — saltándose a un
jugador que nunca llega a hablar.

El punto que más se malinterpreta: **esto no requiere varios procesos.** Con un
único worker de FastAPI, la acción del jugador y la notificación de Redis son
dos corrutinas del mismo *event loop* compitiendo por el mismo estado. El
problema es de concurrencia, no de distribución. Por eso esta pieza es una
dependencia dura del MVP jugable y no una preparación para la Fase 5.

## Alternativas consideradas

### `asyncio.Lock` en memoria del proceso

Lo más simple y lo que resuelve el caso de hoy: un diccionario de cerrojos por
`room_id` dentro del proceso.

- **A favor:** cero latencia, cero dependencia de Redis, trivial de probar.
- **En contra:** deja de funcionar en cuanto haya un segundo worker, y lo hace
  **en silencio**. No hay error, no hay log: simplemente dos procesos escriben
  encima del otro. Y el salto a dos workers es un cambio de una palabra en el
  `CMD` del Dockerfile. Un mecanismo cuya corrección depende de que nadie toque
  una línea de configuración es una trampa, no una solución.

### Concurrencia optimista con `WATCH` / `MULTI`

Redis ofrece transacciones optimistas: se vigila la clave, y si cambió entre el
`WATCH` y el `EXEC`, la transacción se aborta y se reintenta.

- **A favor:** sin cerrojos, sin riesgo de retención, sin TTL que calibrar.
- **En contra:** obliga a que toda la lógica de negocio sea **reintentable**, y
  buena parte de la nuestra tiene efectos colaterales fuera de la clave vigilada
  — armar el TTL del siguiente turno, emitir el broadcast. Un reintento
  duplicaría esos efectos. Reestructurar `game_service` para que fuera
  idempotente de punta a punta era más trabajo y más superficie de error que un
  cerrojo.

### Un único script Lua que haga todo el ciclo

Redis ejecuta Lua de forma atómica. Meter leer-mutar-escribir dentro de un
script elimina la ventana de carrera de raíz, sin cerrojo alguno.

- **A favor:** atomicidad real, imposible de usar mal.
- **En contra:** obliga a reescribir toda la lógica del juego en Lua. Sería una
  segunda implementación de las reglas, en un lenguaje sin tipado, sin Pydantic
  y sin pruebas cómodas, condenada a divergir de `game_service.py`. El costo de
  mantenimiento supera con mucho el beneficio a esta escala.

### Cerrojo distribuido con *fencing token* (elegida)

`SET room:{ABCD}:lock <UUID> NX PX 5000` para adquirir, y un script Lua que
comprueba el UUID antes de escribir o liberar.

## Decisión

Se adopta el cerrojo distribuido con *fencing total*:

1. **Adquisición:** `SET <lock> <UUID-del-worker> NX PX 5000`. El `NX` hace que
   solo uno gane; el `PX` garantiza que un worker que muera no deje la sala
   bloqueada para siempre.
2. **Escritura:** un script Lua comprueba que el valor del cerrojo siga siendo
   nuestro UUID; si coincide, escribe el estado y borra el cerrojo, todo
   atómicamente. Si no, aborta y no escribe nada.
3. **Liberación sin escritura:** el mismo chequeo de token, solo que borrando.
4. **Límite de sección crítica:** 5 s, y queda prohibido hacer I/O externo
   bloqueante dentro (por ejemplo, llamar al LLM de la Fase 3).

El criterio que decidió: es el único que sigue siendo correcto si mañana hay
dos workers, sin duplicar la lógica de negocio en otro lenguaje.

## Consecuencias

**Lo que se gana.** La corrección no depende del número de procesos. La carrera
turno-vs-timeout se resuelve de forma determinista: uno gana, el otro aborta en
silencio, y `resolve_turn_timeout` distingue una notificación vigente de una
obsoleta comparando ronda e índice de turno.

**Lo que se pierde.** Toda acción sobre una sala se serializa, incluidas las que
no mutan nada. Y aparece una clase de error nueva: la contención. Cuando un
worker no logra adquirir el cerrojo tras sus reintentos, hay que decidir qué
hacer, y la respuesta **no es la misma** para un jugador (se le avisa con
`SERVER_BUSY`) que para el temporizador (hay que rearmar su reloj, porque su
notificación no se repite).

**Lo que queda vigilado.** Este diseño tiene dos trampas, y el proyecto cayó en
ambas:

- *Liberar el cerrojo en todos los caminos de salida.* La sección crítica del
  endpoint tenía trece `continue` de rechazo y tres `break` de cierre que
  salían sin soltarlo, dejándolo retenido los 5 s completos. Corregido con un
  `finally`. **La liberación va en un `finally`, nunca al final del camino
  feliz.**
- *No perder un evento que solo se entrega una vez.* La notificación de
  keyspace llega una sola vez y su clave ya expiró; si el handler se rendía al
  no conseguir el cerrojo, ese turno quedaba sin reloj para siempre. Corregido
  rearmando el TTL. Ambos arreglos van en MI-2.

**Pendiente.** La prueba que fuerza la colisión real contra un Redis de verdad
(`07_testing_and_qa_strategy.md` §4.1) sigue sin escribirse. Las pruebas
actuales usan un doble que no simula expiración por TTL: demuestran que el
código libera el cerrojo, no que Redis se comporte como suponemos.

## Nota de aprendizaje

**Por qué un TTL no basta y hace falta un token.**

La tentación es pensar que `SET NX PX 5000` ya resuelve todo: uno gana, y si
muere, el TTL limpia. El agujero está en el caso intermedio — el worker no
muere, solo se pone **lento**.

```
t=0.0s   Worker A: SET lock=A NX PX 5000   → gana, lee el estado
t=0.1s   Worker A: se queda esperando (GC, disco, red...)
t=5.0s   Redis: el TTL expira, la clave lock desaparece
t=5.1s   Worker B: SET lock=B NX PX 5000   → gana, lee, muta, escribe
t=5.2s   Worker A: despierta, cree que sigue teniendo el cerrojo,
                   y escribe el estado que leyó en t=0.0s
```

A pisa el trabajo de B con datos de hace cinco segundos. El cerrojo hizo su
trabajo y aun así el estado quedó corrupto: **A no tenía forma de saber que
había dejado de ser el dueño.**

El *fencing token* cierra eso. El UUID que A guardó es su prueba de propiedad, y
la escritura la valida contra Redis en el mismo paso atómico:

```lua
if redis.call("get", KEYS[1]) == ARGV[1] then   -- ¿el cerrojo sigue siendo mío?
    redis.call("set", KEYS[2], ARGV[2])          -- entonces escribo
    return redis.call("del", KEYS[1])            -- y lo suelto
else
    return 0                                      -- llegué tarde: no toco nada
end
```

Que sea un script Lua no es un detalle de estilo. Si esto fueran dos comandos
—`GET` y luego `SET`— habría una ventana entre ambos y el problema volvería un
nivel más abajo. Redis ejecuta cada script de forma atómica, y eso es lo que
hace que la comprobación y la escritura sean indivisibles.

El corolario, que es donde se cayó: **la liberación necesita exactamente la
misma protección que la escritura.** Un `DEL` incondicional del cerrojo borra el
de quien sea. El A del ejemplo, al terminar, habría borrado el cerrojo de B
mientras B seguía trabajando, metiendo a un tercero dentro de la sección
crítica. Por eso hay dos scripts Lua y no uno: `LUA_UPDATE_AND_UNLOCK` para
salir mutando, `LUA_RELEASE_LOCK` para salir sin mutar. Los dos comprueban el
token.
