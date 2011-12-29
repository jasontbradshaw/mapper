#!/usr/bin/env python

from math import pi, atan, exp, sin, log
import os
import Queue
import random
import threading
import urllib2

class Tile:
    """
    A tile representing both Mercator and Google Maps versions of the same info,
    a point/tile on the globe. This is not meant to be mutable, and is only a
    container for the values initially supplied. Changing values after
    initialization will NOT update other values!
    """

    def __init__(self, kind, a, b, zoom, tile_size):
        """
        This should only really be called by the static constructor methods. a
        and b take on either x/y or latitude/longitude depending on the kind of
        tile this will be. The other kind's values are filled dynamically from
        the given kind. If a Google tile is being created, the
        latitude/longitude are set to the upper-left corner of the given tile's
        x and y values.
        """

        # zoom must be positive
        assert zoom >= 0

        # kept for reference, the size of tiles in pixels
        self.tile_size = tile_size

        # shared by both kinds of tile
        self.zoom = zoom

        # the latitude, longitude, x, and y of this tile
        self.latitude = None
        self.longitude = None
        self.x = None
        self.y = None

        # update internal values from the given information
        if kind == "mercator":
            self.latitude = a
            self.longitude = b

            # calculate x and y coords from latitude and longitude
            lat = self.latitude
            lng = self.longitude

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

        elif kind == "google":
            self.x = a
            self.y = b

            # calculate latitude and longitude for upper-left corner of the tile
            x = self.x
            y = self.y

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

            latitude = max(-90.0, latitude) # cap at -90 degrees
            longitude = min(90.0, longitude) # cap at 90 degrees

        else:
            raise ValueError("Unrecognized tile kind: " + kind)

    @staticmethod
    def from_mercator(latitude, longitude, zoom, tile_size=256):
        """
        Creates a tile from Mercator coordinates and returns it.
        """

        return Tile("mercator", latitude, longitude, zoom, tile_size)

    @staticmethod
    def from_google(x, y, zoom, tile_size=256):
        """
        Creates a tile from Google coordinates and returns it.
        """

        return Tile("google", x, y, zoom, tile_size)

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

class TileDownloader:
    """Downloads map tiles using multiple threads."""

    # valid tile types available for download
    # NOTE: only map, satellite (normal/plain) and overlay work consistently
    TILE_TYPE_MAP = "map"
    TILE_TYPE_TERRAIN = "terrain"
    TILE_TYPE_TERRAIN_PLAIN = "terrain_plain"
    TILE_TYPE_OVERLAY = "overlay"
    TILE_TYPE_SATELLITE = "satellite"
    TILE_TYPE_SATELLITE_PLAIN = "sattelite_plain"
    TILE_TYPE_BIKE = "bike"

    # all the tile types mapped to their url letter
    TYPE_MAP = {
        TILE_TYPE_MAP: "m",
        TILE_TYPE_TERRAIN: "p",
        TILE_TYPE_TERRAIN_PLAIN: "t",
        TILE_TYPE_OVERLAY: "h",
        TILE_TYPE_SATELLITE: "y",
        TILE_TYPE_SATELLITE_PLAIN: "s",
        TILE_TYPE_BIKE: "r"
    }

    def __init__(self, tiles):
        raise NotImplemented("Can't instantiate " + self.__class__.__name__)

    @staticmethod
    def download(tile_type, tiles, num_threads=4):
        """Downloads some tiles using the given type."""

        # downloads the tiles in the given queue until no tiles remain
        def download_tiles(tile_type, tile_queue):
            while 1:
                try:
                    tile = tile_queue.get_nowait()
                    TileDownloader.download_tile(tile_type, tile)
                except Queue.Empty:
                    break

        # put all our tiles into a queue so all threads can share them
        tile_queue = Queue.Queue()
        [tile_queue.put(tile) for tile in tiles]

        # assign threads their respective tile lists
        thread_pool = []
        for i in xrange(num_threads):
            thread = threading.Thread(target=download_tiles,
                    args=[tile_type, tile_queue])
            thread_pool.append(thread)
            thread.start()

        # wait for all the threads to finish
        [thread.join() for thread in thread_pool]

    @staticmethod
    def download_tile(tile_type, tile):
        """Downloads a single tile with the given type."""

        # create the download directory, if it doesn't exist
        try:
            os.mkdir(tile_type)
        except OSError, e:
            # ignore 'directory already exists' errors, propogate all others
            if e.errno != 17:
                raise e

        # fill in a random server number [0-3]
        url = "http://mt%d.google.com/vt/v=" % random.randint(0, 3)

        # specify type of tiles we want
        if tile_type not in TileDownloader.TYPE_MAP:
            print "Tile type " + tile_type + "' was not recognized."
        else:
            url += TileDownloader.TYPE_MAP[tile_type]

        # get ready for next parameters...
        url += "&"

        # insert coordinates and zoom from the given tile
        url += "x=" + str(tile.x)
        url += "&"
        url += "y=" + str(tile.y)
        url += "&"
        url += "z=" + str(tile.zoom)

        # spoof the user agent again (just in case this time)
        agent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US) "
        agent += "AppleWebKit/532.5 (KHTML, like Gecko) "
        agent += "Chrome/4.0.249.30 Safari/532.5"

        request = urllib2.Request(url, headers={"User-Agent": agent})

        # save the tile to a file (in a style, by the while...).
        # overwrites previous content without asking
        fname = os.path.join(str(tile_type),
                             (str(tile.x) + "-" +
                              str(tile.y) + "-" +
                              str(tile.zoom)))

        try:
            # download and save the tile data
            tile_data = urllib2.urlopen(request).read()

            # write the tile to its file
            with open(fname, "w") as tfile:
                tfile.write(tile_data)
        except urllib2.HTTPError, e:
            print "Failed to download '" + str(tile) + "', aborting."
            raise e

class TileCalculator:
    """
    Calculates all the tiles in a region from the specified zoom level down.
    """

    def __init__(self):
        raise NotImplemented("Can't instantiate " + self.__class__.__name__)

    def get_area(vertices):
        """
        Gets all the tiles in an area and returns them as a set. Vertices are
        assumed to be in-order (CW/CCW and starting vertex are irrelevant).
        """

        # don't do calculations if we weren't given any vertices
        if len(vertices) == 0:
            return set()

        # ensure all our vertices have the same zoom level
        if not all([v.zoom == vertices[0].zoom for v in vertices]):
            raise ValueError("All vertices must have the same zoom level.")

        # initialize the set with our initial vertices
        result = set(vertices)

        # find the top, bottom, and left-most vertices (y increases down, x
        # increases right).
        top = None
        bottom = None
        left = None
        for vertex in result:
            # left
            if vertex.x < left.x:
                left = vertex

            # top
            if vertex.y < top.y:
                top = vertex

            # bottom
            if vertex.y > bottom.y:
                bottom = vertex

        # add lines between consecutive vertices
        prev_vertex = tile_vertices[0]
        for vertex in tile_vertices[1:]:
            result.update(TileCalculator.get_line(prev_vertex, vertex))
            prev_vertex = vertex

        # cast rays left to right, top to bottom, adding tiles that lie within
        # the polygon (calculated using edge intersection counts).
        for y in xrange(top.y, bottom.y):
            # TODO: handle corners!
            pass

        return result

    @staticmethod
    def get_line(tile0, tile1):
        """
        Bresenham's line drawing algorithm, modified to yield all the
        tiles between two tiles at a certain zoom, including endpoints.
        Tiles are not guaranteed to be in any specific order.
        """

        # we must be using the same zoom levels for tiles!
        if tile0.zoom != tile1.zoom:
            raise ValueError("Endpoints must have identical zoom levels.")

        # make some shorthand variables
        x0 = tile0.x
        y0 = tile0.y
        x1 = tile1.x
        y1 = tile1.y

        steep = abs(y1 - y0) > abs(x1 - x0)

        if steep:
            x0, y0 = y0, x0
            x1, y1 = y1, x1

        if x0 > x1:
            x0, x1 = x1, x0
            y0, y1 = y1, y0

        deltax = x1 - x0
        deltay = abs(y1 - y0)
        error = deltax / 2
        y = y0

        # set the ystep
        if y0 < y1:
            ystep = 1
        else:
            ystep = -1

        # add all the points to our list
        line_list = [tile0]
        for x in xrange(x0, x1):
            if steep:
                line_list.append(Tile.from_google(y, x, tile0.zoom))
            else:
                line_list.append(Tile.from_google(x, y, tile0.zoom))

            error = error - deltay

            if error < 0:
                y = y + ystep
                error = error + deltax

        # add the final coord, and return the point list
        line_list.append(tile1)
        return line_list

if __name__ == "__main__":

    tile = Tile.from_mercator(30.2832, -97.7362, 18)
    print "Mercator:", tile.latitude, tile.longitude, tile.zoom
    print "Google:", tile.x, tile.y, tile.zoom

    coords = [
        Tile.from_mercator(30.23029793153857, -97.82398223876953, 18),
        Tile.from_mercator(30.36665473179746, -97.78861999511719, 18),
        Tile.from_mercator(30.342361542010376, -97.55859375, 18)
    ]

    print len(TileCalculator.get_line(coords[0], coords[1]))

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

    TileDownloader.download(TileDownloader.TILE_TYPE_MAP, tiles)
