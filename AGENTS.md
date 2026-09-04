# AGENTS.md — make-impostor

Reglas de trabajo para este repositorio.

Este archivo es **autocontenido a propósito**. Parte de lo que sigue también
vive en la configuración personal de Claude del autor, que no está en el
repositorio: quien clone esto (u otro agente, u otra máquina) no la vería.
Cuando algo de aquí y esa configuración personal difieran, **manda este
archivo**, porque es el que viaja con el código.

---

## 1. El proyecto

**Nombre oficial: `make-impostor`**, con «o». Así se llama el repositorio de
GitHub, el proyecto de Jira (clave `MI`) y la carpeta local. En prosa y en la
interfaz, el juego se presenta como «El Impostor».

Juego web multijugador de deducción social por turnos, en tiempo real.
Backend FastAPI + Redis como única fuente de verdad; frontend Next.js;
transporte WebSocket.

Es un **proyecto de aprendizaje**. El objetivo no es solo que el juego
funcione: es entender sistemas distribuidos y en tiempo real, y más adelante
pipelines de IA y RAG. Eso cambia cómo se trabaja aquí — ver la sección 8.

---

## 2. Autorizaciones de Git

**`commit`, `push` y `pull request` son tres permisos distintos. Autorizar uno
no autoriza los siguientes.** Nunca ejecutar `git commit`, `git push` ni
`gh pr create` sin que el autor lo pida en ese momento.

«Arranca con X» autoriza **planificar**, no comitear.

### Reescritura de historia

Este proyecto trabaja con **rebase** (sección 3), así que reescribir historia
es parte del flujo normal y no puede requerir un permiso cada vez. La línea que
decide no es el comando, es **si los commits ya se publicaron**:

| Situación | Permiso |
|---|---|
| `rebase`, `--amend` o `reset` sobre una rama **local sin publicar** | **Preautorizado** |
| Lo mismo sobre una rama **ya publicada** (implica `--force-with-lease`) | **Se pide cada vez, y se explica antes** |
| Cualquier reescritura de `main` | **Prohibido** |
| `git push --force` a secas | **Prohibido** |

El motivo del corte: mientras los commits solo existan en la máquina local,
reescribirlos no puede destruir trabajo de nadie. En cuanto están publicados,
un rebase cambia hashes que otros (u otra máquina, o un PR abierto) ya tienen.

`--force-with-lease` sigue pidiendo permiso aunque sea mucho más seguro que
`--force` —falla si alguien empujó algo que no has visto— porque sigue
reescribiendo lo que ya está publicado.

## 3. Ramas

**Nunca trabajar directamente sobre `main`.** La rama se crea antes de escribir
código, no después.

```
<tipo>/MI-<número>-<descripción-corta>
```

Tipos: `feature/`, `fix/`, `test/`, `ops/`, `docs/`.

El `MI-<número>` es la tarjeta de Jira (sección 6). Si todavía no existe, se
crea antes de la rama.

**Las ramas salen de `main` y vuelven a `main` vía PR.** No hay `develop`: con
un solo desarrollador no hay integración en paralelo que estabilizar, y una
rama intermedia solo añadiría un rebase más.

### Historia lineal

`main` no lleva commits de merge. Dos reglas:

- **Sincronizar** con `main` es siempre `git pull --rebase`, nunca un merge.
  Un commit de merge de sincronización no aporta contenido y ensucia el
  historial.
- **Integrar** un PR es siempre *Rebase and merge*. Los ajustes del repositorio
  en GitHub tienen desactivadas las otras dos opciones para que no se pueda
  hacer por accidente.

**Nunca *Squash and merge*.** Aquí las series de commits son deliberadas —un
commit por defecto corregido, con su porqué en el cuerpo— y aplastarlas en uno
solo tira ese trabajo. *Squash* sirve para ramas de quince commits de «wip»;
no es el caso.

### Referencias estables

Bajo rebase, **un hash de commit es desechable**: cualquier sincronización lo
reescribe. Nunca citar hashes en documentación versionada (ADRs, `docs/`,
descripciones de tarjetas). El identificador estable de un trabajo es su
tarjeta de Jira, que además lleva el contexto que un hash no tiene.

Citar un hash está bien en un mensaje de commit o en un comentario de PR, que
son efímeros por naturaleza.

## 4. Antes de cada commit

Presentar al autor, siempre, y esperar autorización:

1. Objetivo alcanzado y archivos modificados
2. Resumen del diff, con las decisiones que **no se deducen** de él
3. Validaciones ejecutadas y su resultado
4. Riesgos y pendientes conocidos
5. Estado de Git
6. Mensaje de commit propuesto

Y **antes de empezar a programar**, la división en commits prevista.

## 5. Mensajes de commit

- **Sin `Co-authored-by` ni ningún trailer de coautoría.** Los commits son solo
  del autor.
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
  `chore:`, `ci:`.
- **Asunto en inglés**, imperativo, una línea.
- **Cuerpo en español**, con tildes, explicando **por qué**. El qué ya está en
  el diff.

Igual para los PR: título en inglés con formato de commit, cuerpo en español
con objetivo, solución, alcance excluido, validaciones y riesgos.

---

## 6. Jira

Proyecto **`MI`** (`make-impostor`) en `https://jassir1902.atlassian.net`,
tablero Kanban.

Tipos disponibles: **Epic**, **Historia**, **Tarea**, **Error**, **Subtask**.

**Toda tarea deja constancia en una tarjeta antes de empezar.** No se escribe
código de una tarea que no existe en el tablero. La tarjeta se referencia en el
nombre de la rama y en el PR.

Qué tipo usar:

| Tipo | Cuándo |
|---|---|
| **Epic** | Una fase del roadmap (`docs/04`), o un bloque grande como «Fase 3: IA» |
| **Historia** | Funcionalidad con valor para quien juega («ver el resumen post-partida») |
| **Tarea** | Trabajo técnico sin cara visible (infraestructura, refactor, documentación) |
| **Error** | Defecto en algo que ya se dio por terminado |
| **Subtask** | Trozo de una tarjeta mayor, cuando partirla ayuda a seguirla |

Una tarjeta debe poder leerse sin contexto: qué pasa hoy, qué se espera, y
cómo se sabe que quedó. Los hallazgos de auditoría van como **Error**, con el
escenario de fallo concreto, no como «revisar X».

**Crear o modificar tarjetas es una acción externa: se pide autorización antes,
igual que un push.**

---

## 7. Documentación continua

La documentación no es un paso final. **Un cambio que altera lo documentado no
está terminado hasta que el documento lo refleja, en el mismo commit.**

Qué tocar según lo que cambies:

| Si cambias… | Actualiza… |
|---|---|
| Una regla del juego | `01_game_design.md` |
| Estado, concurrencia, persistencia | `02_architecture.md` **+ un ADR** |
| Un contrato de red (payload, código de error, campo de `RoomView`) | `03_api_and_events.md` **y** `frontend/src/types/game.ts`, en el mismo commit |
| El alcance de una fase | `04_roadmap_and_phases.md` |
| Estructura o estado del frontend | `05_frontend_architecture.md` |
| Infraestructura, CI/CD, despliegue | `06_devops_and_ci_cd.md` |
| Estrategia o cobertura de pruebas | `07_testing_and_qa_strategy.md` |
| Qué es secreto, para quién y por qué canal | `08_security.md` |
| **Lo que funciona o deja de funcionar hoy** | `00_current_status.md` |

`00_current_status.md` se actualiza en **todo** commit que cambie qué funciona.
Es el primer archivo que se lee al volver al proyecto tras meses.

### Marcadores de estado

Los documentos de referencia describen el sistema deseado, y eso hace
imposible distinguir especificación de realidad. Toda sección que describa algo
no implementado lleva marcador:

- `✅ Implementado`
- `🚧 Parcial` — con una línea diciendo qué falta
- `📋 Planeado (Fase N)`

Sin marcador se asume `✅`. Si encuentras una sección sin marcador que describa
algo inexistente, marcarla es parte del trabajo.

### ADRs

`docs/adr/` guarda las **decisiones**, no el estado. Un ADR es inmutable: cuando
la decisión cambia, se escribe uno nuevo que supersede al anterior, no se edita
el viejo. Ver `docs/adr/README.md` para el formato.

Se escribe un ADR cuando: se elige entre alternativas reales con consecuencias,
se adopta o descarta una tecnología, o se fija una regla que alguien podría
querer deshacer sin entender por qué existe.

No se escriben ADRs retroactivos en masa. Cuando se toca una zona cuya decisión
nunca se registró, se rescata **esa**.

---

## 8. Modo aprendizaje

El autor usa este proyecto para aprender, y vuelve a él tras pausas largas.
Eso implica, al trabajar:

- **Explicar el porqué técnico, no solo aplicar el arreglo.** Cuando aparezca
  un concepto no trivial (cerrojo distribuido, *fencing token*, TTL como
  autoridad de tiempo, rehidratación sin *sticky sessions*, particionamiento
  por *hash tag*), explicarlo con el ejemplo concreto de este código.
- **Nombrar el modo de fallo, no solo el síntoma.** «Esto se cuelga» sirve de
  poco; «la notificación de keyspace se entrega una sola vez y su clave ya
  expiró» enseña algo.
- **Los ADRs cargan la enseñanza.** Es donde vive el razonamiento, así que es
  donde el concepto debe quedar explicado.
- **No dar por sabido el contexto del propio repositorio.** Tras meses, no se
  recuerda por qué `turn_order` no se reordena al eliminar a alguien.

## 9. Decisiones de negocio

Cuando se detecte una regla de negocio ausente o ambigua, **se pregunta antes
de implementar**, no se deja fuera de alcance para parchearla después. Un
historial de remiendos encadenados se lee peor que un incremento coherente.

Si una decisión ya aprobada se apoyaba en información incompleta y aparece algo
que la cambia, se dice, aunque ya estuviera aprobada.

## 10. Pruebas

**Una prueba que nunca ha fallado no ha demostrado nada.** Las importantes se
verifican rompiendo a propósito lo que protegen y comprobando que fallan
exactamente las esperadas.

Tomar línea base antes de empezar y compararla al terminar. Si una prueba
existente cambia de resultado, parar.

No repetir validaciones caras sin motivo: si la suite ya pasó sobre ese
contenido y desde entonces solo se movieron commits o se cambió documentación,
no se vuelve a correr.

### Dónde va cada prueba

| Carpeta | Qué contiene | Dependencias |
|---|---|---|
| `tests/unit/services/` | Lógica pura de `game_service` | Ninguna |
| `tests/unit/api/` | Rutas y WebSocket con **dobles** de Redis | Ninguna |
| `tests/integration/` | Contra un **Redis real**, multi-instancia | Redis |
| `tests/e2e/` | Playwright, navegadores reales | Todo el stack |

`tests/integration/` y `tests/e2e/` están **vacías**. No poner ahí pruebas con
dobles: aparentaría que ese hueco está cubierto cuando no lo está. Un doble
demuestra que el código hace lo que se espera, no que Redis se comporte como
suponemos.

## 11. Cómo escribir

**No dirigir notas a personas por su nombre** en PR, documentación, tarjetas ni
ningún artefacto del repositorio. Los artefactos sobreviven a quien ocupa hoy
cada rol. En conversación, nombrar a la gente con normalidad.

Comentarios y documentación en español. Identificadores, nombres de rama y
asuntos de commit en inglés.

Al tocar un módulo que no construimos nosotros: cambios aditivos con valor por
omisión que preserve el comportamiento, escribir como escribe ese archivo, no
modificar sus pruebas, y nunca formatear directorios enteros.

---

## 12. Comandos

```bash
# Backend + Redis
docker compose -f backend/docker-compose.yml up --build

# Suite de pruebas (desde la raíz)
python -m pytest -q

# Frontend
cd frontend && npm run dev
npx tsc --noEmit
```

## 13. Mapa de la documentación

| Archivo | Qué responde |
|---|---|
| `docs/00_current_status.md` | Qué funciona **hoy**, qué está roto, qué sigue |
| `docs/01_game_design.md` | Reglas del juego |
| `docs/02_architecture.md` | Estado, concurrencia y persistencia en el backend |
| `docs/03_api_and_events.md` | Contratos REST y WebSocket |
| `docs/04_roadmap_and_phases.md` | Fases y alcance |
| `docs/05_frontend_architecture.md` | Estructura, estado y red del frontend |
| `docs/06_devops_and_ci_cd.md` | Infraestructura, Git, CI/CD, monitoreo |
| `docs/07_testing_and_qa_strategy.md` | Estrategia de pruebas y políticas de PR |
| `docs/08_security.md` | Qué es secreto, para quién y por qué canal |
| `docs/adr/` | Decisiones tomadas, inmutables |
