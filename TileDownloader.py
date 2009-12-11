from Coordinates import MercatorCoord, TileCoord
import threading
import urllib2

from pprint import pprint

"""
URL Examples
------------
terrain:
  http://mt0.google.com/vt/v=app.115&hl=en&src=api&x=164&y=394&z=10&s=Galile

sattelite:
  http://khm1.google.com/kh/v=50&x=165&y=395&z=10&s=Ga

overlay:
  http://mt1.google.com/vt/lyrs=h@115&hl=en&src=api&x=163&y=396&z=10&s=Galil

map:
  http://mt1.google.com/vt/lyrs=m@115&hl=en&src=api&x=163&y=394&z=10&s=Gal

Notes:
 - 's' appears to be irrelevant, urls work without it
 - ???(0|1).google.com breaks down like so:
     mt = terrain, overlay, and map
     khm = sattelite tiles
 - google.com/??/ tells what type of tile to get from the server, like so:
     vt = terrain, overlay, and map types
     kh = sattelite tiles
 - google.com/xx/?=? tells what to get from the maps, overlay
     lyrs=h = overlay tiles
     lyrs=m = map tiles
"""

def main():
    t = TileDownloader([])

class TileDownloader(object):
    """Downloads map tiles using multiple threads"""
    
    def __init__(self, coord_list, num_threads = 10):
        # get the proxies we'll use to prevent Google from banning us ;)
        self._proxy_list = self.get_proxy_list()
    
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
        
        # open it and read the site's text contents
        proxy_text = urllib2.urlopen(request).read()
        
        # format the text by splitting out the thing after '<pre>' in the
        # original text and before '</pre>' in the previous split
        proxy_text = proxy_text.split("<pre>")[1].split("</pre>")[0]
        proxy_text = proxy_text.strip()
        
        # form a list from the lines
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
    
    def __init__(self, coord_list, proxy_list):
        
        threading.Thread.__init__(self)
    
    def run(self):
        pass

if __name__ == "__main__":
    main()
