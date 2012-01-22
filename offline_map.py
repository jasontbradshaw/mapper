#!/usr/bin/env python

import flask

import pymongo
import bson

app = flask.Flask(__name__);

# connect to mongo so we can pull tiles from it
DB = pymongo.Connection("127.0.0.1", 27017)["mapper"]["tiles"]

@app.route("/<v>", methods=("GET",))
def get_tile(v):
    # the things we need to put together our map
    x = flask.request.args.get("x")
    y = flask.request.args.get("y")
    zoom = flask.request.args.get("zoom")

    # try to find the requested tile
    tile_query = {
        "x": int(x),
        "y": int(y),
        "zoom": int(zoom),
        "tile_type.v": v,
    }

    tile = DB.find_one(tile_query)

    # return a 404 if we couldn't find the given tile
    if tile is None:
        flask.abort(404)

    # give the user back our decoded image data
    response = tile["image_data"]
    content_type = "image/png"
    return flask.Response(response=response, content_type=content_type)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9000, debug=True)
