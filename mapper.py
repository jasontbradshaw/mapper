#!/usr/bin/env python

import collections
from math import pi, atan, exp, sin, log
import os
import itertools
import Queue as queue
import random
import threading
import time
import urllib2

import pymongo
import bson

def download(tile_type, tiles, tile_store, num_threads=10, verbose=True):
    """
    Downloads some tiles in parallel from an iterable using the given type.
    num_threads is the number of simultaneous threads that will be used to
    download tiles.
    """

    # check our thread count to make sure we'll get workers
    if num_threads <= 0:
        raise ValueError("num_threads must be greater than 0")

    # the queue our threads will pull tiles from (least-failed tiles first)
    tile_queue = queue.PriorityQueue(num_threads * 10)

    # start our threads; they will wait a bit for tiles to download
    threads = []
    for i in xrange(num_threads):
        thread = threading.Thread(target=__download_tiles_from_queue,
                args=(tile_type, tile_queue, tile_store, 0.1, 3, verbose))
        thread.daemon = True
        threads.append(thread)
        thread.start()

    # feed tiles to the waiting threads as (number of download fails, tile)
    for tile in tiles:
        # attempt to fill the queue, but do so in a way that will allow worker
        # threads to re-insert failed tiles periodically.
        item = (0, tile)
        while 1:
            try:
                tile_queue.put(item, True, 1)
                break
            except queue.Full:
                continue

    # wait for all the threads to finish
    [thread.join() for thread in threads]

def download_area(tile_type, vertices, tile_store, zoom_levels, num_threads=10,
        verbose=True):
    """
    Download tiles formed from the area described by the given tile vertices.
    vertices should be an in-order list of tiles describing the sequential
    vertices of a non-complex polygon, preferrably with accurate Mercator
    coordinates (these translate between zoom levels best). zoom_levels is a
    list of zoom levels to download. See download() for an explanation of the
    other parameters.
    """

    # check our thread count to make sure we'll get workers
    if num_threads <= 0:
        raise ValueError("num_threads must be greater than 0")

    def log(msg):
        """Log a message to the screen if verbose is True."""
        if verbose:
            print msg

    # the queue our threads will pull tiles from (least-failed tiles first)
    tile_queue = queue.PriorityQueue(num_threads * 10)

    # start our threads; they will wait a bit for tiles to download
    threads = []
    for i in xrange(num_threads):
        thread = threading.Thread(target=__download_tiles_from_queue,
                args=(tile_type, tile_queue, tile_store, 0.1, 3, verbose))
        thread.daemon = True
        threads.append(thread)
        thread.start()

    for z in zoom_levels:
        # translate vertices to the given zoom level, then to coordinate pairs
        points = []
        for v in vertices:
            zoomed_v = Tile.from_mercator(v.latitude, v.longitude, z)
            points.append((zoomed_v.x, zoomed_v.y))

        log("Downloading area at zoom " + str(z))

        # get the area for the points
        area = Polygon.generate_area(points)

        # convert points back in to tiles and feed them to the queue
        for tile in (Tile.from_google(p[0], p[1], z) for p in area):
            item = (0, tile)
            while 1:
                try:
                    tile_queue.put(item, True, 1)
                    break
                except queue.Full:
                    continue

    # wait for all the threads to finish
    [thread.join() for thread in threads]

def __download_tiles_from_queue(tile_type, tile_queue, tile_store,
        timeout=0.1, max_failures=3, verbose=True):
    """
    Downloads all the tiles in a queue for some type and stores them in the tile
    store. Will re-insert failed downloads into the queue for later processing,
    but only up to max_failures times. timeout specifies the amount of time in
    seconds downloading threads will wait for new tiles to enter the queue
    before giving up and ending their download loops.
    """

    def log(msg):
        """Log a message to the screen if verbose is True."""
        if verbose:
            print msg

    while 1:
        try:
            # wait a bit for data to show up
            fail_count, tile = tile_queue.get(True, timeout)
            tile_data = tile.download(tile_type)

            # deal with download failures
            if tile_data is None:
                # retry if we haven't yet exceeded the max
                if fail_count < max_failures:
                    # TODO: there might be a dining-philosophers condition here.
                    # if all threads simultaneously arrive at a failed tile and
                    # then the queue fills up, there will be nobody to make more
                    # room in the queue.
                    tile_queue.put((fail_count + 1, tile))
                    log("Download of tile " + str(tile) + " as type " +
                            str(tile_type) + " failed, " +
                            str(fail_count + 1 - max_failures) +
                            " retry attempts remaining")
                else:
                    # give up otherwise
                    log("Could not download tile " + str(tile) + " as type " +
                            str(tile_type) + " (out of retries)")
            else:
                # store the downloaded tile
                log("Downloaded tile " + str(tile) + " as type " +
                        str(tile_type))
                tile_store.store(tile_type, tile, tile_data)

            # signal that we finished processing this tile
            tile_queue.task_done()
        except queue.Empty:
            break

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

    def __init__(self, *args, **kwargs):
        raise NotImplemented(self.__class__.__name__ + " can't be instantiated")

    def store(self, tile_type, tile, tile_data):
        """
        Stores a single tile in the store however the class chooses. This method
        should be thread-safe, as no attempts are made to call it synchronously.
        """

        raise NotImplemented("Implement this in your own subclass!")

class NullTileStore(TileStore):
    """
    Throws away all tiles given to it. Useful for performance testing.
    """

    def __init__(self, *args, **kwargs):
        pass

    def store(*args, **kwargs):
        pass

class FileTileStore(TileStore):
    """
    Stores tiles in a directory on the local file system.
    """

    def __init__(self, directory=time.strftime("tiles_%Y%m%d_%H%M%S"),
            name_generator=None):
        """
        Creates a tile store that writes files to a given directory. If the
        directory doesn't exist, it creates it. A default time-based directory
        name is used if none is provided. name_generator is a callable that takes
        a tile and a tile type and returns a file name. If unspecified, a
        default is used.
        """

        def default_name_generator(tile, tile_type):
            return (tile_type.v + "_" +
                    str(tile.x) + "-" +
                    str(tile.y) + "-" +
                    str(tile.zoom))

        # store the method for generating file names
        self.name_generator = name_generator
        if name_generator is None:
            self.name_generator = default_name_generator

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
        fname = self.name_generator(tile, tile_type)

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
        """
        Store the tile in the database with a Unix update time in seconds. If a
        tile with the same data already exists, update it accordingly.
        """

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

class Polygon:
    """
    A utility class for operations on lists of vertices.
    """

    # represents the bounding box of some points
    Bounds = collections.namedtuple("Bounds", ["top", "right", "bottom", "left"])

    def __init__(self):
        raise NotImplemented(self.__class__.__name__ + " can't be instantiated")

    @staticmethod
    def get_bounds(*vertices):
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
        for vertex in vertices:
            # top
            if top is None or vertex[1] < top[1]:
                top = vertex

            # right
            if right is None or vertex[0] > right[0]:
                right = vertex

            # bottom
            if bottom is None or vertex[1] > bottom[1]:
                bottom = vertex

            # left
            if left is None or vertex[0] < left[0]:
                left = vertex

        return Polygon.Bounds(top=top, right=right, bottom=bottom, left=left)

    @staticmethod
    def generate_vertex_pairs(vertices):
        """
        Generates paired vertices from a list of vertices, including from last
        vertex to first vertex.

        Examples:
            [] -> []
            [A] -> [(A, A)]
            [A, B] -> [(A, B), (B, A)]
            [A, B, C] -> [(A, B), (B, C), (C, A)]
        """

        # don't do any work if we're too short
        if len(vertices) == 0:
            return

        # turn our vertices into a sequence of adjacent vertex pairs
        last_point = None
        for point in vertices:
            if last_point is None:
                last_point = point
                continue

            yield (last_point, point)
            last_point = point

        # add the pair from last to first
        yield (last_point, vertices[0])


    @staticmethod
    def generate_line(a, b):
        """
        Rasterizes the line between the given points, and yields them all
        in-order, endpoints included, using Bresenham's line drawing algorithm.

        Reference: http://en.wikipedia.org/wiki/Bresenham's_line_algorithm
        """

        # make some shorthand variables
        x0, y0 = a
        x1, y1 = b

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
        have non-overlappind edges. Runs of identical vertices are collapsed
        into a single value.
        """

        # collapse adjacent duplicate vertices
        collapse = lambda a, p: a + [p] if (len(a) == 0 or p != a[-1]) else a
        vertices = reduce(collapse, vertices, [])

        # don't bother with calculations for corner cases
        if len(vertices) <= 1:
            for v in vertices:
                yield v
            return
        elif len(vertices) == 2:
            for point in Polygon.generate_line(vertices):
                yield point
            return

        # get all lines, keeping only non-horizontal lines
        lines = [pair for pair in Polygon.generate_vertex_pairs(vertices)]
        lines = filter(lambda p: p[0][1] != p[1][1], lines)

        # find the bounds for the whole polygon
        polygon_bounds = Polygon.get_bounds(*vertices)

        # iterate top to bottom along the y axis, building the SET
        sorted_edges = collections.defaultdict(list)
        for y in xrange(polygon_bounds.top[1], polygon_bounds.bottom[1] + 1):
            for a, b in lines:
                # get bounding box for this line
                bounds = Polygon.get_bounds(a, b)

                # the largest y, so we know when to stop checking the edge
                y_max = bounds.bottom[1]

                # the slope parts of the edge, to use edge coherence
                rise = b[1] - a[1]
                run = b[0] - a[0]

                # add to SET if line has its minimum y coord in this scanline.
                # this handles vertex edge cases as well.
                x_min = None
                if a[1] == y and a[1] == bounds.top[1]:
                    x_min = a[0]
                elif b[1] == y and b[1] == bounds.top[1]:
                    x_min = b[0]

                # only add if we had a minimum vertex at this scanline
                if x_min is not None:
                    sorted_edges[y].append([y_max, x_min, rise, run])

                    # keep the entries sorted by y_max then x_min (list's
                    # natural sorting order, luckily for us).
                    sorted_edges[y].sort()

        # list of active edges, those intersecting with the current scanline
        active_edges = []

        # starting y value as smallest value in SET with a non-empty bucket
        assert len(sorted_edges.keys()) >= 1
        if len(sorted_edges.keys()) > 1:
            y = min(*sorted_edges.keys())
        else:
            y = sorted_edges.keys()[0]

        # continue while sorted edges or active edges have entries
        while len(sorted_edges.values()) > 0 or len(active_edges) > 0:
            # move y bucket into active edge list if the edges' y-min (the key
            # into sorted edges) is the current y.
            if y in sorted_edges:
                active_edges.extend(sorted_edges[y])
                del sorted_edges[y]

            # sort active edges by x coordinates
            active_edges.sort(key=lambda e: e[1])

            # fill between pairs of intersections (excluding the final new edge
            # if we added an odd number). keep track of the last yielded point
            # so we don't duplicate points at 'v'-shaped intersections.
            last_point = None
            for a, b in itertools.izip(*[iter(active_edges)] * 2):
                x_from = int(round(a[1]))
                x_to = int(round(b[1])) + 1

                # round values to nearest whole number
                for x in xrange(x_from, x_to):
                    point = (x, y)

                    # don't yield duplicate points (happens at some vertices)
                    if point != last_point:
                        yield point

                    last_point = point

            # deactivate edges who's y-max is the current y
            active_edges = filter(lambda e: e[0] != y, active_edges)

            # move to the next scanline
            y += 1

            # update x for non-vertical edges left in active edges
            for edge in active_edges:
                _, x_min, rise, run = edge

                # update edge's x_min for next round if the edge isn't vertical
                if run != 0:
                    # TODO: do incremental calculation
                    edge[1] = x_min + (1.0 * run / rise)

    @staticmethod
    def get_area(vertices):
        """
        Same as generate_area(), but returns a list instead of a generator.
        """

        return [point for point in Polygon.generate_area(vertices)]

if __name__ == "__main__":
    pass
