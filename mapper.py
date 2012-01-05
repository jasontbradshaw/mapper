#!/usr/bin/env python

import collections
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

    def __hash__(self):
        """
        We hash only by Google coordinates, so tiles created with very close
        Mercator coordinates may hash to the same value.
        """

        result = 17

        result += result * self.x * 13
        result += result * self.y * 43
        result += result * self.zoom * 19

        return result * 7

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
    A tile store that stores tiles in MongoDB.
    """

    DB_NAME = "mapper"
    DB_COLLECTION = "tiles"

    def __init__(self, server="127.0.0.1", port=27017):
        self.connection = pymongo.Connection(server, port)
        self.db = self.connection[MongoTileStore.DB_NAME]
        self.collection = self.db[MongoTileStore.DB_COLLECTION]

    def store(self, tile_type, tile, tile_data):
        assert isinstance(tile_type, Tile.TileType)
        assert isinstance(tile, Tile)
        assert isinstance(tile_data, basestring)

        # start with the base information to see if we already have this tile
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

        # add specific data for this insert/update
        tile.update({
            # image data as binary
            "image_data": bson.binary.Binary(tile_data),

            # update date, for eventually re-downloading 'old' tiles
            "update_date": int(time.time())
        })

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

class TileCalculator:
    """
    Calculates all the tiles in a region from the specified zoom level down.
    """

    def __init__(self):
        raise NotImplemented("Can't instantiate " + self.__class__.__name__)

    @staticmethod
    def get_area(vertices):
        """
        Gets all the tiles in an area and returns them as a set. Vertices are
        assumed to be in-order (CW/CCW and starting vertex are irrelevant), and
        the final vertex is assumed to be connected to the first vertex. If the
        polygon described by the given vertices is complex (has mutliple inner
        regions), only the first one found will be filled.
        """

        # don't do calculations if we weren't given any vertices
        if len(vertices) == 0:
            return set()

        # ensure all our vertices have the same zoom level
        if not all([v.zoom == vertices[0].zoom for v in vertices]):
            raise ValueError("All vertices must have the same zoom level.")

        # find the furthest vertices in every direction so we know how far we
        # must cast rays to find edges.
        top = None
        bottom = None
        left = None
        right = None
        for vertex in vertices:
            # left
            if left is None or vertex.x < left.x:
                left = vertex

            # right
            if right is None or vertex.x > right.x:
                right = vertex

            # top
            if top is None or vertex.y < top.y:
                top = vertex

            # bottom
            if bottom is None or vertex.y > bottom.y:
                bottom = vertex

        # initialize the set with our initial vertices
        result = set(vertices)

        # add lines between consecutive vertices
        prev_vertex = vertices[0]
        for vertex in vertices[1:]:
            result.update(TileCalculator.get_line(prev_vertex, vertex))
            prev_vertex = vertex

        # connect the last vertex to the first
        result.update(TileCalculator.get_line(prev_vertex, vertices[0]))

        # find the first inner surface of the polygon and fill from there,
        # casting rays top-to-bottom, left-to-right, starting slightly outside
        # the furthest boundaries and continuing slightly past them.
        inner_point = None

        # to avoid overhead, we simply modify a point in-situ since it only gets
        # hashed by x/y/zoom anyhow.
        point = Tile.from_google(0, 0, vertices[0].zoom)

        for y in xrange(top.y - 1, bottom.y + 2):
            # did we just exit a line?
            last_was_filled = False

            for x in xrange(left.x - 1, right.x + 2):
                # set up the point with the current coordinates
                point.x = x
                point.y = y

                # we found our inner point
                if point not in result and last_was_filled:

                    # TODO: cast rays up, down, and right to ensure we're
                    # definitively inside the polygon. alternatively, use corner
                    # detection algorithms.
                    inner_point = point
                    break

                # don't allow consecutive points (we're on a line or similar)
                if point in result and last_was_filled:
                    break

                # track whether the last point we saw was on a line
                last_was_filled = point in result

            # give up once the inner loop found an inner point
            if inner_point is not None:
                break

        # if the polygon has no inner surfaces, it was a 'line', so don't fill
        if inner_point is None:
            return result

        # four-way flood-fill from our inner point
        point_stack = [inner_point]
        while len(point_stack) > 0:
            point = point_stack.pop()

            # fill the point if it wasn't filled already
            if point not in result:
                result.add(point)

                # add the point's neighbors
                north = Tile.from_google(point.x, point.y - 1, point.zoom)
                south = Tile.from_google(point.x, point.y + 1, point.zoom)
                east = Tile.from_google(point.x + 1, point.y, point.zoom)
                west = Tile.from_google(point.x - 1, point.y, point.zoom)
                point_stack.extend((north, south, east, west))

        # return our filled polygon
        return result

    @staticmethod
    def generate_line(tile0, tile1):
        """
        Bresenham's line drawing algorithm, modified to calculate all the tiles
        between two tiles, including endpoints. Returns a generator that yields
        the calculated tiles between tile0 and tile1, including the given tiles.

        Reference: http://en.wikipedia.org/wiki/Bresenham's_line_algorithm
        """

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
        Same as the generator method, but this returns a list of tiles, not a
        generator.
        """

        # consume all the tiles in the generator and return them
        return [tile for tile in TileCalculator.generate_line(tile0, tile1)]

if __name__ == "__main__":
    import pdb

    tile = Tile.from_mercator(30.2832, -97.7362, 18)
    print "Mercator:", tile.latitude, tile.longitude, tile.zoom
    print "Google:", tile.x, tile.y, tile.zoom

    corners = [
        Tile.from_google(59902, 107915, 18),
        Tile.from_google(59902, 107919, 18),
        Tile.from_google(59906, 107919, 18)
    ]

    #area = TileCalculator.get_area(corners)
    #print len(area)

    # these tiles represent roughly the UT Austin campus
    tiles = [
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

    # tiles that are of a single solid color (we can save space!)
    uniform_tiles = [
        Tile.from_google(60, 108, 8), # water
        Tile.from_google(1605, 2885, 13), # land
        Tile.from_google(1605, 2887, 13), # park
        Tile.from_google(1677, 3306, 13) # feature (military, airports, others?)
    ]

    downloader = TileDownloader(MongoTileStore())
    downloader.download(Tile.TYPE_MAP, tiles)

    downloader = TileDownloader(FileTileStore())
    downloader.download(Tile.TYPE_OVERLAY, uniform_tiles)
