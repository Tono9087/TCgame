# Rob and Run — Informe del tablero (91 casillas)

## Conteo por rol

| Rol | Casillas |
|---|---|
| bloqueo | 6 |
| bonus | 8 |
| botin_bajo | 8 |
| botin_medio | 6 |
| boveda | 1 |
| calle | 48 |
| callejon | 12 |
| comisaria | 1 |
| guarida | 1 |

## Colisiones detectadas en la especificación

- (-2, 0): botin_medio, callejon:Suroeste
- (2, -2): botin_medio, callejon:Noreste
- (3, -2): botin_medio, bloqueo

## Reubicaciones

- **botin_medio** (-2, 0) → (-3, -1): Colisiona con el callejón Suroeste. El corredor es indivisible; el robo medio se mueve al hueco libre adyacente al callejón y conserva su valor.
- **botin_medio** (2, -2) → (3, -4): Colisiona con el callejón Noreste. Se usa la posición espejo (eje X) de la reubicación anterior para mantener la simetría Este-Oeste del layout.
- **bloqueo** (3, -2) → (3, -1): Colisiona con Botín Medio (3,-2), de mayor prioridad. (3,-1) es el espejo exacto del bloqueo (-3,2).
- **bloqueo** (-2, 1) → (-2, 3): Conflicto de navegación: junto al bloqueo (-1,-1), el muro especificado (0,-1)|(-1,0) y el cierre lateral del banco, dejaba la calle (-1,0) como un bolsillo inalcanzable para la policía. Se desplaza un anillo hacia fuera dentro del mismo sector Noroeste.

## Salidas de callejones

- Suroeste: (-4, 0) → (-5, 0); (-2, 0) → (-1, 0)
- Sureste: (2, 0) → (1, 0); (4, 0) → (5, 0)
- Noroeste: (-3, 3) → (-4, 4); (-1, 1) → (-1, 0)
- Noreste: (1, -1) → (1, 0); (3, -3) → (4, -4)
  - Nota Noroeste: La continuación recta (0, 0) es 'boveda'; se abre hacia la dirección contigua.
  - Nota Noreste: La continuación recta (0, 0) es 'boveda'; se abre hacia la dirección contigua.

## Muros

- Callejón: 48 segmentos
- Banco: 4 segmentos
- fusionado: [[0, 1], [-1, 1]] — La arista ya tiene el muro del callejón (mismo cierre); no se duplica geometría.
- fusionado: [[0, -1], [1, -1]] — La arista ya tiene el muro del callejón (mismo cierre); no se duplica geometría.
- añadido: [[0, 0], [1, 0]] — Sin este muro la casilla sería un tercer acceso directo al banco.
- añadido: [[0, 0], [-1, 0]] — Sin este muro la casilla sería un tercer acceso directo al banco.

## Validación de layout

- ✅ Grilla: 91 coordenadas axiales únicas — 91
- ✅ Grilla: todas dentro de radio 5
- ✅ Grilla: sin casillas faltantes (3N(N+1)+1)
- ✅ Juego: comisaria = 1 — 1
- ✅ Juego: guarida = 1 — 1
- ✅ Juego: botin_bajo = 8 — 8
- ✅ Juego: botin_medio = 6 — 6
- ✅ Juego: boveda = 1 — 1
- ✅ Juego: bonus = 8 — 8
- ✅ Juego: callejon = 12 — 12
- ✅ Juego: bloqueo = 6 — 6
- ✅ Juego: calles normales = 48 (resto) — 48
- ✅ Juego: cada coordenada tiene exactamente un rol
- ✅ Callejón Suroeste: 3 casillas consecutivas adyacentes
- ✅ Callejón Suroeste: 2 salidas abiertas a calle transitable — [[[-4, 0], [-5, 0]], [[-2, 0], [-1, 0]]]
- ✅ Callejón Suroeste: continuidad interior sin muros
- ✅ Callejón Suroeste: muro en cada arista expuesta (12) — 12
- ✅ Callejón Sureste: 3 casillas consecutivas adyacentes
- ✅ Callejón Sureste: 2 salidas abiertas a calle transitable — [[[2, 0], [1, 0]], [[4, 0], [5, 0]]]
- ✅ Callejón Sureste: continuidad interior sin muros
- ✅ Callejón Sureste: muro en cada arista expuesta (12) — 12
- ✅ Callejón Noroeste: 3 casillas consecutivas adyacentes
- ✅ Callejón Noroeste: 2 salidas abiertas a calle transitable — [[[-3, 3], [-4, 4]], [[-1, 1], [-1, 0]]]
- ✅ Callejón Noroeste: continuidad interior sin muros
- ✅ Callejón Noroeste: muro en cada arista expuesta (12) — 12
- ✅ Callejón Noreste: 3 casillas consecutivas adyacentes
- ✅ Callejón Noreste: 2 salidas abiertas a calle transitable — [[[1, -1], [1, 0]], [[3, -3], [4, -4]]]
- ✅ Callejón Noreste: continuidad interior sin muros
- ✅ Callejón Noreste: muro en cada arista expuesta (12) — 12
- ✅ Banco: exactamente 2 accesos directos (N y S) — [(0, -1), (0, 1)]
- ✅ Muros: los únicos muros entre casillas no-callejón son los del banco — 4
- ✅ Muros: sin aristas duplicadas
- ✅ Navegación: la policía alcanza todas las casillas no-callejón
- ✅ Navegación: los ladrones alcanzan todas las casillas transitables
- ✅ Navegación: la policía no puede entrar en ningún callejón
- ✅ Navegación: todas las salidas de callejón conectan con la red de calles

## Validación geométrica

- ✅ Ningún objeto fuera del tablero
- ✅ Sin materiales faltantes
- ✅ Muros: sin geometría duplicada (1 objeto por arista)
- ✅ Sin edificios/marcadores/fichas flotando
- ✅ Sin intersecciones muro-edificio/ficha
- ✅ Fichas: 4, apoyadas en su casilla de inicio
- ✅ Fichas: sin solapamiento (dist. mínima > 2 x radio base 0.15)
- ✅ Casillas: 91 objetos

## Registro coordenada → rol

| q | r | rol |
|---|---|---|
| -5 | 0 | bonus |
| -5 | 1 | calle |
| -5 | 2 | calle |
| -5 | 3 | bonus |
| -5 | 4 | calle |
| -5 | 5 | calle |
| -4 | -1 | botin_bajo |
| -4 | 0 | callejon |
| -4 | 1 | calle |
| -4 | 2 | calle |
| -4 | 3 | botin_bajo |
| -4 | 4 | calle |
| -4 | 5 | calle |
| -3 | -2 | calle |
| -3 | -1 | botin_medio |
| -3 | 0 | callejon |
| -3 | 1 | botin_medio |
| -3 | 2 | bloqueo |
| -3 | 3 | callejon |
| -3 | 4 | calle |
| -3 | 5 | calle |
| -2 | -3 | botin_bajo |
| -2 | -2 | calle |
| -2 | -1 | bonus |
| -2 | 0 | callejon |
| -2 | 1 | calle |
| -2 | 2 | callejon |
| -2 | 3 | bloqueo |
| -2 | 4 | botin_bajo |
| -2 | 5 | calle |
| -1 | -4 | calle |
| -1 | -3 | calle |
| -1 | -2 | calle |
| -1 | -1 | bloqueo |
| -1 | 0 | calle |
| -1 | 1 | callejon |
| -1 | 2 | botin_medio |
| -1 | 3 | calle |
| -1 | 4 | calle |
| -1 | 5 | calle |
| 0 | -5 | guarida |
| 0 | -4 | calle |
| 0 | -3 | bonus |
| 0 | -2 | calle |
| 0 | -1 | calle |
| 0 | 0 | boveda |
| 0 | 1 | calle |
| 0 | 2 | calle |
| 0 | 3 | bonus |
| 0 | 4 | calle |
| 0 | 5 | comisaria |
| 1 | -5 | calle |
| 1 | -4 | calle |
| 1 | -3 | calle |
| 1 | -2 | bloqueo |
| 1 | -1 | callejon |
| 1 | 0 | calle |
| 1 | 1 | botin_medio |
| 1 | 2 | calle |
| 1 | 3 | calle |
| 1 | 4 | calle |
| 2 | -5 | botin_bajo |
| 2 | -4 | calle |
| 2 | -3 | calle |
| 2 | -2 | callejon |
| 2 | -1 | bloqueo |
| 2 | 0 | callejon |
| 2 | 1 | bonus |
| 2 | 2 | botin_bajo |
| 2 | 3 | calle |
| 3 | -5 | calle |
| 3 | -4 | botin_medio |
| 3 | -3 | callejon |
| 3 | -2 | botin_medio |
| 3 | -1 | bloqueo |
| 3 | 0 | callejon |
| 3 | 1 | calle |
| 3 | 2 | calle |
| 4 | -5 | botin_bajo |
| 4 | -4 | calle |
| 4 | -3 | calle |
| 4 | -2 | calle |
| 4 | -1 | botin_bajo |
| 4 | 0 | callejon |
| 4 | 1 | calle |
| 5 | -5 | bonus |
| 5 | -4 | calle |
| 5 | -3 | calle |
| 5 | -2 | bonus |
| 5 | -1 | calle |
| 5 | 0 | calle |
