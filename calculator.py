#!/usr/bin/env python

from coordinates import MercatorCoord, TileCoord

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
    coords = [
        MercatorCoord(30.23029793153857, -97.82398223876953, 16),
        MercatorCoord(30.36665473179746, -97.78861999511719, 16),
        MercatorCoord(30.342361542010376, -97.55859375, 16)
    ]

    print len(TileCalculator.get_line(coords[0], coords[1], 18))
