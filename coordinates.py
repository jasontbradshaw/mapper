#!/usr/bin/env python

from math import pi, atan, exp, sin, log

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

if __name__ == "__main__":
    merc = MercatorCoord(30.2832, -97.7362, 18)
    tile = TileCoord(59902, 107915, 18)

    print merc.convert()
    print tile.convert()
