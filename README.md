# Movete-mapa

Mapa cultural de Gran La Plata para movete.info: genera `/mapa/`.

Sigue el patrón de `movete-cine` y `movete-espectaculos`: lee el mismo
`eventos.json` que En Vivo y escribe dentro de `Movete-info`.

Entrada:

- `eventos.json`, el que genera `movete-scraper`.
- Las salas y sus coordenadas, en `movete-espectaculos/venues.py`
  (`VENUES_DIRECCIONES`). Se importan de ahí: este repo no guarda salas.

Salida:

```txt
Movete-info/mapa/index.html   lista indexable de la semana + el mapa
Movete-info/mapa/<zona>/index.html   lo mismo, recortado a una zona
Movete-info/mapa/mapa.css
Movete-info/mapa/mapa.js
Movete-info/mapa/sitemap-mapa.xml   lo declara Movete-info/robots.txt
```

Correr local (con `movete-espectaculos` clonado al lado):

```bash
python generar_mapa.py --eventos ../movete-espectaculos/eventos.ejemplo.json \
    --output ../Movete-info/mapa --hoy 2026-06-21
```

Si `movete-espectaculos` está en otra carpeta, se indica con
`MOVETE_ESPECTACULOS=/ruta/a/movete-espectaculos`.

Al final imprime las salas que tuvieron eventos pero todavía no tienen
coordenadas (`sin_coordenadas`). Sus eventos salen igual en la lista, sin pin,
y hay que pedirle las coordenadas a Tres.

## Cómo funciona

- **Mapa:** Leaflet con fondo vectorial de OpenFreeMap, que es gratis y no pide
  registro. Usa el estilo `positron` de día y `dark` de noche (de 20 a 7) o si
  el teléfono está en modo oscuro. No se usan los servidores de tiles de OSM,
  porque su política no permite tráfico de un sitio en producción.
- **Pines:** un pin por sala, con el color y el icono del rubro de lo próximo
  que hay ahí, y un numerito si hay más de un show. El pin late si algo empieza
  en las próximas 2 horas. Lo que ya terminó se saca: sin hora de fin, un show
  se da por terminado a las 2 horas de empezar.
- **Filtros:** hoy, esta noche, finde o semana; tarde o noche; rubro; y
  "Gratis (confirmados)", que solo aparece si algún evento lo es. Se detecta
  del texto del evento ("gratis", "entrada libre", "a la gorra"…) o de un
  precio 0 de la fuente. No se le pide nada nuevo a quien carga en `/sumar/`.
- **Sorprendeme:** elige al azar un show que empiece pronto (en 3 horas; si
  no hay, en 8 o en 48) y, con ubicación, a menos de 25 cuadras. Respeta los
  filtros de rubro y gratis.
- **De la casa:** Tres Empanadas lleva el pin con borde dorado y una estrella,
  y abajo hay un aviso fijo con su próxima fecha real y, con ubicación, la
  distancia. Tiene un solo link, con la marca como texto. Si no hay fechas,
  dice "Ver próximas fechas". El resto del mapa no se toca: ninguna otra sala
  se oculta ni se reordena. Una sala con la misma coordenada que otra comparte
  su pin.
- **Ubicación:** se calcula todo en el teléfono, y la página lo dice. Muestra
  "Cerca tuyo ahora" (lo que empieza en las próximas 3 horas, por distancia) y
  la distancia de cada evento en cuadras (120 m, de esquina a esquina). Si el
  visitante no comparte la ubicación, elige un punto de partida
  (`puntos_partida.py`, coordenadas de OSM).
- **SEO:** la lista de eventos va en el HTML, porque Google casi no lee el mapa
  en JS.
- **Zonas:** una página por zona en `/mapa/<zona>/` (casco, Meridiano V,
  Tolosa, City Bell, Gonnet, Berisso y Ensenada), con su lista, su mapa
  centrado y links a las demás. La zona de cada sala está en `zonas.py` y sale
  de OSM. Una sala nueva con coordenadas hay que sumarla ahí; hasta entonces
  sale solo en el mapa general. Las zonas sin eventos esa semana van con
  `noindex` y quedan fuera del sitemap y de los links.

## Tests

```bash
python -m unittest discover -s tests
```
