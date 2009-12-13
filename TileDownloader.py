from Coordinates import MercatorCoord, TileCoord
import threading
import urllib2
from urllib2 import HTTPError
import random
import os

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
  http://mt0.google.com/vt/v=p&x=164&y=394&z=10

overlay:
  http://mt0.google.com/vt/lyrs=h&x=163&y=396&z=10

map:
  http://mt0.google.com/vt/x=163&y=394&z=10

"""

def main():
    # these tiles represent roughly the UT Austin campus
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
    
    t = TileDownloader("s", tiles, 5)
    t.download()

class TileDownloader(object):
    """Downloads map tiles using multiple threads"""
    
    def __init__(self, tile_type, tile_list, num_threads = 5):
        # get the proxies we'll use to prevent Google from banning us ;)
        self._type = tile_type
        
        self._tile_lists = self.split_list( tile_list, num_threads )
        
    def download(self):
        """Manages the thread 'pool' that downloads the tiles"""
        
        # assign threads their respective tile lists
        thread_pool = []
        for lst in self._tile_lists:
            thread_pool.append( 
                DownloadThread(lst, self.get_proxy_list(), self._type) )
        
        # start all the threads we just created
        for thread in thread_pool:
            # calling 'run()' on a thread waits until it's done, completely
            # defeating the purpose.  we call 'start()', which works as you'd
            # expect
            thread.start()
        
    def split_list(self, lst, n):
        """Splits a list into roughly equal parts"""
        
        # ensure we don't split into more parts than we have
        n = min( len(lst), n )
        
        # round-robin the items into the list of lists (ie. 'split_lists')
        counter = 0

        # can't use '[[]] * n' because that simply copies a reference to the 
        # same empty list into split_lists n times
        split_lists = []
        for i in xrange(n):
            split_lists.append( [] )
        
        for item in lst:
            # wrap counter to distribute items evenly
            if counter >= n:
                counter = 0
            
            # add this item to one of the bins in split_lists
            split_lists[counter].append( item )
            
            counter += 1
            
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
            
            # save the tile to a file (in a style, by the while...).
            # overwrites previous content without asking
            fname = os.path.join( str( self._dir ),
                                  str( self._type ),
                                  ( str( tile.get_x() ) + "-" +
                                    str( tile.get_y() ) + "-" +
                                    str( tile.get_zoom() ) ) )
            
            # download and read the tile data
            try:
                tile_data = urllib2.urlopen(request).read()
            except HTTPError, e:
                print "Failed to download '" + url + "', aborting."
                break
            
            # write the tile to its file
            with open(fname, "w") as tfile:
                tfile.write( tile_data )
            
    def generate_url(self, tile_coord):
        """Generates a new download url based on the given TileCoord."""
        
        # fill in a random server number [0-3]
        url = "http://mt%d.google.com/vt/v=" % ( random.randint(0, 3) )
        
        # specify type of tiles we want
        # map
        if self._type == "m":
            url += "m"
        
        # terrain
        if self._type == "t":
            url += "p"
        
        # overlay
        if self._type == "o":
            url += "h"
        
        # satellite
        if self._type == "s":
            url += "y"
        
        # get ready for next parameters...
        url += "&"
            
        # insert coordinates and zoom from the given TileCoord
        url += "x=" + str( tile_coord.get_x() )
        url += "&"
        url += "y=" + str( tile_coord.get_y() )
        url += "&"
        url += "z=" + str( tile_coord.get_zoom() )
        
        return url

if __name__ == "__main__":
    main()
