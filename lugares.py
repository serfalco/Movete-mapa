"""Lugares fijos del mapa: museos, bibliotecas y centros culturales.

Se ven con el toggle "Ver también lugares", con un pin gris. Las salas de
movete-espectaculos/venues.py que tienen coordenadas también salen como lugar
fijo mientras no tengan un evento a la vista: una sala con eventos se muestra
como evento, nunca dos veces. Por eso acá no se repite ninguna sala.

Todo sale de OpenStreetMap (consulta del 21/11/2026): nombre, coordenadas,
dirección y horario (`opening_hours`), tal como están cargados ahí. La zona
sale de una geocodificación inversa de Nominatim, igual que en zonas.py.
No se deduce ni se completa nada a ojo: si OSM no trae la dirección o el
horario, el lugar sale sin ellos. Cada uno guarda su id de OSM para poder
revisarlo.

Los dudosos no se cargaron: están en el PR, para que los vea Tres.
"""
import re

TIPOS = {
    'museo': 'Museo',
    'biblioteca': 'Biblioteca',
    'centro-cultural': 'Centro cultural',
}   # las salas van sin rótulo: algunas son museos o la República de los Niños

# slug, nombre, tipo, lat, lng, dirección (de OSM o ''), horario OSM o None,
# zona (slug de zonas.py o None), id de OSM.
LUGARES = [
    # Museos
    ('museo-de-fisica', 'Museo de Física', 'museo', -34.907836, -57.943163,
     'Calle 115', 'Mo,We 14:00-17:00, Tu-Fr 09:30-12:30', 'casco', 'node/614233256'),
    ('museo-de-la-catedral', 'Museo de la Catedral de La Plata', 'museo', -34.922455, -57.955694,
     '', None, 'casco', 'node/1867429693'),
    ('museo-del-arte-y-la-memoria', 'Museo del Arte y la Memoria', 'museo', -34.91759, -57.950431,
     '', None, 'casco', 'node/3330275910'),
    ('museo-bellas-artes-pettoruti', 'Museo Provincial de Bellas Artes Emilio Pettoruti', 'museo',
     -34.913794, -57.947558, 'Avenida 51', None, 'casco', 'node/3497294736'),
    ('museo-instrumentos-azzarini', 'Museo de Instrumentos Musicales Dr. Emilio Azzarini', 'museo',
     -34.911349, -57.953666, 'Calle 45 N° 582', 'Mo-Fr 09:00-18:00', 'casco', 'node/4002995831'),
    ('museo-dardo-rocha', 'Museo y Archivo Dardo Rocha', 'museo', -34.920799, -57.956381,
     'Calle 50 N° 933', 'Mo-Su 10:00-13:00,15:00-18:00', 'casco', 'node/4235795777'),
    ('museo-beato-angelico', 'Museo de Arte Contemporáneo Beato Angélico', 'museo', -34.92147, -57.961532,
     'Calle 47', None, 'casco', 'node/5380558916'),
    # Bibliotecas
    ('biblioteca-romero-delgado', 'Biblioteca Popular "Francisco Romero Delgado"', 'biblioteca',
     -34.916502, -57.953141, 'Calle 49 N° 731',
     'Mo-Tu 13:00-19:00; We 08:30-14:30; Th-Fr 13:00-19:00', 'casco', 'node/3330235439'),
    ('biblioteca-lopez-merino', 'Biblioteca López Merino', 'biblioteca', -34.918333, -57.955044,
     'Calle 49 N° 835', 'Mo-Fr 08:00-20:00', 'casco', 'node/4235795770'),
    # Sabato: OSM dice "Th-Fr 08:30-18:00", igual que otras dos bibliotecas
    # cargadas juntas; parece un error de carga y no se muestra.
    ('biblioteca-ernesto-sabato', 'Biblioteca Pública Central Ernesto Sabato', 'biblioteca',
     -34.911561, -57.950293, 'Calle 47 N° 510', None, 'casco', 'node/4260983526'),
    ('biblioteca-del-otro-lado-del-arbol', 'Biblioteca Popular Del otro lado del árbol', 'biblioteca',
     -34.932608, -57.940884, '', None, 'casco', 'way/336735950'),
    ('biblioteca-florentino-ameghino-city-bell', 'Biblioteca Popular Florentino Ameghino', 'biblioteca',
     -34.86906, -58.044646, 'Calle 13c N° 473', None, 'city-bell', 'node/3831756657'),
    ('biblioteca-eduardo-galeano', 'Biblioteca Popular Eduardo Galeano', 'biblioteca',
     -34.877291, -58.052038, 'Calle 19', 'Mo-Fr 13:00-22:00; Sa 13:00-18:00', 'city-bell',
     'node/4686963197'),
    # Villa Elisa: sin página de zona, solo en el mapa general.
    ('biblioteca-alejo-iglesias', 'Biblioteca Popular Alejo Iglesias', 'biblioteca',
     -34.852064, -58.080443, 'Calle 6 N° 1086', None, None, 'node/5635881006'),
    # Centros culturales
    ('centro-cultural-estacion-provincial', 'Centro Cultural Estación Provincial', 'centro-cultural',
     -34.939734, -57.939053, '', None, 'meridiano-v', 'way/200509603'),
    ('centro-cultural-daniel-omar-favero', 'Centro Cultural Daniel Omar Favero', 'centro-cultural',
     -34.898884, -57.950178, '', None, 'casco', 'way/749308728'),
    ('multiespacio-maga', 'Multiespacio MAGA', 'centro-cultural', -34.852035, -58.086107,
     '', None, None, 'node/11026123046'),
    ('centro-cultural-maca', 'Centro Cultural MACÁ', 'centro-cultural', -34.854909, -58.072448,
     '', None, None, 'way/567586638'),
]

_DIAS = {'Mo': 'lun', 'Tu': 'mar', 'We': 'mié', 'Th': 'jue', 'Fr': 'vie', 'Sa': 'sáb', 'Su': 'dom',
         'PH': 'feriados'}
_RANGO_DIAS = re.compile(r'^(Mo|Tu|We|Th|Fr|Sa|Su|PH)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?$')
_RANGO_HORA = re.compile(r'^(\d{2}):(\d{2})-(\d{2}):(\d{2})$')


def _hora(h: str, m: str) -> str:
    return str(int(h)) + ('' if m == '00' else ':' + m)


def horario_legible(oh: str | None) -> str | None:
    """'Mo-Fr 09:00-18:00' -> 'lun a vie 9 a 18'. Solo entiende la forma
    simple de opening_hours; si viene algo más raro devuelve None y el lugar
    sale sin horario (mejor nada que un horario mal leído)."""
    if not oh:
        return None
    partes = []
    # Reglas separadas por ";" o por ", " antes de otro día.
    for regla in re.split(r';\s*|,\s+(?=[A-Z][a-z])', oh.strip()):
        m = re.match(r'^(\S+)\s+(\S+)$', regla.strip())
        if not m:
            return None
        dias = []
        for d in m.group(1).split(','):
            r = _RANGO_DIAS.match(d)
            if not r:
                return None
            dias.append(_DIAS[r.group(1)] + (' a ' + _DIAS[r.group(2)] if r.group(2) else ''))
        horas = []
        for h in m.group(2).split(','):
            r = _RANGO_HORA.match(h)
            if not r:
                return None
            horas.append(_hora(r.group(1), r.group(2)) + ' a ' + _hora(r.group(3), r.group(4)))
        partes.append(' y '.join(dias) + ' ' + ' y '.join(horas))
    return '; '.join(partes)
