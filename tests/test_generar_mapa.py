import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generar_mapa import armar_datos, generar, modo_gratis, render_pagina  # noqa: E402

HOY = date(2026, 11, 21)


def ev(titulo, fecha, lugar, categoria='teatro', **extra):
    return {'titulo': titulo, 'fecha': fecha, 'lugar': lugar, 'categoria': categoria, **extra}


EVENTOS = [
    ev('Sociedad Platense de Stand Up', '2026-11-21 21:30:00', 'Tres Empanadas Comedia', 'stand-up',
       url='https://tresempanadas.com.ar/reservas/'),
    ev('Obra en sala sin coordenadas', '2026-11-22 20:00:00', 'Telón Negro Teatro'),
    ev('Feria en un lugar suelto', '2026-11-23 11:00:00', 'Galpón inventado', 'ferias'),
    ev('Show que ya pasó', '2026-11-19 21:00:00', 'Casa Hereje', 'musica'),
    ev('Show muy lejano', '2026-12-25 21:00:00', 'Casa Hereje', 'musica'),
    ev('Recital', '2026-11-22 22:00:00', 'Casa Hereje', 'musica'),
    ev('Recital', '2026-11-22 22:00:00', 'CASA HEREJE', 'musica'),  # misma función, otra fuente
    ev('Sin fecha', '', 'Casa Hereje'),
    ev('Algo en La Plata', '2026-11-22 18:00:00', 'La Plata', 'otros'),
    ev('Milonga', '2026-11-22 21:00:00', 'Dynamo Teatro', 'danza'),
    ev('Jazz en City Bell', '2026-11-22 21:00:00', 'Desafinado Club', 'musica'),
]


class ArmarDatosTests(unittest.TestCase):
    def setUp(self):
        self.datos = armar_datos(EVENTOS, HOY)
        self.por_titulo = {e['titulo']: e for e in self.datos['eventos']}

    def test_ventana_de_la_semana(self):
        self.assertNotIn('Show que ya pasó', self.por_titulo)
        self.assertNotIn('Show muy lejano', self.por_titulo)
        self.assertNotIn('Sin fecha', self.por_titulo)

    def test_sala_confirmada_lleva_pin(self):
        te = self.por_titulo['Sociedad Platense de Stand Up']
        self.assertEqual(te['sala'], 'tres-empanadas-comedia')
        sala = self.datos['salas']['tres-empanadas-comedia']
        self.assertAlmostEqual(sala['lat'], -34.923728)

    def test_sala_sin_coordenadas_sale_en_la_lista_sin_pin(self):
        sin = self.por_titulo['Obra en sala sin coordenadas']
        self.assertIsNone(sin['sala'])
        self.assertIn('telon-negro-teatro', self.datos['sin_coordenadas'])
        self.assertIsNone(self.por_titulo['Feria en un lugar suelto']['sala'])
        self.assertIn('galpon-inventado', self.datos['sin_coordenadas'])

    def test_lugar_generico_no_se_pide(self):
        self.assertIn('Algo en La Plata', self.por_titulo)
        self.assertNotIn('la-plata', self.datos['sin_coordenadas'])

    def test_misma_funcion_de_dos_fuentes_va_una_vez(self):
        self.assertEqual(sum(1 for e in self.datos['eventos'] if e['titulo'] == 'Recital'), 1)

    def test_ordenado_por_hora(self):
        inicios = [e['inicio'] for e in self.datos['eventos']]
        self.assertEqual(inicios, sorted(inicios))


class PaginaTests(unittest.TestCase):
    def setUp(self):
        self.html = render_pagina(armar_datos(EVENTOS, HOY), HOY)

    def test_lista_indexable_en_el_html(self):
        # Google casi no lee el mapa en JS: los eventos tienen que estar en el HTML.
        self.assertIn('Sociedad Platense de Stand Up', self.html)
        self.assertIn('Obra en sala sin coordenadas', self.html)
        self.assertIn('href="/en-vivo/sala/tres-empanadas-comedia/"', self.html)
        self.assertIn('<link rel="canonical" href="https://movete.info/mapa/">', self.html)

    def test_como_llegar_va_a_google_maps(self):
        self.assertIn('https://www.google.com/maps/dir/?api=1&amp;destination=-34.923728,-57.971826', self.html)

    def test_sala_sin_pin_lo_avisa(self):
        self.assertIn('Sin ubicación en el mapa todavía', self.html)

    def test_datos_del_cliente_son_json_valido_y_seguros(self):
        m = re.search(r'<script id="mapa-datos" type="application/json">(.*?)</script>', self.html, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn('<', m.group(1))
        datos = json.loads(m.group(1))
        self.assertIn('tres-empanadas-comedia', datos['salas'])
        self.assertTrue(datos['puntos'])
        ids = {e['id'] for e in datos['eventos']}
        for i in ids:
            self.assertIn(f'id="{i}"', self.html)

    def test_aviso_de_privacidad_y_sumar(self):
        self.assertIn('no llega a MoVeTe', self.html)
        self.assertIn('href="/sumar/"', self.html)

    def test_no_usa_tiles_de_osm(self):
        # La política de tiles de OSM no permite tráfico de un sitio en producción.
        js = (Path(__file__).resolve().parent.parent / 'static' / 'mapa.js').read_text(encoding='utf-8')
        self.assertNotIn('tile.openstreetmap.org', self.html + js)
        self.assertIn('tiles.openfreemap.org', js)


class ZonasTests(unittest.TestCase):
    def setUp(self):
        self.datos = armar_datos(EVENTOS, HOY)
        self.por_titulo = {e['titulo']: e for e in self.datos['eventos']}

    def test_zona_de_sala_con_coordenadas(self):
        self.assertEqual(self.por_titulo['Sociedad Platense de Stand Up']['zonas'], {'casco'})

    def test_meridiano_v_tambien_es_casco(self):
        self.assertEqual(self.por_titulo['Milonga']['zonas'], {'meridiano-v', 'casco'})

    def test_sala_sin_coordenadas_entra_si_la_direccion_lo_dice(self):
        # Desafinado no tiene pin, pero su dirección dice "City Bell".
        jazz = self.por_titulo['Jazz en City Bell']
        self.assertIsNone(jazz['sala'])
        self.assertEqual(jazz['zonas'], {'city-bell'})
        self.assertEqual(self.por_titulo['Obra en sala sin coordenadas']['zonas'], set())

    def test_pagina_de_zona(self):
        html = render_pagina(self.datos, HOY, zona='city-bell')
        self.assertIn('<h1>Qué hacer esta semana en City Bell</h1>', html)
        self.assertIn('<link rel="canonical" href="https://movete.info/mapa/city-bell/">', html)
        self.assertIn('Jazz en City Bell', html)
        self.assertNotIn('Sociedad Platense de Stand Up', html)
        self.assertNotIn('noindex', html)
        self.assertIn('"centro":{"lat":-34.871452', html)

    def test_enlaces_entre_zonas(self):
        general = render_pagina(self.datos, HOY)
        self.assertIn('href="/mapa/casco/"', general)
        self.assertIn('href="/mapa/city-bell/"', general)
        self.assertNotIn('href="/mapa/ensenada/"', general)  # vacía: no se enlaza
        zona = render_pagina(self.datos, HOY, zona='casco')
        self.assertIn('href="/mapa/">Todo Gran La Plata', zona)
        self.assertIn('href="/mapa/casco/" aria-current="page"', zona)


class GratisTests(unittest.TestCase):
    def test_modo_gratis_por_texto(self):
        self.assertEqual(modo_gratis(ev('Feria gratis', '', 'x')), 'gratis')
        self.assertEqual(modo_gratis(ev('Recital', '', 'x', sinopsis='Entrada libre y gratuita')), 'gratis')
        self.assertEqual(modo_gratis(ev('Impro', '', 'x', descripcion='Show a la gorra')), 'gorra')
        self.assertEqual(modo_gratis(ev('Obra', '', 'x', precio_texto='$8000')), '')
        self.assertEqual(modo_gratis(ev('Gratitud', '', 'x')), '')  # palabra entera

    def test_filtro_solo_si_hay_gratis(self):
        datos = armar_datos(EVENTOS, HOY)
        self.assertNotIn('Gratis (confirmados)', render_pagina(datos, HOY))
        con = EVENTOS + [ev('Feria gratis', '2026-11-22 11:00:00', 'Casa Hereje', 'ferias')]
        html = render_pagina(armar_datos(con, HOY), HOY)
        self.assertIn('data-gratis-filtro=""', html)
        self.assertIn('>Gratis (confirmados)</button>', html)
        self.assertIn('data-gratis="gratis"', html)
        self.assertIn('"g":"gratis"', html)


class DeLaCasaTests(unittest.TestCase):
    def setUp(self):
        self.datos = armar_datos(EVENTOS, HOY)
        self.html = render_pagina(self.datos, HOY)

    def aviso(self, html):
        m = re.search(r'<aside class="mapa-casa".*?</aside>', html, re.S)
        self.assertIsNotNone(m)
        return m.group(0)

    def test_aviso_con_un_solo_link_y_la_marca(self):
        aviso = self.aviso(self.html)
        self.assertIn('De la casa', aviso)
        links = re.findall(r'<a [^>]*>(.*?)</a>', aviso)
        self.assertEqual(links, ['Tres Empanadas'])
        self.assertNotIn('stand up en La Plata', aviso.lower())
        self.assertIn('utm_source=movete', aviso)

    def test_aviso_tambien_en_las_zonas(self):
        # Aunque la zona no tenga a Tres Empanadas, el aviso sale con su fecha.
        aviso = self.aviso(render_pagina(self.datos, HOY, zona='city-bell'))
        self.assertIn('Tres Empanadas', aviso)
        self.assertNotIn('Ver próximas fechas', aviso)

    def test_sin_fechas_dice_ver_proximas(self):
        sin_te = [e for e in EVENTOS if e['lugar'] != 'Tres Empanadas Comedia']
        aviso = self.aviso(render_pagina(armar_datos(sin_te, HOY), HOY))
        self.assertIn('Ver próximas fechas', aviso)

    def test_pin_de_la_casa_y_el_resto_igual(self):
        salas = self.datos['salas']
        self.assertTrue(salas['tres-empanadas-comedia']['casa'])
        self.assertFalse(any(s['casa'] for k, s in salas.items() if k != 'tres-empanadas-comedia'))

    def test_misma_coordenada_un_solo_pin(self):
        # Sociedad Platense de Stand Up es en Tres Empanadas: comparten pin.
        con = EVENTOS + [ev('Otra función', '2026-11-22 21:30:00', 'Sociedad Platense de Stand Up', 'stand-up')]
        datos = armar_datos(con, HOY)
        otra = next(e for e in datos['eventos'] if e['titulo'] == 'Otra función')
        self.assertEqual(otra['sala'], 'tres-empanadas-comedia')


class GenerarTests(unittest.TestCase):
    def test_escribe_la_pagina_y_los_estaticos(self):
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / 'eventos.json'
            entrada.write_text(json.dumps({'eventos': EVENTOS}), encoding='utf-8')
            info = generar(entrada, Path(tmp) / 'mapa', hoy=HOY)
            for nombre in ('index.html', 'mapa.css', 'mapa.js', 'sitemap-mapa.xml'):
                self.assertTrue((Path(tmp) / 'mapa' / nombre).exists(), nombre)
            sitemap = (Path(tmp) / 'mapa' / 'sitemap-mapa.xml').read_text(encoding='utf-8')
            self.assertIn('<loc>https://movete.info/mapa/</loc><lastmod>2026-11-21</lastmod>', sitemap)
            self.assertIn('<loc>https://movete.info/mapa/city-bell/</loc>', sitemap)
            self.assertNotIn('/mapa/ensenada/', sitemap)  # sin eventos: fuera del sitemap
            vacia = (Path(tmp) / 'mapa' / 'ensenada' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('noindex', vacia)
            self.assertEqual(info['salas_con_pin'], 3)
            for z in ('casco', 'meridiano-v', 'city-bell', 'ensenada'):
                self.assertTrue((Path(tmp) / 'mapa' / z / 'index.html').exists(), z)
            self.assertIn('Telón Negro Teatro', info['sin_coordenadas'])


if __name__ == '__main__':
    unittest.main()
