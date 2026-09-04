# Registro de Decisiones de Arquitectura (ADR)

## Qué es un ADR y en qué se diferencia del resto de `docs/`

Los documentos numerados de `docs/` (`01`–`08`) son **referencia viva**:
describen cómo se comporta el sistema y se editan en sitio cuando cambia. Son
necesarios, pero al editarse **pierden la historia**: dicen cómo son las cosas,
nunca por qué se decidió que fueran así ni qué se descartó en el camino.

Un ADR captura **una decisión**: el contexto en que se tomó, las alternativas
que había, lo que se eligió, y lo que costó elegirlo.

La propiedad que lo hace útil es que es **inmutable**. Cuando la decisión
cambia, no se edita el ADR: se escribe uno nuevo que supersede al anterior, y el
viejo pasa a `Superseded` conservando su texto original. Editarlo destruiría lo
único que aporta — poder responder «¿en qué estábamos pensando?» dentro de seis
meses, con la información que había entonces y no con la de hoy.

Ejemplo de por qué importa en este proyecto: en `04_roadmap_and_phases.md`, la
Fase 1 argumenta en un *bullet* que el cerrojo distribuido hace falta **aunque
solo corra un proceso** de FastAPI. Es un razonamiento no obvio y fácil de
deshacer por alguien que piense «esto sobra, hay un único worker». Enterrado en
un roadmap no lo protege nadie. En un ADR sí.

## Cuándo escribir uno

- Se elige entre alternativas reales con consecuencias distintas.
- Se adopta, se descarta o se sustituye una tecnología.
- Se fija una regla o invariante que alguien podría deshacer sin entender por
  qué existe.
- Se acepta a sabiendas una deuda o una limitación.

**No** lleva ADR un cambio que solo aplica algo ya decidido, ni un arreglo cuyo
razonamiento cabe entero en el cuerpo del commit.

## Cuándo NO escribirlos

No se escriben ADRs retroactivos en masa. El sistema ya tiene decisiones
tomadas sin registrar, y sentarse a documentarlas todas produce texto que nadie
lee. La regla es: **cuando se toca una zona cuya decisión nunca se registró, se
rescata esa y solo esa**, en el mismo trabajo.

## Nombre y numeración

```
docs/adr/NNNN-titulo-en-kebab-case.md
```

`NNNN` es correlativo desde `0001` y no se reutiliza nunca, ni siquiera si un
ADR se rechaza o se supersede.

## Estados

| Estado | Significado |
|---|---|
| `Propuesto` | Escrito, en discusión, todavía no se actúa sobre él |
| `Aceptado` | Vigente. El código debería reflejarlo |
| `Superseded por NNNN` | Reemplazado. Su texto queda intacto |
| `Rechazado` | Se consideró y se descartó. Se conserva: saber qué se descartó y por qué evita volver a proponerlo |

## Plantilla

```markdown
# NNNN — Título en una línea

- **Estado:** Propuesto | Aceptado | Superseded por NNNN | Rechazado
- **Fecha:** AAAA-MM-DD
- **Relacionado:** docs/0N_archivo.md §X, MI-NN, ADR NNNN

## Contexto

Qué problema forzó la decisión, con los hechos que había **en ese momento**.
Sin justificar todavía. Si el detonante fue un fallo concreto, describir el
modo de fallo, no el síntoma.

## Alternativas consideradas

Una subsección por alternativa real, con su costo y su beneficio. Una
alternativa que no se evaluó de verdad no va aquí — inventarlas para rellenar
hace el documento menos fiable, no más completo.

## Decisión

Qué se eligió y el criterio que lo decidió.

## Consecuencias

Qué se gana, **qué se pierde**, y qué queda pendiente o vigilado por haber
elegido esto. Esta sección es la que más se consulta y la que más se descuida.

## Nota de aprendizaje

Opcional. El concepto general detrás de la decisión, explicado con el ejemplo
concreto de este repositorio. Este proyecto es un experimento de aprendizaje
(ver `AGENTS.md` §8) y es aquí donde esa explicación pertenece.
```

## Índice

| ADR | Título | Estado |
|---|---|---|
| [0001](0001-cerrojo-distribuido-con-fencing.md) | Cerrojo distribuido con fencing como autoridad de escritura | Aceptado |
