#!/usr/bin/env python

import collections
import copy
import itertools
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

        tile_size = Tile.DEFAULT_TILE_SIZE if tile_size is None else tile_size
        return Tile(Tile.KIND_MERCATOR, latitude, longitude, zoom, tile_size)

    @staticmethod
    def from_google(x, y, zoom, tile_size=None):
        """
        Creates a tile from Google coordinates and returns it.
        """

        tile_size = Tile.DEFAULT_TILE_SIZE if tile_size is None else tile_size
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
    A class representing the bounding box of some points. It holds the top-most,
    right-most, bottom-most, and left-most vertices.
    """

    def __init__(self, top=None, right=None, bottom=None, left=None):
        """
        Create a bounds object from top, right, bottom, and left points. Should
        only be used internally: use get_bounds() instead.
        """

        # save our extremities as copies
        self.top = top
        self.right = right
        self.bottom = bottom
        self.left = left

    @staticmethod
    def get_bounds(*points):
        """
        Returns a Bounds object containing data about the bounding box that
        contains the given points. If multiple points are at the bounds, the
        first is used. If one point satisfies multiple bounds, it will be used
        multiple times.
        """

        # find the furthest vertices in the cardinal directions
        top = None
        right = None
        bottom = None
        left = None
        for point in points:
            # top
            if top is None or point[1] < top[1]:
                top = point

            # right
            if right is None or point[0] > right[0]:
                right = point

            # bottom
            if bottom is None or point[1] > bottom[1]:
                bottom = point

            # left
            if left is None or point[0] < left[0]:
                left = point

        return Bounds(top=top, right=right, bottom=bottom, left=left)

    def __str__(self):
        s = "("
        s += ",".join(map(str((self.top, self.right, self.bottom, self.left))))
        s += ")"

        return s

    def __repr__(self):
        s = self.__class__.__name__ + "("
        s += "top=" + str(self.top)
        s += ", "
        s += "right=" + str(self.right)
        s += ", "
        s += "bottom=" + str(self.bottom)
        s += ", "
        s += "left=" + str(self.left)
        s += ")"

        return s

class Polygon:
    """
    A utility class for operations on lists of vertices.
    """

    def __init__(self):
        raise NotImplemented(self.__class__.__name__ + " can't be instantiated")

    @staticmethod
    def __cycle(iterable, skip=1):
        """
        cycle([1, 2, 3], 1) -> 2, 3, 1, 2, 3, ...
        Returns a generator that yields the elements of an iterable in a cycle,
        starting by skipping the first 'skip' items.
        """

        # don't cycle for empty iterables
        if len(iterable) == 0:
            return

        i = skip
        while 1:
            yield iterable[i]
            i = (i + 1) % len(iterable)

    @staticmethod
    def generate_line(a, b):
        """
        Rasterizes the line between the given points, and yields them all
        in-order, endpoints included, using Bresenham's line drawing algorithm.

        Reference: http://en.wikipedia.org/wiki/Bresenham's_line_algorithm
        """

        # make some shorthand variables
        x0 = a[0]
        y0 = a[1]
        x1 = b[0]
        y1 = b[1]

        # an optimized version of the algorithm (see #Simplification in wiki)
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)

        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1

        err = dx - dy

        while 1:
            # yield a rasterized point on the line
            yield (x0, y0)

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
    def get_line(a, b):
        """
        Same as generate_line(), but returns a list instead of a generator.
        """

        return [point for point in Polygon.generate_line(a, b)]

    @staticmethod
    def generate_area(vertices):
        """
        Generates all the points on the rasterized polygon described by a list
        of vertices and yields them in arbitrary order. Polygons are assumed to
        have non-overlappind edges.
        """

        # don't bother with calculations for corner cases
        if len(vertices) <= 2:
            for point in Polygon.generate_polygon(vertices):
                yield point
            return

        # map points on edges to collections of their line boundaries
        edge_points = collections.defaultdict(list)

        # iterate over the sequentially paired vertices, indcluding (last, first)
        for a, b in itertools.izip(vertices, Polygon.__cycle(vertices, 1)):
            # find the boundaries of this line
            bounds = Bounds.get_bounds(a, b)

            # add only non-horizontal edges
            if bounds.top[1] != bounds.bottom[1]:
                # map each point on the line to a list of line bounds
                for point in Polygon.generate_line(a, b):
                    edge_points[point].append(bounds)

        # make the dict behave as a normal dictionary
        edge_points.default_factory = None

        # scan from top to bottom, generating scanlines
        bounds = Bounds.get_bounds(*vertices)

        # scan left-right (starting from known empty points), intersecting
        for y in xrange(bounds.top[1], bounds.bottom[1] + 1):

            # keep track of whether we're inside the polygon as we scan
            inside = False
            for x in xrange(bounds.left[0], bounds.right[0] + 1):
                # get the current coordinates
                p = (x, y)

                # yield points between intersecting edges
                if inside:
                    yield p

                # if we're on a line, store the point as an intersection
                if p in edge_points:
                    edge_bounds = edge_points[p]

                    # de-dupe certain intersections
                    if len(edge_bounds) > 1:
                        # we only de-dupe two points (no complex polygons)
                        i1_bounds = edge_bounds[0]
                        i2_bounds = edge_bounds[1]

                        # condense down to a single intersection if we didn't
                        # meet in a 'v' or '^' shape and we were on a vertex.
                        if not (i1_bounds.bottom[1] == i2_bounds.bottom[1] or
                                i1_bounds.top[1] == i2_bounds.top[1]):
                            edge_bounds = [i1_bounds]
                        else:
                            # constrain to two intersections otherwise
                            edge_bounds = [i1_bounds, i2_bounds]

                    # yield first inside point if crossing in from outside
                    if not inside:
                        yield p

                    # move from inside to outside every time we cross an edge
                    inside = not inside and len(edge_bounds) % 2 != 0

    @staticmethod
    def get_area(vertices):
        """
        Same as generate_area(), but returns a list instead of a generator.
        """

        return [point for point in Polygon.generate_area(vertices)]

if __name__ == "__main__":
    from pprint import pprint

    tile_m = Tile.from_mercator(30.2832, -97.7362, 18)
    tile_g = Tile.from_google(59902, 107915, 18)
    #print "Mercator:", tile_m.latitude, tile_m.longitude, tile_m.zoom
    #print "Google:", tile_g.x, tile_g.y, tile_g.zoom
    assert tile_m == tile_g

    # get us an area and make sure it contains no duplicate tiles
    points = [
        (0, 0),
        (5, 0),
        (5, 5),
        (0, 5)
    ]
    pprint(Polygon.get_area(points))

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

    #ut_area = Polygon.get_area(ut_corners)
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
