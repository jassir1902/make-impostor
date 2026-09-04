# Seguridad: qué es secreto, para quién y por qué canal

Este documento es el **dueño único** de la pregunta «quién puede saber qué, en
qué momento». Antes vivía repartido entre `02` §6, `03` §2.1 y `01` §7.1, y esa
dispersión dejó pasar una filtración real (§4.1).

La regla que organiza todo el documento: **un secreto no se protege por
mecanismo, se protege por canal.** Basta con que un solo canal lo exponga para
que el resto de las defensas sean decorativas.

---

## 1. El activo que hay que proteger

En un juego de deducción social solo hay **un** secreto que importa:

> **Quién es el impostor**, y todo lo que permita deducirlo antes de tiempo.

Lo demás —puntajes, nombres, quién está en línea— es público por naturaleza.
Si el secreto se filtra, no hay juego; no hay degradación parcial.

De ahí se derivan tres secretos concretos:

| Secreto | De quién se oculta | Hasta cuándo |
|---|---|---|
| `players[].role` | De todos | Hasta `status == "revealing"` |
| `current_word` (la palabra de la ronda) | Del impostor | Siempre |
| El **conjunto de palabras candidatas** de la temática | Del impostor | Siempre |

El tercero es el que se pasó por alto, y es el objeto de §4.1.

## 2. Identidad: por qué el cliente nunca dice quién es

✅ Implementado

Ningún `payload` del cliente contiene `player_id`. La identidad del remitente
se resuelve **exclusivamente** desde el `secret_token` validado en el
`join_room` de esa conexión, que el backend asocia al socket.

Dos identidades distintas, que no hay que confundir:

| | `secret_token` | `connection_id` |
|---|---|---|
| Qué es | UUID persistente generado por el backend | El socket actual |
| Dónde vive | `localStorage` del navegador | En memoria del worker |
| Cuándo cambia | Nunca, mientras exista la sala | En cada reconexión |
| Para qué sirve | Probar **quién eres** | Saber **dónde escribirte** |

Es lo que permite que un refresh conserve rol y estado vital, y que la
reconexión aterrice en cualquier worker sin *sticky sessions*.

**La consecuencia de seguridad:** si el cliente pudiera mandar su `player_id`,
cualquiera votaría en nombre de otro. Al derivarlo del socket autenticado, la
suplantación exige robar el `secret_token`, que nunca viaja salvo una vez, al
emitirse.

### Conexiones duplicadas (Last-One-Wins)

Un `join_room` con un `secret_token` que ya tiene socket activo cierra el
antiguo con **4009**. Evita que dos pestañas actúen como el mismo jugador.

## 3. Las tres barreras de autorización

✅ Implementado

1. **Contrato.** Pydantic rechaza payloads malformados. Un esquema que no
   valida no llega a la lógica.
2. **Máquina de estados.** La fase decide qué es legal: `send_word` solo en
   `playing` y solo del turno activo; `vote` solo en `voting` y solo de un
   jugador vivo; en desempate, `tied_players` restringe los destinos válidos;
   `start_game` y `next_round` solo del Host.
3. **Exposición condicional.** `broadcast_room_view` construye una vista
   **distinta por destinatario** y omite lo que ese destinatario no debe saber.

La tercera es la única que protege el secreto del §1. Las dos primeras protegen
la integridad de la partida, que es otra cosa.

### Lo que el servidor no acepta del cliente aunque lo mande

- **`timed_out`.** Solo lo produce el listener de expiración del servidor. Un
  cliente que envíe literalmente `"TIEMPO_AGOTADO"` como palabra queda
  registrado como palabra normal, no como penalización.
- **`imposters_count`.** Se valida contra `floor((N-1)/2)`. El servidor es la
  autoridad, no el panel del Host.
- **`player_id`.** No se acepta en ningún payload (§2).

## 4. Superficie por canal

Aquí está el fallo que motivó el documento.

### 4.1 REST — 🚧 Con una filtración conocida

`GET /api/topics/official` devuelve el objeto `Topic` **completo**: todas las
palabras y todas las pistas. Es público, sin autenticación.

El ataque no necesita herramientas: el impostor abre esa URL en otra pestaña.
Con `show_category: true` conoce la categoría, y por tanto reduce la palabra a
las ~8 candidatas de esa temática. Con `use_hints` conoce además el mapeo
pista → palabra.

Todo el cuidado de `broadcast_room_view` para no delatar al impostor queda
anulado por un endpoint que nadie consideraba parte de la superficie de
seguridad, porque **la vigilancia estaba puesta en el WebSocket**.

**Corrección pendiente** (hallazgo 3): el catálogo debe exponerse como
`{id, name, word_count}`. El vocabulario no tiene ninguna razón para salir del
servidor: el cliente solo necesita poder elegir una temática por su nombre.

> Lección general: al enumerar qué protege un sistema, enumerar **canales**,
> no funciones. La función que filtró aquí no tiene nada que ver con el juego.

### 4.2 WebSocket — ✅ Correcto

`broadcast_room_view` arma la vista por destinatario:

- `players[].role` se **omite** mientras `status` sea `waiting`, `playing` o
  `voting`; se **incluye** en `revealing`.
- `your_word` solo se envía a inocentes; el impostor recibe `your_hint` (si
  `use_hints`) y nunca la palabra.
- `current_category` solo si `show_category`.
- `votes` no se expone en ningún momento.
- `score` no cambia durante `playing` ni `voting` — se calcula entero al entrar
  en `revealing`, para que nadie deduzca roles observando cuándo sube el
  puntaje de quién.

El último punto es sutil y vale la pena entenderlo: si el impostor sumara 200 y
los inocentes 100 al terminar cada ronda, mirar el tráfico revelaría los roles
sin necesidad de romper nada. Aplazar **todo** el cálculo elimina la señal en
lugar de intentar ocultarla.

### 4.3 Revelación final

En `revealing` se envían `players[].role`, `winner` y `round_log` completo. Es
deliberado: ocultarlo ya no protege nada y, sobre todo, un desenlace donde el
impostor gana sin ser descubierto nunca llegaría a conocerse.

## 5. Abuso y denegación de servicio

| Protección | Estado |
|---|---|
| Rate limit de 5 mensajes/s por socket, cierre con 4029 | ✅ |
| Límite de 10 jugadores por sala, cierre con 4006 | ✅ |
| Códigos de sala de 4 caracteres, alfabeto sin ambigüedades | ✅ |
| CORS con lista explícita, sin comodín junto a `allow_credentials` | ✅ |
| Contenedor de la API con usuario sin privilegios | ✅ |
| **Rate limit en los endpoints REST** | ❌ Ninguno |
| **Ciclo de vida de las salas (TTL / recolector)** | ❌ Ninguno |

Los dos últimos se combinan en un problema real: `POST /api/rooms` es público,
sin límite de tasa, y cada llamada escribe una clave que **nunca** se borra
(hallazgo 2). Un bucle trivial llena la memoria de Redis. El espacio de códigos
es de 32⁴ ≈ 1,05 millones, así que también es agotable.

Con solo 4 caracteres, además, enumerar salas activas es barato. Hoy eso solo
permite entrar a un lobby ajeno en `waiting` — `03` §3.1 cierra con **4003** si
la partida ya empezó — pero conviene tenerlo presente antes de que las salas
lleven algo que valga la pena robar.

## 6. Fases futuras

📋 Planeado

- **Fase 3 (IA).** El prompt del Host llega a un LLM: hay que tratarlo como
  entrada no confiable y limitar la tasa por IP o por sala. Y sigue vigente la
  prohibición de `02` §4.3: **nada de I/O externo dentro de la sección crítica
  del cerrojo**, porque una llamada al LLM excede de sobra los 5 s del `PX`.
- **Fase 4 (cuentas).** Entra autenticación real con Supabase. Ahí `CORS` con
  `allow_credentials` y la lista explícita de orígenes dejan de ser higiene y
  pasan a ser la frontera de sesión. Las escrituras de estadísticas solo se
  hacen para jugadores con sesión iniciada, y nunca deben bloquear la emisión
  del `revealing`.
- **Secretos.** `backend/.env` está en `.gitignore` y solo se versiona
  `.env.example`. El repositorio es **público**: cualquier clave que entre en la
  historia hay que darla por comprometida y rotarla, no basta con borrarla.
