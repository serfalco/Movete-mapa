"""Puntos de partida para quien no comparte su ubicación.

Coordenadas sacadas de Nominatim/OSM el 21/11/2026, como las salas: nunca se
inventa ni se deduce una coordenada. Tolosa quedó afuera porque OSM no
devolvió un punto confiable (pendiente de Tres).
"""

# (clave, etiqueta, lat, lng). El primero es el centro por default del mapa.
PUNTOS_PARTIDA = [
    ('plaza-moreno', 'Plaza Moreno', -34.921364, -57.954492),
    ('plaza-san-martin', 'Plaza San Martín', -34.915301, -57.947867),
    ('plaza-italia', 'Plaza Italia', -34.910658, -57.955279),
    ('plaza-rocha', 'Plaza Rocha', -34.920876, -57.941576),
    ('meridiano-v', 'Meridiano V', -34.939012, -57.939767),
    ('city-bell', 'City Bell (Plaza Belgrano)', -34.871452, -58.046223),
    ('gonnet', 'Gonnet', -34.885240, -58.023818),
    ('berisso', 'Berisso', -34.868857, -57.882867),
    ('ensenada', 'Ensenada', -34.857490, -57.907717),
]
