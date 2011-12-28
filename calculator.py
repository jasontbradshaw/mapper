#!/usr/bin/env python

import math
from pprint import pprint

from Coordinates import MercatorCoord, TileCoord

def main():
    coords = [ MercatorCoord(30.23029793153857, -97.82398223876953, 16),
               MercatorCoord(30.36665473179746, -97.78861999511719, 16),
               MercatorCoord(30.342361542010376, -97.55859375, 16) ]
    
    t = TileCalculator(coords, 16)
    
    print len( t.get_line(coords[0], coords[1], 18) )

class TileCalculator:
    """
    Calculates all the tiles in a region from the specified zoom level down.
    Needs a list containing all the in-order vertices of a polygon to do so.
    """
    
    def __init__(self, merc_coords, start_zoom):
        """Convert the MercatorCoords to TileCoords."""
        
        assert len(merc_coords) > 0
        
        # the highest zoom level we sill start from, moving downward
        self._start_zoom = start_zoom
        
        self._merc_coords = merc_coords
    
    def calculate(self):
        """Calculate the interior tiles from the given vertices."""
        
        grid = make_grid( self._start_zoom )
        
        # calculate the cells we need to download by going though every zoom
        # level from the starting zoom to the largest possible
        for zoom in xrange(zoom, 19):
            pass
        
    def make_grid(self, zoom):
        """Create an appropriately sized grid for a given zoom level."""
        
        # convert the first tile so we can set the min/max vars from something
        first_tile = self._merc_coords[0]
        first_tile.set_zoom(zoom)
        first_tile = first_tile.convert()
        
        # intialize the min/max variables so we can calculate them for real
        max_x = first_tile.get_x()
        max_y = first_tile.get_y()
        min_x = max_x
        min_y = max_y
        
        # find the 'sides' of the grid by their respective x/y values and
        # record them so we can size and create our grid
        for coord in self._merc_coords[1:]: # skip the first one (we did it)
            coord.set_zoom(zoom)
            
            # make it into a tile coord
            coord = coord.convert()
            
            # find the sides of the grid
            max_x = max( coord.get_x(), max_x )
            max_y = max( coord.get_y(), max_y )
            min_x = min( coord.get_x(), min_x )
            min_y = min( coord.get_y(), min_y )
        
        # calculate the grid dimensions, making sure it's at least 1x1
        grid_width = max(max_x - min_x, 1)
        grid_height = max(max_y - min_y, 1)
        
        # create the empty grid and intialize it to 'False'
        grid = []
        for i in xrange(grid_width):
            grid.append( [False] * grid_height )
        
        return grid
    
    def get_line(self, merc0, merc1, zoom):
        """
        Bresenham's line drawing algorithm, modified to yield all the
        points between x and y at a certain zoom (excluding endpoints).
        """
        
        # set the zoom in the MercatorCoords so we can convert them
        merc0.set_zoom(zoom)
        merc1.set_zoom(zoom)
        
        # convert our MercatorCoords to TileCoords
        tile0 = merc0.convert()
        tile1 = merc1.convert()
        
        # make some shorthand variables
        x0 = tile0.get_x()
        y0 = tile0.get_y()
        x1 = tile1.get_x()
        y1 = tile1.get_y()
        
        steep = abs(y1 - y0) > abs(x1 - x0)
        
        if steep:
            temp = x0
            x0 = y0
            y0 = temp
            
            temp = x1
            x1 = y1
            y1 = temp
        
        if x0 > x1:
            temp = x0
            x0 = x1
            x1 = temp
            
            temp = y0
            y0 = y1
            y1 = temp
        
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
        line_list = []
        for x in xrange(x0, x1):
            if steep:
                line_list.append( TileCoord(y, x, zoom) )
            else:
                line_list.append( TileCoord(x, y, zoom) )
            
            error = error - deltay
            
            if error < 0:
                y = y + ystep
                error = error + deltax
        
        return line_list
    
if __name__ == "__main__":
    main()
