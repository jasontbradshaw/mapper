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

def download_area(tile_type, vertices, tile_store, zoom_levels, num_threads=10,
        logger=None, skip_to_tile=None):
    """
    Download tiles formed from the area described by the given tile vertices.
    vertices should be an in-order list of tiles describing the sequential
    vertices of a non-complex polygon, preferrably with accurate Mercator
    coordinates (these translate between zoom levels best). zoom_levels is a
    list of zoom levels to download. If skip_to_tile is non-None, all preceding
    tiles not equal to the given tile will be skipped. See download() for an
    explanation of the other parameters.
    """

    # check our thread count to make sure we'll get workers
    if num_threads <= 0:
        raise ValueError("num_threads must be greater than 0")

    # use a default logger if none was specified
    logger = __get_null_logger() if logger is None else logger

    tile_queue = queue.Queue(num_threads * 10)
    halt_event = threading.Event()

    threads = []
    for i in xrange(num_threads):
        args = (tile_type, tile_queue, tile_store, 0.1, 10, halt_event, logger)
        thread = threading.Thread(target=__download_tiles_from_queue, args=args)
        thread.daemon = True
        threads.append(thread)
        thread.start()

    # whether we should skip tiles
    should_skip = skip_to_tile is not None

    # log that we're skipping, so it doesn't look like we froze
    if should_skip:
        logger.info("Skipping to " + str(skip_to_tile) + "...")

    for zoom in zoom_levels:
        logger.info("Downloading zoom level " + str(zoom))

        # skip entire zoom levels if necessary to find the first non-skip tile
        if should_skip and skip_to_tile.zoom != zoom:
            logger.debug("Skipping zoom level " + str(zoom))
            continue

        # translate vertices to the given zoom level, then to coordinate pairs
        points = []
        for v in vertices:
            zoomed_v = Tile.from_mercator(v.latitude, v.longitude, zoom)
            points.append((zoomed_v.x, zoomed_v.y))

        # get the area for the points
        area = Polygon.generate_area(points)

        # track tile download rate
        rate_calculator = RateCalculator(1000, 15)
        rate_calculator.start()

        # convert points back into tiles and feed them to the queue
        for tile in (Tile.from_google(p[0], p[1], zoom) for p in area):
            # skip to the specified tile if necessary
            if should_skip:
                # disable skipping once we find the specified tile
                if (tile.x == skip_to_tile.x and
                        tile.y == skip_to_tile.y and
                        tile.zoom == skip_to_tile.zoom):
                    logger.info("Skipped to tile " + str(tile))
                    should_skip = False

                    # reset to start time if we were skipping
                    rate_calculator.reset()
                    rate_calculator.start()
                else:
                    # otherwise, skip tiles that don't match
                    logger.debug("Skipping " + str(tile))
                    continue

            item = (0, tile)
            while 1:
                try:
                    logger.debug("Adding " + str(item) + " to queue")
                    tile_queue.put(item, True, 0.1)
                    break
                except queue.Full:
                    logger.debug("Queue full, retrying 'put' for " + str(item))
                    continue

            # count enqueuing the tile towards the download rate
            rate_calculator.tock()

            ave_rate = rate_calculator.tick()
            if ave_rate is not None:
                logger.info("Download rate (tiles/second): " + str(ave_rate))


    logger.debug("Telling queue processing has stopped...")
    tile_queue.join()
    logger.debug("Queue stopped processing")

    logger.debug("Signaling threads to halt")
    halt_event.set()

    logger.debug("Joining all downloader threads...")
    [thread.join() for thread in threads]
    logger.debug("Downloader threads joined")

def __download_tiles_from_queue(tile_type, tile_queue, tile_store, timeout,
        max_failures, halt_event, logger=None):
    """
    Downloads all the tiles in a queue for some type and stores them in the tile
    store. Will re-insert failed downloads into the queue for later processing,
    but only up to max_failures times. timeout specifies the amount of time in
    seconds downloading threads will wait for new tiles to enter the queue
    before giving up and ending their download loops. halt_event is an event
    object indicating whether we should stop downloading.
    """

    # use a default logger if none was specified
    logger = __get_null_logger() if logger is None else logger

    # get the current thread name for use in log messages
    tname = threading.current_thread().name

    # try to pull from the queue as long as the halt event hasn't happened
    while not halt_event.wait(0):
        try:
            # pull a tile from the queue
            fail_count, tile = tile_queue.get(True, timeout)

            try:
                # download and store the tile data
                logger.debug(tname + " downloading " + str(tile) +
                        " as " + str(tile_type) + "...")

                tile_data = tile.download(tile_type)
                logger.info("Downloaded " + str(len(tile_data)) + " bytes " +
                        "for " + str(tile))

                # log the number of retries it took if we failed at least once
                if fail_count > 0:
                    retry_count = max_failures - fail_count
                    logger.info("Took " + str(retry_count) + " retry attempt" +
                            ("" if retry_count == 1 else "s") +
                            " to download " + str(tile))

                tile_store.store(tile_type, tile, tile_data)

            except Tile.TileDownloadError, e:
                # common error message parameters
                t = str(tile)
                tt = str(tile_type)
                m = str(e.message)

                # retry if we haven't yet exceeded the max
                if fail_count < max_failures:
                    # TODO: there might be a dining-philosophers condition here.
                    # if all threads simultaneously arrive at a failed tile and
                    # then the queue fills up, there will be nobody to make more
                    # room in the queue.
                    tile_queue.put((fail_count + 1, tile))

                    rr = str(max_failures - (fail_count + 1))
                    logger.warning("Download of " + t +
                            " failed with message '" + m + "' " +
                            "(retries remaining: " + rr + ")")
                else:
                    # give up otherwise
                    logger.error("Download of " + t + " failed with message '" +
                            m + "' (out of retries)")

            # signal that we finished processing this tile
            tile_queue.task_done()

        # keep trying until told to halt
        except queue.Empty:
            continue

    logger.debug(tname + " got halt signal, exiting")

def parse_shape_file(shape_file):
    """
    Parses a shape file and returns a list of coordinates as tiles.

    Files are expected to be in the format:
      (<latitude_float0>, <longitude_float0>)\n
      (<latitude_float1>, <longitude_float1>)\n
      ...
      (<latitude_floatN>, <longitude_floatN>)\n
    """

    coords = []
    with open(shape_file, "r") as sf:
        for line in sf:
            # strip whitespace and parens, split by comma
            lat, lng = line.strip().strip("()").split(",")

            # strip remaining whitespace, cast to float, make tuple
            coords.append(Tile.from_mercator(float(lat), float(lng), 0))

    return coords

def __get_null_logger():
    """
    Creates a logging.Logger-like object with debug(), info(), warning(),
    error(), and critical() methods that soak up all log messages passed to
    them. Returns the logger object.
    """

    class NullLogger: pass
    null_logger = NullLogger()

    do_nothing = lambda *args, **kwargs: None

    null_logger.debug = do_nothing
    null_logger.info = do_nothing
    null_logger.warning = do_nothing
    null_logger.error = do_nothing
    null_logger.critical = do_nothing

    return null_logger

class Tile:
    """
    A tile representing both Mercator and Google Maps versions of the same info,
    a point/tile on the globe. This is not meant to be mutable, and is only a
    container for the values initially supplied. Changing values after
    initialization will NOT update other values!

    Conversion formulae gleaned from Jeremy R. Geerdes' post:
      http://groups.google.com/group/google-maps-api/msg/7a0aba451045ed94
    """

    # raised when we couldn't download a tile
    class TileDownloadError(Exception): pass

    # a simple class for tile types with a descriptive name and a URL 'v' value
    TileType = collections.namedtuple("TileType", ["name", "v"])

    # possible kinds of tile for initialization
    KIND_GOOGLE = "google"
    KIND_MERCATOR = "mercator"

    # our various tile types
    TYPE_BIKE = TileType("bike", "r")
    TYPE_MAP = TileType("map", "m")
    TYPE_OVERLAY = TileType("overlay", "h")
    TYPE_SATELLITE = TileType("satellite", "y")
    TYPE_SATELLITE_PLAIN = TileType("satellite_plain", "s")
    TYPE_TERRAIN = TileType("terrain", "p")
    TYPE_TERRAIN_PLAIN = TileType("terrain_plain", "t")

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
        string, or returns None if no data could be downloaded. Raises
        TileDownloadError when tile download fails.
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

        # pass exceptions along for the caller to handle
        except Exception, e:
            raise Tile.TileDownloadError(str(e))

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

    def __init__(*args, **kwargs): pass
    def store(*args, **kwargs): pass

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

        # make sure the database has our index, building it if necessary.
        # without this, we'd have to look up every tile to see if already
        # existed, which becomes unusably slow with lots of tiles (100000+).
        index = [
            ("x", pymongo.ASCENDING),
            ("y", pymongo.ASCENDING),
            ("zoom", pymongo.ASCENDING),
            ("tile_type.name", pymongo.ASCENDING),
            ("tile_type.v", pymongo.ASCENDING)
        ]
        self.collection.ensure_index(index, unique=True, drop_dups=True)

    def store(self, tile_type, tile, tile_data):
        """
        Store the tile in the database with a Unix update time in seconds. If a
        tile with the same data already exists, update it accordingly. This
        assumes that an index with unique keys has been added on x, y, zoom,
        tile_type.name, and tile_type.v.
        """

        tile = {
            # coordinates
            "x": int(tile.x),
            "y": int(tile.y),
            "zoom": int(tile.zoom),

            # tile type (we're expecting a collections.namedtuple)
            "tile_type": tile_type._asdict(),

            # image data as binary
            "image_data": bson.binary.Binary(tile_data),

            # update date, for eventually re-downloading 'old' tiles
            "update_date": int(time.time())
        }

        # add our tile to the collection, overwriting old data if it exists
        self.collection.insert(tile)

class RateCalculator:
    """
    Used to track and calculate rates.
    """

    def __init__(self, tick_rate_ms, window_size):
        if tick_rate_ms < 0:
            raise ValueError("Tick rate must be at least 0")

        if window_size < 1:
            raise ValueError("Window size must be at least 1")

        # how long we should go between ticks
        self.tick_rate_ms = tick_rate_ms

        # how many rates should be accumulated to calculate the running average
        self.window_size = window_size

        # rate list, first item is oldest rate
        self.window = []

        # how many tocks we've accumulated since the last tick
        self.tock_count = 0

        # time of the last tick
        self.last_tick_time = None

    def start(self):
        """
        Start calculating the rate.
        """

        self.window = []
        self.tock_count = 0
        self.last_tick_time = time.time()

    def reset(self):
        """
        Reset to initial state.
        """

        self.window = []
        self.tock_count = 0
        self.last_tick_time = None

    def tock(self):
        """
        Count an action towards the rate.
        """

        if self.last_tick_time is None:
            raise ValueError("Must start the calculator before tocking!")

        self.tock_count += 1

    def tick(self):
        """
        Return rate of tocks if we've reached the next tick time, otherwise
        None.
        """

        if self.last_tick_time is None:
            raise ValueError("Must start the calculator before ticking!")

        tt = time.time()
        if tt >= self.last_tick_time + (1.0 * self.tick_rate_ms / 1000):
            # calculate the current rate
            rate = 0.0
            if self.tock_count > 0:
                rate = self.tock_count / (tt - self.last_tick_time)

            # keep a running average of previous rates
            if len(self.window) >= self.window_size:
                self.window.pop(0)
            self.window.append(rate)

            window_sum = sum(self.window)
            ave_rate = 0.0
            if window_sum > 0:
                ave_rate = 1.0 * window_sum / len(self.window)

            # reset counters for next rate calculation
            self.tock_count = 0
            self.last_tick_time = tt

            # return the rate if we had reached the tick time
            return rate

        # return None otherwise, to indicate the tick time hasn't come yet
        return None

class Polygon:
    """
    A utility class for operations on lists of vertices.
    """

    # represents the bounding box of some points
    Bounds = collections.namedtuple("Bounds", ["top", "right", "bottom", "left"])

    class Edge:
        """
        Represents an edge used in the sorted edge table and active edge table.
        """

        def __init__(self, y_max, x_min, rise, run):
            self.y_max = y_max
            self.x_min = x_min
            self.rise = rise
            self.run = run

        def __str__(self):
            return repr(self)

        def __repr__(self):
            s = self.__class__.__name__ + "("
            s += ", ".join(map(repr, (self.y_max, self.x_min, self.rise,
                self.run)))
            s += ")"

            return s

    def __init__(self):
        raise NotImplemented(self.__class__.__name__ + " can't be instantiated")

    @staticmethod
    def get_bounds(*vertices):
        """
        Returns a Bounds object containing data about the bounding box that
        contains the given vertices. If multiple vertices are at the bounds, the
        first is used. If one vertex satisfies multiple bounds, it will be used
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
    def generate_vertex_pairs(vertices, exclude_horizontal=False):
        """
        Generates paired vertices from a list of vertices, including from last
        vertex to first vertex. If exclude_horizontal is True, horizontal edge
        pairs are not yielded.

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

            # only yield non-horizontal edges if we're exluding them
            if exclude_horizontal:
                if point[1] != last_point[1]:
                    yield (last_point, point)
            else:
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

        # remove identical start/end vertices as well
        while len(vertices) > 1 and vertices[0] == vertices[-1]:
            vertices.pop()

        # don't bother with calculations for corner cases
        if len(vertices) <= 1:
            for v in vertices:
                yield v
            return
        elif len(vertices) == 2:
            for point in Polygon.generate_line(*vertices):
                yield point
            return

        # get all lines, keeping only non-horizontal lines
        lines = [pair for pair in Polygon.generate_vertex_pairs(vertices, True)]

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
                    sorted_edges[y].append(Polygon.Edge(y_max, x_min, rise, run))

                    # keep the entries sorted by y_max then x_min
                    sorted_edges[y].sort(key=lambda e: (e.y_max, e.x_min))

        # list of active edges, those intersecting with the current scanline
        active_edges = []

        # starting y value is smallest value in SET with a non-empty bucket,
        # i.e. the top of our polygon's bounds.
        y = polygon_bounds.top[1]

        # continue while sorted edges or active edges have entries
        while len(sorted_edges.values()) > 0 or len(active_edges) > 0:
            # move y bucket into active edge list if the edges' y-min (the key
            # into sorted edges) is the current y.
            if y in sorted_edges:
                active_edges.extend(sorted_edges[y])
                del sorted_edges[y]

            # sort active edges by x coordinates
            active_edges.sort(key=lambda e: e.x_min)

            # fill between pairs of intersections (excluding the final new edge
            # if we added an odd number). keep track of the last yielded point
            # so we don't duplicate points at 'v'-shaped intersections.
            last_point = None
            for a, b in itertools.izip(*[iter(active_edges)] * 2):
                x_from = int(round(a.x_min))
                x_to = int(round(b.x_min)) + 1

                # round values to nearest whole number
                for x in xrange(x_from, x_to):
                    point = (x, y)

                    # don't yield duplicate points (happens at some vertices)
                    if point != last_point:
                        yield point

                    last_point = point

            # deactivate edges who's y-max is the current y
            active_edges = filter(lambda e: e.y_max != y, active_edges)

            # move to the next scanline
            y += 1

            # update x for non-vertical edges left in active edges
            for edge in active_edges:
                # update edge's x_min for next round if the edge isn't vertical
                if edge.run != 0:
                    # TODO: use incremental calculation
                    edge.x_min = edge.x_min + (1.0 * edge.run / edge.rise)

    @staticmethod
    def get_area(vertices):
        """
        Same as generate_area(), but returns a list instead of a generator.
        """

        return [point for point in Polygon.generate_area(vertices)]

if __name__ == "__main__":
    import argparse
    import sys
    import logging

    # constant values for zoom levels
    MIN_ZOOM = 0
    MAX_ZOOM = 21

    # various tile stores we're allowed to use
    TILE_STORES = {
        "null": NullTileStore,
        "file": FileTileStore,
        "mongo": MongoTileStore
    }

    # all the types of tiles available for download
    TILE_TYPES = {
        Tile.TYPE_BIKE.name: Tile.TYPE_BIKE,
        Tile.TYPE_MAP.name: Tile.TYPE_MAP,
        Tile.TYPE_OVERLAY.name: Tile.TYPE_OVERLAY,
        Tile.TYPE_SATELLITE.name: Tile.TYPE_SATELLITE,
        Tile.TYPE_SATELLITE_PLAIN.name: Tile.TYPE_SATELLITE_PLAIN,
        Tile.TYPE_TERRAIN.name: Tile.TYPE_TERRAIN,
        Tile.TYPE_TERRAIN_PLAIN.name: Tile.TYPE_TERRAIN_PLAIN,
    }

    # the levels of log verbosity we support
    LOG_LEVELS = {
        "silent": None,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }

    parser = argparse.ArgumentParser(
            description="Download an area of map tiles from Google maps.")

    parser.add_argument("-l", "--log-level", choices=LOG_LEVELS, default="info",
            help="set the log verbosity (default info)")
    parser.add_argument("-f", "--log-file", type=os.path.abspath, default=None,
            help="if specified, logs to the given file rather than the screen")

    parser.add_argument("-m", "--min-zoom", type=int, default=0,
            help="minimum zoom to download (" + str(MIN_ZOOM) + "-" +
            str(MAX_ZOOM) + ")")
    parser.add_argument("-z", "--max-zoom", type=int, default=0,
            help="maximum zoom to download (" + str(MIN_ZOOM) + "-" +
            str(MAX_ZOOM) + ")")

    parser.add_argument("-t", "--tile-type", default="map",
            choices=TILE_TYPES, help="type of tile to download (default map)")

    parser.add_argument("-n", "--num-threads", type=int, default=10,
            help="number of download threads to use (default 10)")

    parser.add_argument("shape_file", type=os.path.abspath,
            help="shape file to download")

    parser.add_argument("-s", "--tile-store", default="file",
            choices=["null", "file", "mongo"],
            help="where tiles are stored")

    parser.add_argument("-k", "--skip-to-tile", nargs=3, type=int, default=None,
            help="tile to skip to before downloading tiles (format 'x y zoom'")

    # TODO: add specific options for various tiles stores

    args = parser.parse_args()

    # enforce zoom levels (custom to prevent ultra-verbose default output)
    if args.min_zoom < MIN_ZOOM or args.min_zoom > MAX_ZOOM:
        print parser.format_usage().strip()
        print ("mapper.py: error: argument -m/--min-zoom: invalid zoom: " +
                repr(args.min_zoom) + " (must be between " + str(MIN_ZOOM) +
                "-" + str(MAX_ZOOM) + ")")
        sys.exit(1)

    if args.max_zoom < MIN_ZOOM or args.max_zoom > MAX_ZOOM:
        print parser.format_usage().strip()
        print ("mapper.py: error: argument -z/--max-zoom: invalid zoom: " +
                repr(args.max_zoom) + " (must be between " + str(MIN_ZOOM) +
                "-" + str(MAX_ZOOM) + ")")
        sys.exit(2)

    if args.max_zoom < args.min_zoom:
        print parser.format_usage().strip()
        print ("mapper.py: error: argument -z/--max-zoom: invalid zoom: " +
                repr(args.max_zoom) + " (must be larger than the min zoom)")
        sys.exit(3)

    # enforce thread count
    if args.num_threads < 1:
        print parser.format_usage().strip()
        print ("mapper.py: error: argument -n/--num-threads: invalid thread count: " +
                repr(args.num_threads) + " (must be >= 1)")
        sys.exit(4)

    # turn tile type string into a tile type object
    tile_type = TILE_TYPES[args.tile_type]

    # get the zoom levels we'll download (arg ranges are inclusive)
    zoom_levels = xrange(args.min_zoom, args.max_zoom + 1)

    # create a tile store based on the specified string
    tile_store = TILE_STORES[args.tile_store]()

    # set up a logger depending on the specified verbosity and file name
    logger = __get_null_logger()
    if LOG_LEVELS[args.log_level] is not None:
        logging.basicConfig(level=LOG_LEVELS[args.log_level],
                filename=args.log_file)
        logger = logging

    # build the skip-to-tile
    skip_to_tile = None
    if args.skip_to_tile is not None:
        skip_to_tile = Tile.from_google(args.skip_to_tile[0],
                args.skip_to_tile[1], args.skip_to_tile[2])

    # download the area from the shape file
    try:
        shape_vertices = parse_shape_file(args.shape_file)
        download_area(tile_type, shape_vertices, tile_store, zoom_levels,
                num_threads=args.num_threads, logger=logger,
                skip_to_tile=skip_to_tile)
    except KeyboardInterrupt:
        # exit and signal that we were interrupted
        logging.shutdown()
        sys.exit(10)

    # great success!
    logging.shutdown()
    sys.exit(0)

