#!/usr/bin/env python

import os
import Queue
import random
import threading
import urllib2

from coordinates import MercatorCoord, TileCoord

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

if __name__ == "__main__":
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
