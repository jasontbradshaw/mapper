#!/usr/bin/env python

import mapper
from mapper import Polygon, Tile, NullTileStore, FileTileStore, MongoTileStore
from pprint import pprint

tile_m = Tile.from_mercator(30.2832, -97.7362, 18)
tile_g = Tile.from_google(59902, 107915, 18)
print "Mercator:", tile_m.latitude, tile_m.longitude, tile_m.zoom
print "Google:", tile_g.x, tile_g.y, tile_g.zoom
assert tile_m == tile_g

# get us an area
print "indian:"
points = [
    (2, 3),
    (7, 1),
    (13, 5),
    (13, 11),
    (7, 7),
    (2, 9),
]
pprint(Polygon.get_area(points))
print

print "turquoise:"
points = [
    (4, 1),
    (1, 11),
    (9, 5),
    (12, 8),
    (12, 1)
]
pprint(Polygon.get_area(points))
print

# these tiles represent roughly the UT Austin campus
ut_corners = [
    Tile.from_google(59902, 107915, 18),
    Tile.from_google(59906, 107915, 18),
    Tile.from_google(59906, 107919, 18),
    Tile.from_google(59902, 107919, 18)
]

# all the tiles in the area encompassed by the corners
ut_tiles = [
    Tile.from_google(59902, 107915, 18),
    Tile.from_google(59903, 107915, 18),
    Tile.from_google(59904, 107915, 18),
    Tile.from_google(59905, 107915, 18),
    Tile.from_google(59906, 107915, 18),

    Tile.from_google(59902, 107916, 18),
    Tile.from_google(59903, 107916, 18),
    Tile.from_google(59904, 107916, 18),
    Tile.from_google(59905, 107916, 18),
    Tile.from_google(59906, 107916, 18),

    Tile.from_google(59902, 107917, 18),
    Tile.from_google(59903, 107917, 18),
    Tile.from_google(59904, 107917, 18),
    Tile.from_google(59905, 107917, 18),
    Tile.from_google(59906, 107917, 18),

    Tile.from_google(59902, 107918, 18),
    Tile.from_google(59903, 107918, 18),
    Tile.from_google(59904, 107918, 18),
    Tile.from_google(59905, 107918, 18),
    Tile.from_google(59906, 107918, 18),

    Tile.from_google(59902, 107919, 18),
    Tile.from_google(59903, 107919, 18),
    Tile.from_google(59904, 107919, 18),
    Tile.from_google(59905, 107919, 18),
    Tile.from_google(59906, 107919, 18)
]

print "ut:"
ut_area = Polygon.get_area(map(lambda t: (t.x, t.y), ut_corners))
pprint(ut_area)
print

# tiles that are of a single solid color (we can save space!)
uniform_tiles = [
    Tile.from_google(60, 108, 8), # water
    Tile.from_google(1605, 2885, 13), # land
    Tile.from_google(1605, 2887, 13), # park
    Tile.from_google(1677, 3306, 13), # military, airports, others?
    Tile.from_google(119822, 215827, 19) # cemetary, university, others?
]

#mapper.download_area(Tile.TYPE_MAP, ut_corners, NullTileStore(), range(20))
