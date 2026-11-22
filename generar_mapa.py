"""Genera /mapa/ de movete.info: el mapa cultural de Gran La Plata.

Lee el mismo eventos.json que En Vivo y las salas (con coordenadas) de
movete-espectaculos/venues.py, y escribe:

- <output>/index.html  lista indexable de la semana + el mapa (Leaflet)
- <output>/mapa.css, <output>/mapa.js

Todo lo que depende de la ubicación del visitante se calcula en su teléfono:
la página no manda la ubicación a ningún lado.

Ejemplo local:

python generar_mapa.py --eventos ../movete-espectaculos/eventos.ejemplo.json \
    --output ../Movete-info/mapa --hoy 2026-06-21
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from string import Template
from urllib.parse import quote_plus

AQUI = Path(__file__).resolve().parent
ESPECTACULOS = Path(os.environ.get('MOVETE_ESPECTACULOS', AQUI.parent / 'movete-espectaculos'))
sys.path.insert(0, str(ESPECTACULOS))

from edicion import DIAS, MESES_ABR  # noqa: E402
from generar_edicion import (  # noqa: E402
    _ALIAS_OBRA,
    CATEGORY_ORDER,
    calcular_alias_obras,
    cargar_eventos,
    cat_label,
    esc,
    evento_lugar,
    evento_titulo,
    evento_url,
    hoy_argentina,
    normalizar_categorias,
    obra_slug,
    parse_fecha,
)
from venues import venue_canonico, venue_info, venue_slug  # noqa: E402

from puntos_partida import PUNTOS_PARTIDA  # noqa: E402

# El mapa muestra de hoy en adelante: la semana que filtra la página y un día
# de margen, porque el generador corre martes, jueves y domingo.
DIAS_VENTANA = 8

# Rubros en el orden de los botones. Cine va al final: es la cartelera de
# cine clubs y espacios INCAA que trae la agenda, no la de /cine/.
ORDEN_RUBROS = [c for c in CATEGORY_ORDER if c != 'otros'] + ['cine', 'otros']

# Lugares que no son una sala: no se le pide a Tres una coordenada para ellos.
LUGARES_GENERICOS = {'la-plata', 'gran-la-plata', 'a-confirmar', 'online', 'virtual'}


def _hora(f: datetime, sin_hora: bool) -> str:
    return '' if sin_hora else f.strftime('%H:%M')


def armar_datos(eventos: list[dict], hoy: date, dias: int = DIAS_VENTANA) -> dict:
    """Eventos de la ventana, salas con pin y salas a las que les falta.

    Una sala sin coordenadas confirmadas no lleva pin, pero sus eventos salen
    igual en la lista. Esas salas quedan en 'sin_coordenadas' para pedírselas
    a Tres.
    """
    eventos = normalizar_categorias(eventos)
    _ALIAS_OBRA.clear()
    _ALIAS_OBRA.update(calcular_alias_obras(eventos))

    desde = datetime.combine(hoy, time.min)
    hasta = desde + timedelta(days=dias)
    salas: dict[str, dict] = {}
    sin_coordenadas: dict[str, str] = {}
    items: list[dict] = []
    vistos: set[tuple] = set()

    for ev in eventos:
        crudo = str(ev.get('fecha') or '').strip()
        if not crudo:
            continue
        try:
            f = parse_fecha(crudo)
        except ValueError:
            continue
        if not desde <= f < hasta:
            continue

        lugar = evento_lugar(ev)
        vc = venue_canonico(lugar)
        info = venue_info(lugar)
        direccion = str(ev.get('direccion') or info['direccion'] or '').strip()

        sala = None
        if vc and vc['lat'] is not None:
            sala = vc['slug']
            salas.setdefault(sala, {
                'nombre': vc['nombre'],
                'direccion': vc['direccion'],
                'lat': vc['lat'],
                'lng': vc['lng'],
                'url': f"/en-vivo/sala/{vc['slug']}/",
            })
        elif lugar.strip() and venue_slug(lugar) not in LUGARES_GENERICOS:
            clave = vc['slug'] if vc else venue_slug(lugar)
            sin_coordenadas.setdefault(clave, vc['nombre'] if vc else lugar.strip())

        titulo = evento_titulo(ev)
        clave_dup = (titulo.casefold(), f, sala or info['nombre'].casefold())
        if clave_dup in vistos:
            continue
        vistos.add(clave_dup)

        oslug = obra_slug(ev)
        sin_hora = len(crudo) <= 10
        items.append({
            'titulo': titulo,
            'f': f,
            'inicio': f.strftime('%Y-%m-%dT%H:%M'),
            'sin_hora': sin_hora,
            'cat': ev.get('categoria') or 'otros',
            'sala': sala,
            'lugar': vc['nombre'] if vc else (info['nombre'] if lugar.strip() else ''),
            'sala_url': f"/en-vivo/sala/{vc['slug']}/" if vc else '',
            'direccion': direccion,
            'link': f'/en-vivo/obra/{oslug}/' if oslug else evento_url(ev),
            'entradas': evento_url(ev) if oslug else '',
        })

    items.sort(key=lambda e: (e['f'], e['titulo'].casefold()))
    for i, it in enumerate(items):
        it['id'] = f'e{i}'
    return {'eventos': items, 'salas': salas, 'sin_coordenadas': sin_coordenadas}


def como_llegar(item: dict, salas: dict) -> str:
    """Link de Google Maps: con destino exacto si la sala tiene pin."""
    sala = salas.get(item['sala']) if item['sala'] else None
    if sala:
        return ('https://www.google.com/maps/dir/?api=1&destination='
                f"{sala['lat']},{sala['lng']}")
    if item['direccion']:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(item['direccion'])}"
    return ''


def render_item(item: dict, salas: dict) -> str:
    f = item['f']
    cat = item['cat']
    titulo = esc(item['titulo'])
    link = item['link']
    externo = link.startswith('http')
    if link:
        attrs = ' target="_blank" rel="noopener"' if externo else ''
        titulo_html = f'<a href="{esc(link)}"{attrs}>{titulo}</a>'
    else:
        titulo_html = titulo
    lugar = esc(item['lugar'])
    lugar_html = f'<a href="{esc(item["sala_url"])}">{lugar}</a>' if item['sala_url'] else lugar
    hora = _hora(f, item['sin_hora'])
    meta = ' · '.join(p for p in [f'{DIAS[f.weekday()][:3]} {hora} hs' if hora
                                   else DIAS[f.weekday()], lugar_html] if p)
    entradas = ''
    if item['entradas']:
        entradas = (f'\n        <p class="event-ticket"><a class="card-link" href="{esc(item["entradas"])}" '
                    'target="_blank" rel="noopener">Entradas y más info →</a></p>')
    llegar = como_llegar(item, salas)
    llegar_html = ''
    if llegar:
        llegar_html = (f'\n        <a class="mapa-llegar" href="{esc(llegar)}" target="_blank" rel="noopener"'
                       f' aria-label="Cómo llegar a {lugar} en Google Maps">'
                       '<img src="/assets/icons/google-maps.svg" alt="" width="18" height="18"> Cómo llegar</a>')
    sin_pin = '' if item['sala'] else '\n        <p class="mapa-sin-pin">Sin ubicación en el mapa todavía</p>'
    return f"""
      <li class="event-card mapa-item" id="{item['id']}" data-category="{esc(cat)}"
          data-inicio="{item['inicio']}" data-sin-hora="{'1' if item['sin_hora'] else ''}"
          data-sala="{esc(item['sala'] or '')}">
        <div class="event-card-topline">
          <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
          <p class="pill">{esc(cat_label(cat))}</p>
          <p class="mapa-dist" hidden></p>
        </div>
        <h3>{titulo_html}</h3>
        <p class="event-meta">{meta}</p>{entradas}{sin_pin}
        <div class="mapa-item-acciones">{llegar_html}
          <button type="button" class="mapa-ver" data-ver="{esc(item['sala'] or '')}"{'' if item['sala'] else ' hidden'}>Ver en el mapa</button>
        </div>
      </li>"""


def datos_cliente(datos: dict) -> str:
    """JSON que lee mapa.js. Seguro para ir dentro de <script>."""
    eventos = [{
        'id': it['id'],
        't': it['titulo'],
        'i': it['inicio'],
        'sh': it['sin_hora'],
        'c': it['cat'],
        's': it['sala'],
        'u': it['link'],
    } for it in datos['eventos']]
    rubros = {c: cat_label(c) for c in ORDEN_RUBROS}
    payload = {
        'eventos': eventos,
        'salas': datos['salas'],
        'puntos': [{'id': k, 'nombre': n, 'lat': la, 'lng': lo} for k, n, la, lo in PUNTOS_PARTIDA],
        'rubros': rubros,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def render_rubros(datos: dict) -> str:
    presentes = {it['cat'] for it in datos['eventos']}
    botones = ['<button type="button" class="mapa-chip" data-rubro="" aria-pressed="true">Todo</button>']
    for c in ORDEN_RUBROS:
        if c in presentes:
            botones.append(f'<button type="button" class="mapa-chip" data-rubro="{esc(c)}" '
                           f'aria-pressed="false" style="--cat: var(--c-{esc(c)}, var(--c-otros))">'
                           f'{esc(cat_label(c))}</button>')
    return '\n          '.join(botones)


def render_puntos() -> str:
    return '\n            '.join(f'<option value="{esc(k)}">{esc(n)}</option>' for k, n, _la, _lo in PUNTOS_PARTIDA)


def _version(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:10]


def render_pagina(datos: dict, hoy: date) -> str:
    items = datos['eventos']
    lista = ''.join(render_item(it, datos['salas']) for it in items)
    if not items:
        lista = '\n      <li class="mapa-vacio">Esta semana todavía no cargamos eventos. Volvé en un rato.</li>'
    con_pin = sum(1 for it in items if it['sala'])
    plantilla = Template((AQUI / 'plantilla.html').read_text(encoding='utf-8'))
    return plantilla.substitute(
        page_title='Mapa cultural de La Plata: qué hay cerca tuyo · MoVeTe',
        page_description=('Mapa de teatro, música, stand up y más en La Plata, City Bell, '
                          'Gonnet, Berisso y Ensenada. Mirá qué hay cerca tuyo esta semana.'),
        page_url='https://movete.info/mapa/',
        total=len(items),
        con_pin=con_pin,
        rubros=render_rubros(datos),
        puntos=render_puntos(),
        lista=lista,
        datos=datos_cliente(datos),
        anio=hoy.year,
        v_css=_version(AQUI / 'static' / 'mapa.css'),
        v_js=_version(AQUI / 'static' / 'mapa.js'),
    )


def generar(eventos_json: str | Path, output_dir: str | Path, hoy: date | None = None) -> dict:
    hoy = hoy or hoy_argentina()
    eventos, _generado = cargar_eventos(eventos_json)
    datos = armar_datos(eventos, hoy)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(render_pagina(datos, hoy), encoding='utf-8')
    for nombre in ('mapa.css', 'mapa.js'):
        shutil.copyfile(AQUI / 'static' / nombre, out / nombre)
    # Sitemap propio, como cine/sitemap-pelis.xml: robots.txt lo declara.
    # Las páginas por zona (paso 3) se suman acá.
    (out / 'sitemap-mapa.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>https://movete.info/mapa/</loc><lastmod>{hoy.isoformat()}</lastmod></url>\n'
        '</urlset>\n', encoding='utf-8')
    return {
        'eventos': len(datos['eventos']),
        'con_pin': sum(1 for it in datos['eventos'] if it['sala']),
        'salas_con_pin': len(datos['salas']),
        'sin_coordenadas': sorted(datos['sin_coordenadas'].values()),
    }


def main() -> None:
    p = argparse.ArgumentParser(description='Genera /mapa/ de MoVeTe')
    p.add_argument('--eventos', default=str(ESPECTACULOS / 'eventos.json'))
    p.add_argument('--output', default=str(AQUI.parent / 'Movete-info' / 'mapa'))
    p.add_argument('--hoy', default=None, help='Fecha YYYY-MM-DD que se toma como hoy')
    a = p.parse_args()
    info = generar(a.eventos, a.output, date.fromisoformat(a.hoy) if a.hoy else None)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
