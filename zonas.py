"""Zonas del mapa: una página por zona en /mapa/<zona>/.

La zona de cada sala sale de OSM, con una geocodificación inversa de sus
coordenadas (Nominatim, 21/11/2026). Dentro del casco OSM devuelve
city=La Plata; afuera, la localidad (town); y marca el barrio Meridiano V.
No se deduce nada a ojo.

Una sala que todavía no tiene coordenadas entra a una zona solo si su
dirección lo dice con todas las letras ("..., City Bell, La Plata").
"""
import re
import unicodedata

# (slug, nombre para títulos, punto de partida que centra el mapa o None)
ZONAS = [
    ('casco', 'el casco de La Plata', 'plaza-moreno'),
    ('meridiano-v', 'Meridiano V', 'meridiano-v'),
    ('tolosa', 'Tolosa', None),
    ('city-bell', 'City Bell', 'city-bell'),
    ('gonnet', 'Gonnet', 'gonnet'),
    ('berisso', 'Berisso', 'berisso'),
    ('ensenada', 'Ensenada', 'ensenada'),
]

# Meridiano V queda dentro del casco: sus salas salen en las dos páginas.
DENTRO_DE = {'meridiano-v': 'casco'}

# Slug de sala (venue_slug del nombre canónico) -> zona, según OSM.
ZONA_DE_SALA = {
    'azulunala': 'casco',
    'casa-hereje': 'casco',
    'casa-metro': 'casco',
    'casa-pulsar': 'casco',
    'casa-suiza': 'casco',
    'casa-unclan': 'casco',
    'centro-cultural-islas-malvinas': 'casco',
    'centro-cultural-pasaje-dardo-rocha': 'casco',
    'centro-cultural-viejo-almacen-el-obrero': 'meridiano-v',
    'centro-de-arte-unlp': 'casco',
    'centro-de-capacitacion-informacion-e-investigacion-educativa-ciie': 'casco',
    'cine-ecoselect-espacio-incaa': 'casco',
    'dynamo-teatro': 'meridiano-v',
    'el-teatro-bar': 'casco',
    'escenario-40': 'casco',
    'espacio-doble-t': 'casco',
    'espacio-live': 'casco',
    'espacio-medusa': 'casco',
    'espacio-satelite': 'casco',
    'espacio-sudaka': 'casco',
    'esquina-america': 'meridiano-v',
    'estudio-71': 'casco',
    'galpon-de-la-grieta-y-biblioteca-popular-la-chicharra': 'meridiano-v',
    'guajira-bar': 'casco',
    'la-compostera': 'casco',
    'la-culturosa': 'casco',
    'la-macacha-centro-cultural': 'casco',
    'la-salamanca-centro-de-cultura-y-pena': 'casco',
    'lazuli-espacio-cultural': 'casco',
    'museo-almafuerte': 'casco',
    'museo-de-ciencias-naturales-de-la-plata': 'casco',
    'observatorio-planetario-de-la-plata': 'casco',
    'pena-de-las-bellas-artes': 'casco',
    'republica-de-los-ninos': 'gonnet',
    'ruda-red-ultrapotente-de-amistad': 'meridiano-v',
    'sala-420': 'casco',
    'sociedad-platense-de-stand-up': 'casco',
    'teatro-argentino-de-la-plata': 'casco',
    'teatro-bar-cultural-la-ferreteria': 'casco',
    'teatro-coliseo-podesta': 'casco',
    'teatro-la-nonna': 'casco',
    'teatro-metro': 'casco',
    'teatro-rene-favaloro': 'casco',
    'teatro-unlp-y-biblioteca-popular-teatral-alberto-mediza': 'casco',
    'tres-empanadas-comedia': 'casco',
    # Biblioteca Popular Mafalda y Libertad: Arturo Seguí, sin página de zona.
}

# Localidades que, escritas en la dirección, alcanzan para ubicar la zona.
_LOCALIDAD = {
    'city bell': 'city-bell',
    'gonnet': 'gonnet',
    'tolosa': 'tolosa',
    'berisso': 'berisso',
    'ensenada': 'ensenada',
}


def _norm(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', str(texto or '').lower())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', texto)).strip()


def zonas_de(sala_slug: str | None, direccion: str) -> set[str]:
    """Zonas a las que pertenece un evento (vacío si no sabemos)."""
    zona = ZONA_DE_SALA.get(sala_slug or '')
    if not zona:
        d = _norm(direccion)
        zona = next((z for loc, z in _LOCALIDAD.items()
                     if re.search(rf'(^|\s){loc}(\s|$)', d)), None)
    if not zona:
        return set()
    return {zona, DENTRO_DE[zona]} if zona in DENTRO_DE else {zona}
