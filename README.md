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
- **Filtros:** hoy, esta noche, finde o semana; tarde o noche; rubro.
- **Ubicación:** se calcula todo en el teléfono, y la página lo dice. Muestra
  "Cerca tuyo ahora" (lo que empieza en las próximas 3 horas, por distancia) y
  la distancia de cada evento en cuadras (120 m, de esquina a esquina). Si el
  visitante no comparte la ubicación, elige un punto de partida
  (`puntos_partida.py`, coordenadas de OSM).
- **SEO:** la lista de eventos va en el HTML, porque Google casi no lee el mapa
  en JS.

## Tests

```bash
python -m unittest discover -s tests
```
