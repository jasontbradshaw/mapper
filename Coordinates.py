#!/usr/bin/env python

from math import pi, atan, exp, sin, log

def main():
    print MercatorCoord(30.2832, -97.7362, 18).convert()
    print TileCoord(59902, 107915, 18).convert()

class MercatorCoord(object):
    """A Mercator projection coordinate"""
    
    def __init__(self, lat, lon, zoom):
        self._latitude = lat
        self._longitude = lon
        self._zoom = zoom
        
    def get_latitude(self):
        return self._latitude
    
    def get_longitude(self):
        return self._longitude
    
    def get_zoom(self):
        return self._zoom
    
    def convert(self):
        """
        Convert this to a TileCoord
        Conversion formula gleaned from Jeremy R. Geerdes' post:
        http://groups.google.com/group/google-maps-api/msg/7a0aba451045ed94
        """
        
        lng = self.get_longitude()
        lat = self.get_latitude()
        zoom = self.get_zoom()
        
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
    
    def __str__(self):
        return "%f, %f, %d" % (self._latitude, self._longitude, self._zoom)

class TileCoord(object):
    """A Google Maps tile coordinate"""
    
    def __init__(self, x, y, zoom):
        # x and y are tile-level only (ie. they are not in-tile coords)
        self._x = x
        self._y = y
        self._zoom = zoom
    
    def get_x(self):
        return self._x
    
    def get_y(self):
        return self._y
    
    def get_zoom(self):
        return self._zoom
    
    def convert(self):
        """
        Convert this to a MercartorCoord
        Conversion formula gleaned from Jeremy R. Geerdes' post:
        http://groups.google.com/group/google-maps-api/msg/7a0aba451045ed94
        """
        
        x = self.get_x()
        y = self.get_y()
        zoom = self.get_zoom()
        
        longitude = ( ( (x * 256) - (256 * (2**(zoom - 1))) ) /
                      ( (256 * (2**zoom)) / 360.0 ) )
        
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

    def __str__(self):
        return "%d, %d, %d" % (self._x, self._y, self._zoom)

if __name__ == "__main__":
    main()
