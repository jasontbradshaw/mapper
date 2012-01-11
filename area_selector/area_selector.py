#!/usr/bin/env python

import flask
from flask import Flask, redirect, url_for

app = flask.Flask(__name__)

@app.route("/")
def root():
    return redirect(url_for("static", filename="area_selector.html"))

if __name__ == "__main__":
    app.run()
