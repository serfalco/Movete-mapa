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
import re
import shutil
import sys
from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from string import Template
from urllib.parse import quote_plus

AQUI = Path(__file__).resolve().parent
ESPECTACULOS = Path(os.environ.get('MOVETE_ESPECTACULOS', AQUI.parent / 'movete-espectaculos'))
sys.path.insert(0, str(ESPECTACULOS))

from edicion import DIAS, MESES_ABR  # noqa: E402
from generar_edicion import (  # noqa: E402
    _ALIAS_OBRA,
    agregar_evento_fijo_stand_up,
    CATEGORY_ORDER,
    calcular_alias_obras,
    cargar_eventos,
    cat_label,
    esc,
    evento_lugar,
    evento_titulo,
    evento_url,
    hoy_argentina,
    _precio,
    normalizar_categorias,
    obra_slug,
    parse_fecha,
)
from venues import (  # noqa: E402
    VENUES_DIRECCIONES,
    _normalizar,
    venue_canonico,
    venue_info,
    venue_slug,
)

from lugares import LUGARES, TIPOS, horario_legible  # noqa: E402
from puntos_partida import PUNTOS_PARTIDA  # noqa: E402
from zonas import DENTRO_DE, ZONAS, zonas_de  # noqa: E402

# El mapa muestra de hoy en adelante: la semana que filtra la página y un día
# de margen, porque el generador corre martes, jueves y domingo.
DIAS_VENTANA = 8

# Rubros en el orden de los botones. Cine va al final: es la cartelera de
# cine clubs y espacios INCAA que trae la agenda, no la de /cine/.
ORDEN_RUBROS = [c for c in CATEGORY_ORDER if c != 'otros'] + ['cine', 'otros']

# Lugares que no son una sala: no se le pide a Tres una coordenada para ellos.
LUGARES_GENERICOS = {'la-plata', 'gran-la-plata', 'a-confirmar', 'online', 'virtual'}


# Tres Empanadas: pin con borde dorado y el aviso "Stand Up en Tres Empanadas". El resto del
# mapa queda neutral: su pin y sus eventos se ordenan y filtran como cualquiera.
SALAS_DE_LA_CASA = {'tres-empanadas-comedia'}
AVISO_URL = 'https://tresempanadas.com.ar/reservas/?utm_source=movete&utm_medium=mapa&utm_campaign=aviso'

# "Gratis (confirmados)": solo lo que lo dice con todas las letras. Que falten
# algunos no importa; que aparezca uno que no lo es, sí.
_GRATIS = re.compile(r'\b(gratis|gratuit[oa]s?|entrada (libre|liberada)|sin costo|no arancelad[oa]s?)\b')
_GORRA = re.compile(r'\ba la gorra\b')


def modo_gratis(ev: dict) -> str:
    """'gorra', 'gratis' o '' según el texto del evento (o un precio 0 de la fuente)."""
    texto = _normalizar(' '.join(str(ev.get(k) or '') for k in
                                 ('titulo', 'title', 'sinopsis', 'descripcion', 'precio_texto')))
    if _GORRA.search(texto):
        return 'gorra'
    if _GRATIS.search(texto) or _precio(ev) == 0:
        return 'gratis'
    return ''


def pines_por_coordenada() -> dict[tuple[float, float], tuple[str, dict]]:
    """Para cada coordenada, la sala del catálogo que da nombre al pin (la
    primera en VENUES_DIRECCIONES)."""
    pines: dict[tuple[float, float], tuple[str, dict]] = {}
    for nombre, *_resto in VENUES_DIRECCIONES.values():
        vc = venue_canonico(nombre)
        if vc and vc['lat'] is not None:
            pines.setdefault((vc['lat'], vc['lng']), (vc['slug'], vc))
    return pines


# Un lugar fijo a menos de esto de una sala con pin es la misma casa: no se repite.
MISMO_LUGAR_M = 60


def _metros(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat, dlng = radians(b[0] - a[0]), radians(b[1] - a[1])
    h = sin(dlat / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(dlng / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def armar_lugares(paginas_sala: set[str] | None = None) -> list[dict]:
    """Lugares fijos para el toggle "Ver también lugares".

    Primero las salas con coordenadas, con 'sala': mapa.js esconde su pin gris
    mientras esa sala tenga un evento a la vista, así nunca sale dos veces.
    Después los museos, bibliotecas y centros culturales de lugares.py que no
    caen encima de una sala.
    """
    paginas_sala = paginas_sala or set()
    out = []
    for (lat, lng), (slug, vc) in pines_por_coordenada().items():
        out.append({'id': f's-{slug}', 'nombre': vc['nombre'], 'tipo': 'sala', 'lat': lat, 'lng': lng,
                    'direccion': vc['direccion'] or '', 'horario': None,
                    'zonas': zonas_de(slug, vc['direccion'] or ''),
                    'url': f'/en-vivo/sala/{slug}/' if slug in paginas_sala else '', 'sala': slug})
    salas = [(o['lat'], o['lng']) for o in out]
    for slug, nombre, tipo, lat, lng, direccion, oh, zona, _osm in LUGARES:
        if any(_metros((lat, lng), c) < MISMO_LUGAR_M for c in salas):
            continue
        zonas = set()
        if zona:
            zonas = {zona, DENTRO_DE[zona]} if zona in DENTRO_DE else {zona}
        out.append({'id': f'l-{slug}', 'nombre': nombre, 'tipo': tipo, 'lat': lat, 'lng': lng,
                    'direccion': direccion, 'horario': horario_legible(oh), 'zonas': zonas,
                    'url': '', 'sala': None})
    return out


def render_lugares(lugares: list[dict], salas_con_eventos: set[str]) -> str:
    """Lista indexable de los lugares fijos, plegada debajo de la de eventos.
    No repite las salas que esta semana ya salen con eventos."""
    fijos = [lu for lu in lugares if not lu['sala'] or lu['sala'] not in salas_con_eventos]
    if not fijos:
        return ''
    fijos.sort(key=lambda lu: (lu['tipo'] == 'sala', _normalizar(lu['nombre'])))
    filas = []
    for lu in fijos:
        nombre = esc(lu['nombre'])
        if lu['url']:
            nombre = f'<a href="{esc(lu["url"])}">{nombre}</a>'
        detalle = ' · '.join(esc(x) for x in (TIPOS.get(lu['tipo'], ''), lu['direccion'], lu['horario']) if x)
        llegar = f"https://www.google.com/maps/dir/?api=1&destination={lu['lat']},{lu['lng']}"
        filas.append(f'<li><strong>{nombre}</strong>' + (f' <span>{detalle}</span>' if detalle else '')
                     + f' <a class="mapa-llegar" href="{esc(llegar)}" target="_blank" rel="noopener"'
                     f' aria-label="Cómo llegar a {esc(lu["nombre"])} en Google Maps">Cómo llegar</a></li>')
    return ('<details class="mapa-lugares-lista">\n          <summary>Lugares para visitar '
            f'<span>{len(fijos)}</span></summary>\n          <ul>\n            '
            + '\n            '.join(filas) + '\n          </ul>\n        </details>')


def _hora(f: datetime, sin_hora: bool) -> str:
    return '' if sin_hora else f.strftime('%H:%M')


def armar_datos(eventos: list[dict], hoy: date, dias: int = DIAS_VENTANA) -> dict:
    """Eventos de la ventana, salas con pin y salas a las que les falta.

    Una sala sin coordenadas confirmadas no lleva pin, pero sus eventos salen
    igual en la lista. Esas salas quedan en 'sin_coordenadas' para pedírselas
    a Tres.
    """
    # Tres Empanadas abre todos los viernes: el show fijo entra cada viernes de
    # la ventana, como en En Vivo (si una fuente ya lo trae, no se repite). Los
    # jueves abre algunos nomás: esos salen solo si vienen en la cartelera.
    for d in range(dias):
        dia = hoy + timedelta(days=d)
        if dia.weekday() == 4:
            eventos = agregar_evento_fijo_stand_up(eventos, dia)
    eventos = normalizar_categorias(eventos)
    _ALIAS_OBRA.clear()
    _ALIAS_OBRA.update(calcular_alias_obras(eventos))

    desde = datetime.combine(hoy, time.min)
    hasta = desde + timedelta(days=dias)
    pines = pines_por_coordenada()
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
            # Dos nombres en el mismo lugar (Teatro Metro y Casa Metro; Tres
            # Empanadas y su show de los viernes) van en un solo pin.
            sala, pin = pines.get((vc['lat'], vc['lng']), (vc['slug'], vc))
            salas.setdefault(sala, {
                'nombre': pin['nombre'],
                'direccion': pin['direccion'],
                'lat': vc['lat'],
                'lng': vc['lng'],
                'url': f"/en-vivo/sala/{sala}/",
                'casa': sala in SALAS_DE_LA_CASA,
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
            'zonas': zonas_de(vc['slug'] if vc else None, direccion),
            'gratis': modo_gratis(ev),
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
    gratis_html = ''
    if item['gratis']:
        gratis_html = ('\n          <p class="pill mapa-gratis">'
                       + ('A la gorra' if item['gratis'] == 'gorra' else 'Gratis') + '</p>')
    return f"""
      <li class="event-card mapa-item" id="{item['id']}" data-category="{esc(cat)}"
          data-inicio="{item['inicio']}" data-sin-hora="{'1' if item['sin_hora'] else ''}"
          data-sala="{esc(item['sala'] or '')}" data-gratis="{esc(item['gratis'])}">
        <div class="event-card-topline">
          <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
          <p class="pill">{esc(cat_label(cat))}</p>{gratis_html}
          <p class="mapa-dist" hidden></p>
        </div>
        <h3>{titulo_html}</h3>
        <p class="event-meta">{meta}</p>{entradas}{sin_pin}
        <div class="mapa-item-acciones">{llegar_html}
          <button type="button" class="mapa-ver" data-ver="{esc(item['sala'] or '')}"{'' if item['sala'] else ' hidden'}>Ver en el mapa</button>
        </div>
      </li>"""


def datos_cliente(datos: dict, centro: tuple[float, float] | None = None,
                  casa: dict | None = None, lugares: list[dict] | None = None) -> str:
    """JSON que lee mapa.js. Seguro para ir dentro de <script>."""
    eventos = []
    for it in datos['eventos']:
        e = {'id': it['id'], 't': it['titulo'], 'i': it['inicio'], 'sh': it['sin_hora'],
             'c': it['cat'], 's': it['sala'], 'u': it['link']}
        if it['gratis']:
            e['g'] = it['gratis']
        pin = datos['salas'].get(it['sala']) if it['sala'] else None
        if pin and it['lugar'] and it['lugar'] != pin['nombre']:
            e['l'] = it['lugar']   # otro nombre en el mismo pin (Casa Metro en Teatro Metro)
        eventos.append(e)
    rubros = {c: cat_label(c) for c in ORDEN_RUBROS}
    payload = {
        'eventos': eventos,
        'salas': datos['salas'],
        'puntos': [{'id': k, 'nombre': n, 'lat': la, 'lng': lo} for k, n, la, lo in PUNTOS_PARTIDA],
        'rubros': rubros,
    }
    if centro:
        payload['centro'] = {'lat': centro[0], 'lng': centro[1]}
    if casa:
        payload['casa'] = casa
    if lugares:
        payload['lugares'] = []
        for lu in lugares:
            x = {'id': lu['id'], 'n': lu['nombre'], 't': TIPOS.get(lu['tipo'], ''), 'k': lu['tipo'],
                 'lat': lu['lat'], 'lng': lu['lng']}
            for clave, campo in (('h', 'horario'), ('d', 'direccion'), ('u', 'url'), ('s', 'sala')):
                if lu[campo]:
                    x[clave] = lu[campo]
            payload['lugares'].append(x)
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


def datos_casa(datos: dict) -> dict | None:
    """Lo que necesita el aviso de Tres Empanadas: dónde queda y sus próximas
    fechas reales (las que trae la cartelera, nada inventado)."""
    vc = venue_canonico('Tres Empanadas Comedia')
    if not vc or vc['lat'] is None:
        return None
    proximas = [{'i': it['inicio'], 'sh': it['sin_hora']}
                for it in datos['eventos'] if it['sala'] in SALAS_DE_LA_CASA]
    return {'nombre': 'Tres Empanadas', 'url': AVISO_URL,
            'lat': vc['lat'], 'lng': vc['lng'], 'proximas': proximas}


def render_aviso(casa: dict | None, datos: dict) -> str:
    """Aviso fijo abajo. Un solo link y con la marca como texto: MoVeTe no
    compite con Tres Empanadas en búsquedas genéricas. mapa.js actualiza la
    fecha (saca las que ya pasaron) y suma la distancia si hay ubicación."""
    if not casa:
        return ''
    proximo = next((it for it in datos['eventos'] if it['sala'] in SALAS_DE_LA_CASA), None)
    if proximo:
        f = proximo['f']
        cuando = DIAS[f.weekday()][:3].lower() + ('' if proximo['sin_hora'] else ' ' + f.strftime('%H:%M'))
    else:
        cuando = 'Ver próximas fechas'
    return f"""<aside class="mapa-casa" aria-label="Stand Up en Tres Empanadas">
    <span class="mapa-casa-texto">Stand Up en <a href="{esc(casa['url'])}">{esc(casa['nombre'])}</a> · <span class="mapa-casa-cuando">{esc(cuando)}</span><span class="mapa-casa-dist"></span></span>
  </aside>"""


def render_gratis(datos: dict) -> str:
    """Filtro "Gratis (confirmados)": solo si esta semana hay alguno."""
    if not any(it['gratis'] for it in datos['eventos']):
        return ''
    return ('<button type="button" class="mapa-chip mapa-chip-gratis" data-gratis-filtro="" '
            'aria-pressed="false">Gratis (confirmados)</button>')


def render_puntos() -> str:
    return '\n            '.join(f'<option value="{esc(k)}">{esc(n)}</option>' for k, n, _la, _lo in PUNTOS_PARTIDA)


def _version(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:10]


def datos_de_zona(datos: dict, zona: str) -> dict:
    """Los datos recortados a una zona: sus eventos y las salas con pin."""
    eventos = [it for it in datos['eventos'] if zona in it['zonas']]
    usadas = {it['sala'] for it in eventos if it['sala']}
    return {**datos, 'eventos': eventos,
            'salas': {k: v for k, v in datos['salas'].items() if k in usadas}}


def cuentas_por_zona(datos: dict) -> dict[str, int]:
    return {z: sum(1 for it in datos['eventos'] if z in it['zonas']) for z, _n, _p in ZONAS}


def render_zonas(cuentas: dict[str, int], actual: str | None) -> str:
    """Enlazado interno entre el mapa general y las zonas con eventos."""
    links = []
    if actual:
        links.append('<a href="/mapa/">Todo Gran La Plata</a>')
    for z, nombre, _p in ZONAS:
        n = cuentas.get(z, 0)
        if not n:
            continue
        corto = 'Casco' if z == 'casco' else nombre
        if z == actual:
            links.append(f'<a href="/mapa/{z}/" aria-current="page">{esc(corto)} <span>{n}</span></a>')
        else:
            links.append(f'<a href="/mapa/{z}/">{esc(corto)} <span>{n}</span></a>')
    if len(links) <= 1:
        return ''
    return ('<nav class="mapa-zonas" aria-label="Zonas">\n        <h2>Por zona</h2>\n        '
            + '\n        '.join(links) + '\n      </nav>')


def render_pagina(datos: dict, hoy: date, zona: str | None = None,
                  cuentas: dict[str, int] | None = None,
                  paginas_sala: set[str] | None = None) -> str:
    cuentas = cuentas if cuentas is not None else cuentas_por_zona(datos)
    lugares = armar_lugares(paginas_sala)
    if zona:
        lugares = [lu for lu in lugares if zona in lu['zonas']]
    # El aviso va en todas las páginas, también en las zonas donde TE no está.
    casa = datos_casa(datos)
    aviso = render_aviso(casa, datos)
    centro = None
    if zona:
        _z, nombre_zona, punto = next(z for z in ZONAS if z[0] == zona)
        datos = datos_de_zona(datos, zona)
        centro = next(((la, lo) for k, _n, la, lo in PUNTOS_PARTIDA if k == punto), None)
    items = datos['eventos']
    lista = ''.join(render_item(it, datos['salas']) for it in items)
    if not items:
        donde = f' en {nombre_zona}' if zona else ''
        lista = (f'\n      <li class="mapa-vacio">Esta semana todavía no cargamos eventos{esc(donde)}. '
                 '<a href="/mapa/">Mirá todo el mapa →</a></li>')
    if zona:
        page_title = f'Qué hacer esta semana en {nombre_zona} · Mapa cultural · MoVeTe'
        page_description = (f'Teatro, música, stand up y más en {nombre_zona} esta semana: '
                            f'{len(items)} eventos en el mapa, con cómo llegar.')
        h1 = f'Qué hacer esta semana en {nombre_zona}'
        eyebrow = f'Mapa cultural · {nombre_zona[0].upper() + nombre_zona[1:]}'
        lead = f'Lo que hay esta semana en {nombre_zona}, en el mapa y en la lista.'
        page_url = f'https://movete.info/mapa/{zona}/'
        lista_titulo = f'Esta semana en {nombre_zona}'
    else:
        page_title = 'Mapa cultural de La Plata: qué hay cerca tuyo · MoVeTe'
        page_description = ('Mapa de teatro, música, stand up y más en La Plata, City Bell, '
                            'Gonnet, Berisso y Ensenada. Mirá qué hay cerca tuyo esta semana.')
        h1 = 'Qué hay cerca tuyo'
        eyebrow = 'Mapa cultural · Gran La Plata'
        lead = 'Teatro, música, stand up y más en La Plata, City Bell, Gonnet, Berisso y Ensenada.'
        page_url = 'https://movete.info/mapa/'
        lista_titulo = 'Esta semana en el mapa'
    plantilla = Template((AQUI / 'plantilla.html').read_text(encoding='utf-8'))
    return plantilla.substitute(
        page_title=esc(page_title),
        page_description=esc(page_description),
        page_url=page_url,
        # Una zona sin eventos existe (no rompe links viejos) pero no se indexa.
        robots='<meta name="robots" content="noindex, follow">' if not items else '',
        eyebrow=esc(eyebrow),
        h1=esc(h1),
        lead=esc(lead),
        lista_titulo=esc(lista_titulo),
        total=len(items),
        rubros=render_rubros(datos),
        puntos=render_puntos(),
        lista=lista,
        zonas=render_zonas(cuentas, zona),
        gratis=render_gratis(datos),
        ver_lugares=('<button type="button" class="mapa-chip mapa-chip-lugares" data-lugares="" '
                     'aria-pressed="false">Ver también lugares</button>') if lugares else '',
        lugares=render_lugares(lugares, set(datos['salas'])),
        aviso=aviso,
        datos=datos_cliente(datos, centro, casa, lugares),
        anio=hoy.year,
        v_css=_version(AQUI / 'static' / 'mapa.css'),
        v_js=_version(AQUI / 'static' / 'mapa.js'),
    )


def escribir_sitemap(out: Path, cuentas: dict[str, int], hoy: date) -> None:
    """Sitemap propio, como cine/sitemap-pelis.xml: robots.txt lo declara.
    Solo entran las zonas con eventos (las vacías van con noindex)."""
    urls = ['https://movete.info/mapa/'] + [
        f'https://movete.info/mapa/{z}/' for z, _n, _p in ZONAS if cuentas.get(z)]
    filas = ''.join(f'  <url><loc>{u}</loc><lastmod>{hoy.isoformat()}</lastmod></url>\n' for u in urls)
    (out / 'sitemap-mapa.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{filas}</urlset>\n', encoding='utf-8')


def generar(eventos_json: str | Path, output_dir: str | Path, hoy: date | None = None) -> dict:
    hoy = hoy or hoy_argentina()
    eventos, _generado = cargar_eventos(eventos_json)
    datos = armar_datos(eventos, hoy)
    cuentas = cuentas_por_zona(datos)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Las páginas de sala las escribe movete-espectaculos antes que el mapa:
    # un lugar fijo enlaza la suya solo si existe.
    dir_salas = out.parent / 'en-vivo' / 'sala'
    paginas_sala = {d.name for d in dir_salas.iterdir() if d.is_dir()} if dir_salas.is_dir() else set()
    (out / 'index.html').write_text(
        render_pagina(datos, hoy, cuentas=cuentas, paginas_sala=paginas_sala), encoding='utf-8')
    for z, _n, _p in ZONAS:
        (out / z).mkdir(exist_ok=True)
        (out / z / 'index.html').write_text(
            render_pagina(datos, hoy, zona=z, cuentas=cuentas, paginas_sala=paginas_sala),
            encoding='utf-8')
    for nombre in ('mapa.css', 'mapa.js'):
        shutil.copyfile(AQUI / 'static' / nombre, out / nombre)
    escribir_sitemap(out, cuentas, hoy)
    return {
        'eventos': len(datos['eventos']),
        'con_pin': sum(1 for it in datos['eventos'] if it['sala']),
        'salas_con_pin': len(datos['salas']),
        'lugares_fijos': len(armar_lugares()),
        'por_zona': cuentas,
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
