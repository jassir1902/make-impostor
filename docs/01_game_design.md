# Documento de Diseño del Juego (GDD) - El Impostor

Este documento define las reglas de negocio, la mecánica principal y el flujo de experiencia de usuario para la versión web del Juego del Impostor. Servirá como la "fuente de la verdad" para el comportamiento de la aplicación.

## 1. Concepto Principal

El Juego del Impostor es una experiencia multijugador de deducción social por turnos. Los jugadores inocentes deben descubrir quién es el impostor basándose en las palabras que cada uno elige decir en su turno, mientras que el impostor debe intentar mezclarse sin conocer la palabra real, guiándose únicamente por una pista general de la temática.

## 2. Roles del Juego

| Rol          | Objetivo                                                 | Información Disponible                                                      |
| :----------- | :------------------------------------------------------- | :-------------------------------------------------------------------------- |
| **Inocente** | Descubrir y eliminar a los impostores mediante votación. | Conoce la temática general y la palabra exacta de la ronda.                 |
| **Impostor** | Sobrevivir hasta igualar en número a los inocentes.      | Solo conoce la temática general y una pista opcional. No conoce la palabra. |

## 3. Parámetros de la Sala y Configuración (Host)

El primer jugador en crear/entrar a una sala es designado automáticamente como el Anfitrión (_Host_). El anfitrión tiene el control del inicio y la configuración de la partida.

- **Mínimo de jugadores:** Se requieren al menos 3 jugadores en la sala para iniciar una partida.
- **Límite de jugadores:** Máximo 10 jugadores por sala (recomendado para mantener fluidez).
- **Selección de Temática:** El anfitrión elige una temática del catálogo o selecciona "Aleatorio".
- **Uso de Pistas (Toggle):** Define si los impostores recibirán una pista de ayuda.
- **Mostrar Categoría (Toggle):** Define si el nombre de la temática se oculta o se muestra a todos durante el juego.
- **Voto Anónimo (Toggle):** Define si al final de la votación se revela quién votó por quién o si se mantiene en secreto.

## 4. Matemáticas y Condiciones de Victoria

El anfitrión (Host) tiene la libertad de elegir la cantidad exacta de impostores para la ronda a través del menú de configuración. Sin embargo, para preservar el balance del juego, el servidor es la autoridad absoluta y no confía ciegamente en el valor enviado por el cliente.

El servidor valida estrictamente que la cantidad elegida por el Host se encuentre dentro de un rango permitido (Mínimo 1, y un Máximo calculado dinámicamente). La fórmula aplicada para el límite máximo es: floor((N - 1) / 2) donde N es el número total de jugadores vivos en la sala al momento de iniciar la ronda. Si el Host envía un número fuera de este rango, el servidor rechaza la petición e impide el inicio de la partida.

**Condiciones de fin de partida:**

- **Victoria de los Inocentes:** El juego termina inmediatamente a favor de los inocentes si la cantidad de impostores vivos llega a cero (0).
- **Victoria del Impostor:** El juego termina inmediatamente a favor de los impostores si la cantidad de impostores vivos es igual o mayor a la cantidad de inocentes vivos.

## 5. Dinámica de Turnos y Rondas

El juego se divide en un ciclo de Rondas. Cada ronda consta de una fase de escritura y una fase de votación.

### Fase de Escritura (Turnos)

1. Al iniciar el juego, el servidor genera un orden de turnos aleatorio que se mantendrá durante toda la partida.
2. Al iniciar un turno, el servidor establece un `turn_deadline` (timestamp) con 20 segundos de límite. El frontend utiliza este dato **únicamente** para mostrar una cuenta regresiva visual — nunca para decidir por su cuenta que el turno expiró.
3. La autoridad real sobre el tiempo no vive en la memoria de ningún proceso: el servidor la delega en una clave de Redis con TTL de 20 segundos (`room:{ABCD}:timeout`). Al expirar, Redis notifica el evento y cualquier instancia de backend disponible compite por un cerrojo distribuido para aplicar la penalización. La instancia que gana el cerrojo registra la penalización de "TIEMPO_AGOTADO" en el historial de la ronda y avanza automáticamente al siguiente jugador vivo. El detalle técnico completo de este mecanismo (TTL, _keyspace notifications_ y cerrojo con _fencing token_) vive en `02_architecture.md`, secciones 3 y 4 — este documento solo fija la regla de negocio: 20 segundos por turno, penalización registrada, avance automático.

### Fase de Votación y Empates

1. Una vez que todos los jugadores vivos han completado su turno, se abre la pantalla de votación.
2. Cada jugador selecciona a su sospechoso y presiona "Enviar Voto".
3. **Resolución de Votos:** El jugador con más votos es eliminado.
4. **Regla del Primer Empate:** Si hay un empate en la mayoría de votos, se
   realiza una segunda ronda de votación rápida. **Todos los jugadores
   vivos conservan su derecho a votar** (el pool de votantes no cambia),
   pero el pool de candidatos se restringe exclusivamente a los
   jugadores que quedaron empatados en la primera ronda.
5. **Regla del Doble Empate:** Si el desempate resulta en un nuevo empate, nadie es eliminado. La ronda avanza directamente a la siguiente palabra.

## 6. Abandono de Partida (Desconexiones)

- **Recargas de Página (Refresh):** El sistema utiliza un ID persistente guardado en el navegador de cada jugador. Si un jugador recarga la página o sufre un corte de red temporal, mantiene su lugar, su rol y su estado vital.
- **Salida Definitiva:** Si un jugador utiliza el botón explícito de "Salir de la sala", es considerado como una eliminación inmediata del juego. El servidor evaluará las condiciones de victoria de forma instantánea. Si era su turno, este se salta automáticamente.
- **Migración de Anfitrión (Host Migration):** Si el jugador que posee el rol de Anfitrión abandona la sala definitivamente, el servidor detectará la vacante y transferirá automáticamente los privilegios de Host al jugador más antiguo que siga conectado en la sala, evitando que la partida quede "huérfana" o bloqueada. El orden de antigüedad se determina por el orden real de ingreso a la sala, no por la vista local de conexiones de una única instancia de backend (ver `02_architecture.md`, sección 3.3).

## 7. Sistema de Puntuación y Clasificación

El juego maneja dos sistemas de puntuación con propósitos y ciclos de vida distintos: un **puntaje efímero por sala** (`score`) que impulsa la competitividad dentro de una misma sesión de juego, y **estadísticas persistentes de perfil** que sobreviven entre partidas, atadas a una cuenta de usuario.

### 7.1 Puntaje Efímero de Sala (`score`)

Este puntaje evalúa la capacidad de supervivencia y engaño de los jugadores durante múltiples partidas dentro de una misma sesión de sala:

- **Jugador Inocente:** Gana **100 puntos** por cada ronda sobrevivida.
- **Jugador Impostor:** Al tener una condición de supervivencia más difícil, gana **200 puntos** por cada ronda sobrevivida.

**Seguridad del cálculo:** Para evitar la suplantación o la detección anticipada del impostor mediante el análisis del tráfico de red (DevTools), el campo `score` no sufre modificaciones durante las fases de `playing` o `voting`. El servidor realiza el cálculo de supervivencia y aplica la suma total de puntos exclusivamente en el instante en que la partida finaliza (estado `revealing`), actualizando la tabla de clasificación de forma segura.

**Persistencia y ciclo de vida:** Este puntaje está estrictamente ligado al ciclo de vida de la sala. Si un jugador sufre una desconexión accidental y logra reconectarse a la misma sala activa, su puntuación acumulada se mantendrá intacta. Sin embargo, si la sala queda vacía y es destruida por el servidor, o si el jugador se une a una sala con un código distinto, su puntuación iniciará desde cero. **El valor numérico de `score` nunca se persiste fuera de Redis ni se traduce a las estadísticas de perfil** — son dos sistemas independientes.

### 7.2 Estadísticas Persistentes de Perfil (Fase 4)

Independientemente del `score` de una partida específica, la cuenta de un jugador registrado acumula un conteo de **victorias por rol** a lo largo de todas las partidas que juega:

- `victorias_como_inocente`: se incrementa en 1 si el jugador terminó una partida viva en el bando ganador siendo Inocente.
- `victorias_como_impostor`: se incrementa en 1 si el jugador terminó una partida viva en el bando ganador siendo Impostor.

**Reglas de registro:**

- Este registro ocurre **exclusivamente** en el instante en que la sala transiciona a `status: "revealing"` — el mismo momento en que se calcula el `score` efímero de la sección 7.1, pero como una escritura completamente separada hacia la base de datos persistente (Supabase), no hacia Redis.
- Se registra **únicamente** para jugadores que tienen una sesión de usuario iniciada al momento del `revealing`. Un jugador invitado (sin cuenta) nunca genera una escritura persistente — su partida no se pierde de forma anómala, simplemente nunca estuvo destinada a durar más allá de la sala, igual que su `score`.
- No se persiste el `score` numérico de la sala, ni una "tasa de aciertos" ni ninguna otra métrica derivada — solo el conteo de victorias por rol. Cualquier estadística adicional de perfil que se quiera agregar en el futuro debe declararse explícitamente aquí antes de implementarse, para evitar que el esquema de Supabase y este documento diverjan.

## 8. Sistema de Historial (Log de Partida y Temáticas)

### Prevención de Repetición

El servidor asocia el ID de la temática jugada con el código de la sala actual. Durante una misma sesión de sala, el servidor filtra aleatoriamente las palabras disponibles para garantizar que una palabra previamente jugada nunca vuelva a salir.
**Agotamiento del Catálogo:** Si el grupo de jugadores agota todas las palabras disponibles de una temática elegida, el servidor reiniciará automáticamente el filtro histórico de esa categoría específica. Esto permite que el juego continúe de forma ininterrumpida (ideal para temáticas cortas creadas manualmente), volviendo a disponer del catálogo completo.

### Debate Post-Partida

El servidor mantiene un registro estructurado (`RoundLog`) de cada ronda completada. Al finalizar la partida (cuando alguien gana), se muestra a todos los jugadores un resumen que incluye:

- El número de ronda.
- La palabra que cada jugador escribió en su turno (o si fue una penalización automática por tiempo agotado).
- Quién fue el eliminado de esa ronda (o si hubo un doble empate).
- **El rol real de cada jugador** — inocente o impostor. Antes de este punto el rol de los demás nunca se revela (es la mecánica central del juego); pero una vez que la partida entra en `revealing`, ocultarlo ya no protege nada, y es precisamente el momento en que el juego debe cerrar el misterio — incluyendo el caso en que los impostores ganan sin haber sido descubiertos nunca durante la partida.
  Este registro es vital para la experiencia social y el debate posterior entre los participantes.
