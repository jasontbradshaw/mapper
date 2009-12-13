from Coordinates import MercatorCoord, TileCoord
import threading
import urllib2
import random
import os

from pprint import pprint

"""
URL Examples
------------
sattelite:
  http://khm1.google.com/kh/v=50&x=165&y=395&z=10&s=Ga

terrain:
  http://mt0.google.com/vt/v=app.115&hl=en&src=api&x=164&y=394&z=10&s=Galile

overlay:
  http://mt1.google.com/vt/lyrs=h@115&hl=en&src=api&x=163&y=396&z=10&s=Galil

map:
  http://mt1.google.com/vt/lyrs=m@115&hl=en&src=api&x=163&y=394&z=10&s=Gal

Notes:
 - 's' appears to be irrelevant, urls work without it
 - ???[0-3].google.com breaks down like so:
     mt = terrain, overlay, and map tiles
     khm = sattelite tiles
 - google.com/??/ tells what type of tile to get from the server, like so:
     vt = terrain, overlay, and map types
     kh = sattelite tiles
 - google.com/xx/?=? tells what to get from the maps, overlay
     lyrs=h = overlay tiles
     lyrs=m = map tiles

Sanitized (Working) Examples:
sattelite:
  http://khm0.google.com/kh/v=50&x=165&y=395&z=10

terrain:
  http://mt0.google.com/vt/v=app.115&x=164&y=394&z=10

overlay:
  http://mt0.google.com/vt/lyrs=h&x=163&y=396&z=10

map:
  http://mt0.google.com/vt/x=163&y=394&z=10

"""

def main():
    tiles = [ TileCoord(59902, 107915, 18),
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
              TileCoord(59906, 107919, 18) ]
    
    t = TileDownloader("t", tiles)
    t.download()

class TileDownloader(object):
    """Downloads map tiles using multiple threads"""
    
    def __init__(self, tile_type, tile_list, num_threads = 10):
        # get the proxies we'll use to prevent Google from banning us ;)
        self._type = tile_type
        
        self._split_lists = self.split_list( tile_list, num_threads )
        
    def download(self):
        """Manages the thread pool that downloads the tiles"""
        
        # assign threads their respective tile lists
        thread_pool = []
        for lst in self._split_lists:
            thread_pool.append( DownloadThread(lst, self.get_proxy_list()) )
        
        for thread in thread_pool:
            thread.run()
        
    def split_list(self, lst, n):
        """Splits a list into roughly equal parts"""
        
        # ensure we don't split into more parts than we can have
        n = min( len(lst), n )
        
        part_size = len(lst) / n
        
        # split the list and store it in the result list
        split_lists = []
        for i in xrange(n):
            # as long as this isn't the last section of the list
            if i < n - 1:
                split_lists.append( lst[0:part_size] )
                
                # trim lst down by the amount we just split it by
                lst = lst[part_size:]
            else:
                split_lists.append( lst[0:] ) # append the remaining piece
        
        for l in split_lists:
            print len(l)
            
        return split_lists
    
    def get_proxy_list(self):
        # the site we'll get our list from
        url  = "http://www.digitalcybersoft.com"
        url += "/ProxyList/fresh-proxy-list.shtml"
        
        # spoof the user agent (turns out the admin doesn't like scripts...)
        # we'll use a Chrome dev build, just for super-nerdy kicks :)
        agent  = "Mozilla/5.0 (X11; U; Linux x86_64; en-US) "
        agent += "AppleWebKit/532.5 (KHTML, like Gecko) "
        agent += "Chrome/4.0.249.30 Safari/532.5"
        request = urllib2.Request(url, headers = {"User-Agent": agent})
        
        # open it and read the site's HTML contents
        proxy_text = urllib2.urlopen(request).read()
        
        # format the text by splitting out the thing after '<pre>' in the
        # original text and before '</pre>' in the previous split
        proxy_text = proxy_text.split("<pre>")[1].split("</pre>")[0]
        proxy_text = proxy_text.strip()
        
        # form a list from the lines we just got
        proxy_list = proxy_text.split("\n")
        
        # format each line to the 'ProxyHandler' specification:
        #     http://<ip-address>:<port>/
        # see the 'urllib2' documentation (at the very bottom) for more info
        for i in xrange( len(proxy_list) ):
            # takes only the 'address:port' from the list and formats it
            proxy_list[i] = "http://" + proxy_list[i].split()[0] + "/"
        
        #pprint( proxy_list )
        return proxy_list

class DownloadThread(threading.Thread):
    """Downloads given tiles using a proxy list"""
    
    def __init__( self, tile_list, proxy_list, tile_type = "m",
                  destination_directory = "" ):
        
        self._tile_list = tile_list
        self._proxy_list = proxy_list
        self._dir = destination_directory
        
        # used by function 'generate_url'
        self._type = tile_type
        
        # needs to be called by convention
        threading.Thread.__init__(self)
    
    def run(self):
        """Downloads the given tiles"""
        
        # create the download directory, if it doesn't exist
        try:
            os.mkdir( os.path.join( str(self._dir), str(self._type) ) )
        except OSError, e:
            # ignore preexisting directory, since we probably created it
            pass
        
        # spoof the user agent again (just in case this time)
        agent  = "Mozilla/5.0 (X11; U; Linux x86_64; en-US) "
        agent += "AppleWebKit/532.5 (KHTML, like Gecko) "
        agent += "Chrome/4.0.249.30 Safari/532.5"
        
        # download every TileCoord this thread was given
        for tile in self._tile_list:
            # build the url we'll use to download this tile
            url = self.generate_url( tile )
            
            request = urllib2.Request(url, headers = {"User-Agent": agent})
            
            # save the tile to a file (in a style, by the while...)
            fname = os.path.join( str( self._dir ),
                                  str( self._type ),
                                  ( str( tile.get_x() ) + "-" +
                                    str( tile.get_y() ) + "-" +
                                    str( tile.get_zoom() ) ) )
            
            with open(fname, "w") as tfile:
                # download, read, then write the tile data
                tfile.write( urllib2.urlopen(request).read() )
                
    def generate_url(self, tile_coord):
        """Generates a new download url based on the tile_type given."""
        
        url = "http://"
        
        # select the approproate server name (map, terrain, or overlay)
        if self._type == "m" or self._type == "t" or self._type == "o":
            url += "mt"
        else: # satellite
            url += "khm"
        
        # choose a random server number
        url += str( random.randint(0, 3) )
        url += ".google.com/"
        
        # select the correct identifier
        if self._type == "m" or self._type == "t" or self._type == "o":
            url += "vt"
        else:
            url += "kh"
        
        url += "/"
        
        # specify type of tiles ('m' needs no special parameters)
        if self._type == "t":
            url += "v=app.115&"
        
        if self._type == "o":
            url += "lyrs=h&"
        
        if self._type == "s":
            url += "v=50&"
        
        # insert coordinates and zoom from the given TileCoord
        url += "x=" + str( tile_coord.get_x() )
        url += "&"
        url += "y=" + str( tile_coord.get_y() )
        url += "&"
        url += "z=" + str( tile_coord.get_zoom() )
        
        return url

if __name__ == "__main__":
    main()
