#!/usr/bin/env python

from math import pi, atan, exp, sin, log
import os
import Queue
import random
import threading
import urllib2

class MercatorCoord:
    """A Mercator projection coordinate."""

    def __init__(self, lat, lon, zoom):
        self.latitude = lat
        self.longitude = lon
        self.zoom = zoom

    def convert(self):
        """
        Convert this to a TileCoord.
        Conversion formula gleaned from Jeremy R. Geerdes' post:
        http://groups.google.com/group/google-maps-api/msg/7a0aba451045ed94
        """

        lng = self.longitude
        lat = self.latitude
        zoom = self.zoom

        # absolute pixel coordinates
        x_abs = ( round(256 * (2**(zoom - 1))) +
                  (lng * ((256 * (2**zoom)) / 360)) )

        y_exp = sin( (lat * pi) / 180 )
        y_exp = max(-0.9999, y_exp) # cap at -0.9999
        y_exp = min(0.9999, y_exp) # cap at 0.9999

        y_abs = ( round(256 * (2**(zoom - 1))) +
              ( (0.5 * log((1 + y_exp) / (1 - y_exp))) *
                ((-256 * (2**zoom)) / (2 * pi)) ) )

        # tile coordinates (tile-level resolution)
        x_tile = int(x_abs / 256)
        y_tile = int(y_abs / 256)

        # relative coordinates (pixel-level resolution, relative to tile)
        #x_rel = x % 256
        #y_rel = y % 256

        return TileCoord(x_tile, y_tile, zoom)

    def __repr__(self):
        return (self.__class__.__name__ + "(" +
                str(self.latitude) + ", " +
                str(self.longitude) + ", " +
                str(self.zoom) + ")")

    def __str__(self):
        return repr(self)

    def __hash__(self):
        # hash using our coordinates
        result = 17

        # we convert all numbers to floats to get better hash results
        result += hash(self.latitude * 1.0) * 31
        result += hash(self.longitude * 1.0) * 13
        result += hash(self.zoom * 1.0) * 11

        return result

    def __eq__(self, other):
        return (isinstance(other, MercatorCoord) and
                other.latitude == self.latitude and
                other.longitude == self.longitude and
                other.zoom == self.zoom)

class TileCoord:
    """A Google Maps tile coordinate."""

    def __init__(self, x, y, zoom):
        # x and y are tile-level only (ie. they are not in-tile coords)
        self.x = x
        self.y = y
        self.zoom = zoom

    def convert(self):
        """
        Convert this to a MercartorCoord.
        Conversion formula gleaned from Jeremy R. Geerdes' post:
        http://groups.google.com/group/google-maps-api/msg/7a0aba451045ed94
        """

        x = self.x
        y = self.y
        zoom = self.zoom

        longitude = ( ( (x * 256) - (256 * (2**(zoom - 1))) ) /
                      ( (256 * (2**zoom)) / 360.0 ) )

        # normalize longitude
        while longitude > 180:
            longitude -= 360

        while longitude < -180:
            logitude += 360

        lat_exp = ( ( (y * 256) - (256 * (2**(zoom - 1))) ) /
                    ( (-256 * (2**zoom)) / (2 * pi) ) )
        latitude = ( ( (2 * atan(exp(lat_exp))) - (pi / 2) ) / (pi / 180) )

        latitude = max(-90.0, latitude) # cap at -90 degrees
        longitude = min(90.0, longitude) # cap at 90 degrees

        return MercatorCoord(latitude, longitude, zoom)

    def __repr__(self):
        return (self.__class__.__name__ + "(" +
                str(self.x) + ", " + str(self.y) + ", " + str(self.zoom) + ")")

    def __str__(self):
        return repr(self)

    def __hash__(self):
        # hash using our coordinates
        result = 43

        # we convert all numbers to floats to get better hash results
        result += hash(self.x * 1.0) * 13
        result += hash(self.y * 1.0) * 11
        result += hash(self.zoom * 1.0) * 31

        return result

    def __eq__(self, other):
        return (isinstance(other, TileCoord) and
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

        # insert coordinates and zoom from the given TileCoord
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

    def get_area(merc_coords, zoom):
        """
        Gets all the tiles in an area for some zoom level and returns them as a
        set. Coordinates are assumed to be in-order, and the polygon they
        describe to be non-complex (have no overlapping edges). Coordinates are
        constrained to the given zoom.
        """

        # don't do calculations if we we'rent given any vertices
        if len(merc_coords) == 0:
            return set()

        # make sure all the coords have the same zoom level
        tile_vertices = []
        for m in merc_coords:
            # create a copy with the required zoom, then convert to a tile coord
            m_copy = MercatorCoord(m.latitude, m.longitude, zoom)
            tile_vertices.append(m_copy.convert())

        # initialize the set with our initial vertices
        result = set(tile_vertices)

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
            result.update(TileCalculator.get_line(
                prev_vertex.convert(), vertex.convert(), zoom))
            prev_vertex = vertex

        # cast rays left to right, top to bottom, adding tiles that lie within
        # the polygon (calculated using edge intersection counts).
        for y in xrange(top.y, bottom.y):
            # TODO: handle corners!
            pass

        return result

    @staticmethod
    def get_line(merc0, merc1, zoom):
        """
        Bresenham's line drawing algorithm, modified to yield all the
        tiles between merc0 and merc1 at a certain zoom, including endpoints.
        Tiles are not guaranteed to be in any specific order.
        """

        # set the zoom in the MercatorCoords so we can convert them
        merc0.zoom = zoom
        merc1.zoom = zoom

        # convert our MercatorCoords to TileCoords
        tile0 = merc0.convert()
        tile1 = merc1.convert()

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
                line_list.append(TileCoord(y, x, zoom))
            else:
                line_list.append(TileCoord(x, y, zoom))

            error = error - deltay

            if error < 0:
                y = y + ystep
                error = error + deltax

        # add the final coord, and return the point list
        line_list.append(tile1)
        return line_list

if __name__ == "__main__":
    merc = MercatorCoord(30.2832, -97.7362, 18)
    tile = TileCoord(59902, 107915, 18)

    print merc.convert(), tile
    print tile.convert(), merc

    coords = [
        MercatorCoord(30.23029793153857, -97.82398223876953, 16),
        MercatorCoord(30.36665473179746, -97.78861999511719, 16),
        MercatorCoord(30.342361542010376, -97.55859375, 16)
    ]

    print len(TileCalculator.get_line(coords[0], coords[1], 18))

    # these tiles represent roughly the UT Austin campus
    tiles = [
        TileCoord(59902, 107915, 18),
        TileCoord(59903, 107915, 18),
        TileCoord(59904, 107915, 18),
        TileCoord(59905, 107915, 18),
        TileCoord(59906, 107915, 18),

        TileCoord(59902, 107916, 18),
        TileCoord(59903, 107916, 18),
        TileCoord(59904, 107916, 18),
        TileCoord(59905, 107916, 18),
        TileCoord(59906, 107916, 18),

        TileCoord(59902, 107917, 18),
        TileCoord(59903, 107917, 18),
        TileCoord(59904, 107917, 18),
        TileCoord(59905, 107917, 18),
        TileCoord(59906, 107917, 18),

        TileCoord(59902, 107918, 18),
        TileCoord(59903, 107918, 18),
        TileCoord(59904, 107918, 18),
        TileCoord(59905, 107918, 18),
        TileCoord(59906, 107918, 18),

        TileCoord(59902, 107919, 18),
        TileCoord(59903, 107919, 18),
        TileCoord(59904, 107919, 18),
        TileCoord(59905, 107919, 18),
        TileCoord(59906, 107919, 18)
    ]

    TileDownloader.download(TileDownloader.TILE_TYPE_MAP, tiles)
