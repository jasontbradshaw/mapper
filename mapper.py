#!/usr/bin/env python

import collections
import copy
from math import pi, atan, exp, sin, log
import os
import Queue as queue
import random
import threading
import time
import urllib2

import pymongo
import bson

class Tile:
    """
    A tile representing both Mercator and Google Maps versions of the same info,
    a point/tile on the globe. This is not meant to be mutable, and is only a
    container for the values initially supplied. Changing values after
    initialization will NOT update other values!

    Conversion formulae gleaned from Jeremy R. Geerdes' post:
      http://groups.google.com/group/google-maps-api/msg/7a0aba451045ed94
    """

    # a simple class for tile types with a descriptive name and a URL 'v' value
    TileType = collections.namedtuple("TileType", ["name", "v"])

    # possible kinds of tile for initialization
    KIND_GOOGLE = "google"
    KIND_MERCATOR = "mercator"

    # our various tile types
    TYPE_MAP = TileType("Map", "m")
    TYPE_TERRAIN = TileType("Terrain", "p")
    TYPE_TERRAIN_PLAIN = TileType("Terrain (plain)", "t")
    TYPE_OVERLAY = TileType("Overlay", "h")
    TYPE_SATELLITE = TileType("Satellite", "y")
    TYPE_SATELLITE_PLAIN = TileType("Sattelite (plain)", "s")
    TYPE_BIKE = TileType("Bike", "r")

    # the default size of square tiles
    DEFAULT_TILE_SIZE = 256

    # a URL template for downloading the tile from Google
    URL_TEMPLATE = "http://mt%d.google.com/vt?v=%s&x=%s&y=%s&z=%s"

    def __init__(self, kind, a, b, zoom, tile_size):
        """
        This should only really be called by the static constructor methods. a
        and b take on either x/y or latitude/longitude depending on the kind of
        tile this will be. The other kind's values are filled dynamically from
        the given kind. If a Google tile is being created, the
        latitude/longitude are set to the upper-left corner of the given tile's
        x and y values.
        """

        # update internal values from the given information
        if kind == Tile.KIND_MERCATOR:
            self.init_from_mercator(a, b, zoom, tile_size)
        elif kind == Tile.KIND_GOOGLE:
            self.init_from_google(a, b, zoom, tile_size)
        else:
            raise ValueError("Unrecognized tile kind: " + kind)

    def init_from_mercator(self, latitude, longitude, zoom, tile_size):
        """
        Initializes this tile from a latitude, longitude, zoom, and tile size.
        """

        # zoom must be positive
        assert zoom >= 0

        # shared by both kinds of tile
        self.zoom = zoom

        # kept for reference, the size of this tile in pixels
        self.tile_size = tile_size

        self.latitude = latitude
        self.longitude = longitude

        # calculate x and y coords from latitude and longitude
        lat = latitude
        lng = longitude

        # absolute pixel coordinates
        x_abs = ( round(tile_size * (2 ** (zoom - 1))) +
                  (lng * ((tile_size * (2 ** zoom)) / 360)) )

        y_exp = sin( (lat * pi) / 180 )
        y_exp = max(-0.9999, y_exp) # cap at -0.9999
        y_exp = min(0.9999, y_exp) # cap at 0.9999

        y_abs = ( round(tile_size * (2 ** (zoom - 1))) +
              ( (0.5 * log((1 + y_exp) / (1 - y_exp))) *
                ((-tile_size * (2 ** zoom)) / (2 * pi)) ) )

        # tile coordinates (tile-level resolution)
        self.x = int(x_abs / tile_size)
        self.y = int(y_abs / tile_size)

        # TODO: relative coordinates (pixel resolution, relative to tile)
        #x_rel = x % tile_size
        #y_rel = y % tile_size

    def init_from_google(self, x, y, zoom, tile_size):
        """
        Initializes this tile from an x, y, zoom, and tile size.
        """

        # zoom must be positive
        assert zoom >= 0

        # shared by both kinds of tile
        self.zoom = zoom

        # kept for reference, the size of this tile in pixels
        self.tile_size = tile_size

        self.x = x
        self.y = y

        # calculate latitude and longitude for upper-left corner of the tile
        longitude = ( ( (x * tile_size) - (tile_size * (2 ** (zoom - 1))) ) /
                      ( (tile_size * (2 ** zoom)) / 360.0 ) )

        # normalize longitude
        while longitude > 180:
            longitude -= 360

        while longitude < -180:
            logitude += 360

        lat_exp = ( ( (y * 256) - (256 * (2 ** (zoom - 1))) ) /
                    ( (-256 * (2 ** zoom)) / (2 * pi) ) )
        latitude = ( ( (2 * atan(exp(lat_exp))) - (pi / 2) ) / (pi / 180) )

        # cap final values at their logical extremes
        self.latitude = max(-90.0, latitude)
        self.longitude = min(90.0, longitude)

    @staticmethod
    def from_mercator(latitude, longitude, zoom, tile_size=None):
        """
        Creates a tile from Mercator coordinates and returns it.
        """

        if tile_size is None:
            tile_size = Tile.DEFAULT_TILE_SIZE

        return Tile(Tile.KIND_MERCATOR, latitude, longitude, zoom, tile_size)

    @staticmethod
    def from_google(x, y, zoom, tile_size=None):
        """
        Creates a tile from Google coordinates and returns it.
        """

        if tile_size is None:
            tile_size = Tile.DEFAULT_TILE_SIZE

        return Tile(Tile.KIND_GOOGLE, x, y, zoom, tile_size)

    def download(self, tile_type):
        """
        Downloads the image data for this tile and returns it as a binary
        string, or returns None if no data could be downloaded.
        """

        # create the request URL from the template
        url = Tile.URL_TEMPLATE % (random.randint(0, 3),
                tile_type.v, self.x, self.y, self.zoom)

        # spoof the user agent so google doesn't ban us
        agent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US) "
        agent += "AppleWebKit/532.5 (KHTML, like Gecko) "
        agent += "Chrome/4.0.249.30 Safari/532.5"

        # build the request to download this tile
        request = urllib2.Request(url, headers={"User-Agent": agent})

        try:
            # download the tile and return its image data
            return urllib2.urlopen(request).read()
        except urllib2.HTTPError, e:
            return None

    def hash_google(self):
        """
        Hashes the tile based only on its Google coordinates and zoom.
        """

        result = 17

        result += result * self.x * 13
        result += result * self.y * 43
        result += result * self.zoom * 19

        return result * 7

    def hash_mercator(self):
        """
        Hashes the tile based only on its Mercator coordinates and zoom.
        """

        result = 13

        result += result * hash(self.latitude) * 41
        result += result * hash(self.longitude) * 11
        result += result * self.zoom * 13

        return result * 19

    def __hash__(self):
        """
        Uses both custom hash functions together to generate a hash over all the
        members of the tile.
        """

        return self.hash_google() ^ self.hash_mercator()

    def __eq__(self, other):
        return (isinstance(other, Tile) and
                other.x == self.x and
                other.y == self.y and
                other.zoom == self.zoom)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        r = self.__class__.__name__ + "("
        r += ", ".join(map(repr, [self.x, self.y, self.zoom]))

        if self.tile_size != Tile.DEFAULT_TILE_SIZE:
            r += ", tile_size=" + repr(self.tile_size)

        r += ")"

        return r

class TileStore:
    """
    Interface for storing tiles. Provides a single 'store' method that takes
    tile data and stores it however the class chooses.
    """

    def store(self, tile_type, tile, tile_data):
        """
        Stores a single tile in the store however the class chooses. This method
        should be thread-safe, as no attempts are made to call it synchronously.
        """

        raise NotImplemented("Implement this in your own subclass!")

class FileTileStore:
    """
    Stores tiles in a directory on the local file system.
    """

    def __init__(self, directory=time.strftime("tiles_%Y%m%d_%H%M%S")):
        """
        Creates a tile store that writes files to a given directory. If the
        directory doesn't exist, it creates it. A default time-based directory
        name is used if none is provided.
        """

        self.directory = os.path.abspath(directory)

        # ensure the given directory exists
        try:
            os.mkdir(self.directory)
        except OSError, e:
            # ignore 'already exists' errors, but raise all others
            if e.errno != 17:
                raise e

    def store(self, tile_type, tile, tile_data):
        """
        Writes files to the given directory.
        """

        # build a file name containing descriptive data
        fname = (tile_type.v + "_" +
                str(tile.x) + "-" +
                str(tile.y) + "-" +
                str(tile.zoom))

        # write the file into our directory, overwriting existing files
        with open(os.path.join(self.directory, fname), "w") as f:
            f.write(tile_data)

class MongoTileStore(TileStore):
    """
    Stores tiles on a MongoDB server.
    """

    def __init__(self, server="127.0.0.1", port=27017, db="mapper",
            collection="tiles"):
        self.connection = pymongo.Connection(server, port)
        self.db = self.connection[db]
        self.collection = self.db[collection]

    def store(self, tile_type, tile, tile_data):
        assert isinstance(tile_type, Tile.TileType)
        assert isinstance(tile, Tile)
        assert isinstance(tile_data, basestring)

        # start with base information so we can use it to find existing tiles
        tile = {
            # coordinates
            "x": int(tile.x),
            "y": int(tile.y),
            "zoom": int(tile.zoom),

            # tile type (we're expecting a collections.namedtuple)
            "tile_type": tile_type._asdict()
        }

        # update the id of our 'new' tile to match the stored one
        stored_tile = self.collection.find_one(tile)
        if stored_tile is not None:
            tile["_id"] = stored_tile["_id"]

        # image data as binary
        tile["image_data"] = bson.binary.Binary(tile_data)

        # update date, for eventually re-downloading 'old' tiles
        tile["update_date"] = int(time.time())

        # add our tile to the collection, updating if the '_id' is set
        self.collection.save(tile)

class TileDownloader:
    """Downloads map tiles using multiple threads."""

    def __init__(self, tile_store):
        self.tile_store = tile_store

    def download(self, tile_type, tiles, num_threads=10):
        """Downloads some tiles using the given type."""

        # put all our tiles into a queue so all threads can share them
        tile_queue = queue.Queue()
        [tile_queue.put(tile) for tile in tiles]

        # assign threads their respective tile lists
        thread_pool = []
        for i in xrange(num_threads):
            thread = threading.Thread(target=self.download_tiles,
                    args=(tile_type, tile_queue))
            thread_pool.append(thread)
            thread.start()

        # wait for all the threads to finish
        [thread.join() for thread in thread_pool]

    def download_tiles(self, tile_type, tile_queue):
        """
        Downloads all the tiles in the given queue for the given type and stores
        them in the tile store.
        """

        while 1:
            try:
                tile = tile_queue.get_nowait()
                tile_data = tile.download(tile_type)

                if tile_data is None:
                    raise IOError("Could not download tile " + str(tile) +
                            " as type " + tile_type)

                self.tile_store.store(tile_type, tile, tile_data)
            except queue.Empty:
                break

class Bounds:
    """
    A class representing the bounding box of some tiles. It holds the top-most,
    right-most, bottom-most, and left-most vertices, as well as the bounding
    box's width, height, and corners.
    """

    def __init__(self, top, right, bottom, left):
        """
        Create a bounds object from top, left, bottom, and right tiles. Should
        only be used internally: use get_bounds() instead.
        """

        # save our extremities as copies
        self.top = copy.copy(top)
        self.right = copy.copy(right)
        self.bottom = copy.copy(top)
        self.left = copy.copy(left)

        # determine the corners of the bounding box as tiles
        self.top_left = Tile.from_google(left.x, top.y, top.zoom)
        self.top_right = Tile.from_google(right.x, top.y, top.zoom)
        self.bottom_right = Tile.from_google(right.x, bottom.y, top.zoom)
        self.bottom_left = Tile.from_google(left.x, bottom.y, top.zoom)

        # find the width and height of the bounding box, edges inclusive
        self.width = abs(self.left.x - self.right.x) + 1
        self.height = abs(self.top.y - self.bottom.y) + 1

    @staticmethod
    def get_bounds(tiles):
        """
        Returns a Bounds object containing data about the bounding box that
        contains the given tiles. If multiple tiles are at the bounds, the first
        is used. If one tile satisfies multiple bounds, it will be used multiple
        times. The returned object contains new tiles for all boundaries.
        """

        # don't bother trying to find the bounds of an empty tile set
        if len(tiles) == 0:
            return None

        # disallow unmatched zoom levels
        if not all([t.zoom == tiles[0].zoom for t in tiles]):
            raise ValueError("All tiles must have the same zoom level.")

        # find the furthest vertices in the cardinal directions
        top = None
        right = None
        bottom = None
        left = None
        for tile in tiles:
            # top
            if top is None or tile.y < top.y:
                top = tile

            # right
            if right is None or tile.x > right.x:
                right = tile

            # bottom
            if bottom is None or tile.y > bottom.y:
                bottom = tile

            # left
            if left is None or tile.x < left.x:
                left = tile

        return Bounds(top, right, bottom, left)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        s = self.__class__.__name__ + "("
        s += ", ".join(map(repr, (self.top, self.right, self.bottom, self.left)))
        s += ")"

        return s

class TileCalculator:
    """
    Calculates all the tiles in a region from the specified zoom level down.
    Meant only to be used as a container class! If members are modified after
    initialization, values won't be updated to reflect them.
    """

    def __init__(self):
        raise NotImplemented("Can't instantiate " + self.__class__.__name__)

    @staticmethod
    def generate_line(tile0, tile1):
        """
        Generates all the tiles on the line rendered between tile0 and tile1,
        endpoints inclusive, using Bresenham's line drawing algorithm. Tiles
        must have the same zoom level.

        Reference: http://en.wikipedia.org/wiki/Bresenham's_line_algorithm
        """

        # disallow unmatched zoom levels
        if tile0.zoom != tile1.zoom:
            raise ValueError("Tiles must have the same zoom level.")

        # make some shorthand variables
        x0 = tile0.x
        y0 = tile0.y
        x1 = tile1.x
        y1 = tile1.y

        # an optimized version of the algorithm (see #Simplification in wiki)
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)

        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1

        err = dx - dy

        while 1:
            # yield a tile on the line
            yield Tile.from_google(x0, y0, tile0.zoom)

            if x0 == x1 and y0 == y1:
                return

            e2 = 2 * err

            if e2 > -dy:
                err -= dy
                x0 += sx

            if e2 < dx:
                err += dx
                y0 += sy

    @staticmethod
    def get_line(tile0, tile1):
        """
        Same as generate_line(), but returns a list instead of a generator.
        """

        # consume all the tiles in the generator and return them
        return [tile for tile in TileCalculator.generate_line(tile0, tile1)]

    @staticmethod
    def generate_polygon(vertices, use_separator=False, connect_ends=True):
        """
        Generates the tiles in a polygon from a sequential list of vertices. If
        connect_ends is True (the default), the first and last vertices are
        connected. If use_separator is True, None is yielded after every line in
        order to delimit them, and no vertex de-duplicating takes place.

        Yields the edges in order from the first pair to the last pair of
        vertices, followed by the edge from last to first if connect_ends is
        True.

        All vertices must have the same zoom level.
        """

        # disallow unmatched zoom levels
        if not all([v.zoom == vertices[0].zoom for v in vertices]):
            raise ValueError("All vertices must have the same zoom level.")

        # yield lines between consecutive vertices
        prev_v = None
        for v in vertices:
            # yield the very first vertex (it gets skipped while line-yielding)
            if prev_v is None:
                if not use_separator:
                    yield copy.copy(v) # only yield unique tile objects
                prev_v = v
                continue

            # yield all the tiles on the line
            first = True
            for tile in TileCalculator.generate_line(prev_v, v):
                # if not using a separator, skip the first tile, the previous
                # vertex itself
                if not use_separator and first:
                    first = False
                    continue

                yield tile

            # yield a special separator between lines if requested
            if use_separator:
                yield None

            prev_v = v

        # connect ends if specified and we have more than just a point or a line
        if connect_ends and len(vertices) > 2:
            # connect the last vertex to the first, leaving out the endpoints
            first = True
            for tile in TileCalculator.generate_line(prev_v, vertices[0]):
                # don't yield the first or last vertices if not separating
                if not use_separator and (first or tile == vertices[0]):
                    first = False
                    continue

                yield tile

            # yield a final separator if necessary
            if use_separator:
                yield None

    @staticmethod
    def get_polygon(vertices, use_separator=False, connect_ends=True):
        """
        Same as generate_polygon(), but returns a list rather than a generator.
        """

        return [line for line in TileCalculator.generate_polygon(vertices,
            use_separator, connect_ends)]

    @staticmethod
    def generate_area(vertices, connect_ends=True):
        """
        Generates all the tiles in a polygon described by some vertices and
        yields them in arbitrary order. connect_ends behaves as in
        generate_polygon().

        Reference: http://en.wikipedia.org/wiki/Flood_fill#Fixed_memory_method_.28right-hand_fill_method.29
        """

        # don't bother with calculations for corner cases
        if len(vertices) == 0:
            return
        if len(vertices) == 1:
            yield copy.copy(vertices[0])
            return
        elif len(vertices) == 2:
            for tile in TileCalculator.generate_line(vertices[0], vertices[1]):
                yield tile
            return

        # find the bounds so we know the maximum ray-casting distances
        bounds = Bounds.get_bounds(vertices)

    @staticmethod
    def get_area(vertices, connect_ends=True):
        """
        Same as generate_area(), but returns a list instead of a generator.
        """

        return [t for t in TileCalculator.generate_area(vertices, connect_ends)]

if __name__ == "__main__":
    import pdb
    from pprint import pprint

    tile_m = Tile.from_mercator(30.2832, -97.7362, 18)
    tile_g = Tile.from_google(59902, 107915, 18)
    #print "Mercator:", tile_m.latitude, tile_m.longitude, tile_m.zoom
    #print "Google:", tile_g.x, tile_g.y, tile_g.zoom
    assert tile_m == tile_g

    # get us an area and make sure it contains no duplicate tiles
    test_tiles = [
        Tile.from_google(0, 0, 0),
        Tile.from_google(5, 0, 0),
        Tile.from_google(5, 5, 0),
        Tile.from_google(0, 5, 0),
    ]

    pprint(TileCalculator.get_polygon(test_tiles[0:1], use_separator=False))
    print
    pprint(TileCalculator.get_polygon(test_tiles[0:2], use_separator=False))
    print
    pprint(TileCalculator.get_polygon(test_tiles[0:3], use_separator=False))
    print
    pprint(TileCalculator.get_polygon(test_tiles[0:4], use_separator=False))

    # these tiles represent roughly the UT Austin campus
    ut_corners = [
        Tile.from_google(59902, 107915, 18),
        Tile.from_google(59902, 107919, 18),
        Tile.from_google(59906, 107919, 18)
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

    #ut_area = TileCalculator.get_area(ut_corners)
    #print len(ut_area)

    # tiles that are of a single solid color (we can save space!)
    uniform_tiles = [
        Tile.from_google(60, 108, 8), # water
        Tile.from_google(1605, 2885, 13), # land
        Tile.from_google(1605, 2887, 13), # park
        Tile.from_google(1677, 3306, 13) # feature (military, airports, others?)
    ]

    #downloader = TileDownloader(MongoTileStore())
    #downloader.download(Tile.TYPE_MAP, ut_tiles)

    #downloader = TileDownloader(FileTileStore())
    #downloader.download(Tile.TYPE_OVERLAY, uniform_tiles)
