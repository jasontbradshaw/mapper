$(function () {
    // destroys the localStorage copy of CSS that less.js creates
    (function (pathToCss) { // e.g. '/css/' or '/stylesheets/'
        if (!window.localStorage || !less || less.env !== 'development') {
            return;
        }
        var host = window.location.host;
        var protocol = window.location.protocol;
        var keyPrefix = protocol + '//' + host + pathToCss;

        for (var key in window.localStorage) {
            if (key.indexOf(keyPrefix) === 0) {
                delete window.localStorage[key];
            }
        }

        console.log("Destroyed less.js cache");
    })("css");

    // keep track of keyboard and mouse state
    var keypressTracker = setupKeypressTracker();
    var mouseTracker = setupMouseTracker();

    setupMenu();

    // build the main map and allow polygon creation
    var map = setupMap();
    setupCustomMapTypes(map);
    setupViewPersistence(map);
    setupControls(map);
    setupPolygon(map, keypressTracker, mouseTracker);
});

// create and return an object that always holds the current mouse coordinates
var setupMouseTracker = function () {
    // an object for tracking mouse location
    var MouseTracker = function () {
        this.__x = 0;
        this.__y = 0;

        // returns the last known mouse position
        this.getMousePos = function () {
            return [this.__x, this.__y];
        };

        this.__setMousePos = function (x, y) {
            this.__x = x;
            this.__y = y;
        };
    };

    var mouseTracker = new MouseTracker();

    // modify it every time the mouse moves
    $(window).mousemove(function (e) {
        mouseTracker.__setMousePos(e.pageX, e.pageY);
    });

    return mouseTracker;
};

// creates and returns an object that tracks currently pressed keyboard keys
var setupKeypressTracker = function () {
    // an object for tracking pressed keys
    var KeypressTracker = function () {
        this.__map = {};

        this.__addPressed = function (keyCode) {
            this.__map["key_" + keyCode] = true;
        };

        this.__removePressed = function (keyCode) {
            delete this.__map["key_" + keyCode];
        };

        // returns whether the given keycode is pressed
        this.isPressed = function (keyCode) {
            return this.__map.hasOwnProperty("key_" + keyCode);
        };
    };

    // create our own instance of the keypress tracker
    var keypressTracker = new KeypressTracker();

    // update it when keys are pressed/released
    $(window).keydown(function (e) { keypressTracker.__addPressed(e.which); });
    $(window).keyup(function (e) { keypressTracker.__removePressed(e.which); });

    return keypressTracker;
};

// make the menu hide when it is clicked on, or off, of
var setupMenu = function () {
    var menu = $("#menu");
    var body = $("body");

    var menuHide = function () {
        menu.hide();
    };

    // hide the menu after it or the body is clicked
    body.click(menuHide);
    menu.click(menuHide);
}

// initialize the main map
var setupMap = function () {
    var mapCanvas = $("#map");

    var map = new google.maps.Map(mapCanvas.get(0), {
        center: new google.maps.LatLng(0, 0),
        zoom: 2,
        mapTypeId: google.maps.MapTypeId.ROADMAP,

        // pare the UI down to the bare necessities
        disableDefaultUI: true,
        panControl: true,
        zoomControl: true,
        mapTypeControl: true,
    });

    return map;
};

// add custom map types to the map
var setupCustomMapTypes = function (map) {
    var CoordMapType = function () {};
    CoordMapType.prototype.tileSize = new google.maps.Size(256, 256);
    CoordMapType.prototype.maxZoom = 21;

    // names for the map type
    CoordMapType.prototype.name = "Coordinates";
    CoordMapType.prototype.alt = "Tile Coordinates Map Type";

    // return a basic overlay skeleton with classes that we style in css
    CoordMapType.prototype.getTile = function (coord, zoom, ownerDocument) {
        var div = $("<div></div>")
            .addClass("coord_overlay_tile")
            .append($("<div></div>")
                    .addClass("coord_text")
                    .text(coord.x + ", " + coord.y)
           );

        return div.get(0);
    };

    // add the coord map type to the map as an overlay
    map.overlayMapTypes.insertAt(0, new CoordMapType());
};

// puts our custom controls into the map
var setupControls = function (map) {
    // add custom controls for the help text and the zoom indicator
    var helpBox = $("#help");
    map.controls[google.maps.ControlPosition.BOTTOM_CENTER].push(helpBox.get(0));

    var zoomIndicator = $("#zoom_indicator");
    zoomIndicator.text(map.getZoom()); // set zoom to map's current zoom level
    map.controls[google.maps.ControlPosition.LEFT_TOP].push(zoomIndicator.get(0));

    // update the zoom indicator when the zoom level changes
    google.maps.event.addListener(map, "zoom_changed", function () {
        zoomIndicator.text(map.getZoom());
    });
};

// stores the maps' location to persist it between page loads
var setupViewPersistence = function (map) {

    // go to the last coordinates of the map if there were any
    if (localStorage.getItem("lastMapView") !== null) {
        var lastView = JSON.parse(localStorage.getItem("lastMapView"));
        map.panTo(new google.maps.LatLng(lastView.latitude, lastView.longitude));
        map.setZoom(lastView.zoom);
    }

    // store the current view of the map so we can reload it next time
    var storeLastView = function () {
        localStorage.setItem("lastMapView", JSON.stringify({
            zoom: map.getZoom(),
            latitude: map.getCenter().lat(),
            longitude: map.getCenter().lng(),
        }));
    };

    // make zoom and center change store the view information
    google.maps.event.addListener(map, "center_changed", function () {
        storeLastView();
    });

    google.maps.event.addListener(map, "zoom_changed", function () {
        storeLastView();
    });
};

// make clicking create a polygon on the map, and right-clicking show its menu
var setupPolygon = function (map, keypressTracker, mouseTracker) {
    // keys for collection points and deleting polygons
    var collectorKeyCode = 16; // shift

    // collect coordinates as a line that we can convert to a polygon later
    var polyline = null;

    // specify the various colors we'll use for polygons
    var normalFillColor = "black";
    var normalFillOpacity = 0.4;
    var normalStrokeColor = "black";
    var normalStrokeOpacity = 0.6;

    var highlightFillColor = "green";
    var highlightFillOpacity = 0.4;
    var highlightStrokeColor = "#0ac200";
    var highlightStrokeOpacity = 0.6;

    $(window).keyup(function (e) {
        // create a polygon when done collecting points
        if (e.which === collectorKeyCode) {

            // turn the polyline into a polygon if it's long enough
            if (polyline != null && polyline.getPath().getLength() > 1) {
                // track the polygon's z value so we can change it later
                var polygonZ = 0;

                // create a new polygon on the map from the temporary polyline
                var polygon = new google.maps.Polygon({
                    map: map,
                    paths: polyline.getPath(),
                    editable: true,

                    // give it some fancier colors
                    fillColor: normalFillColor,
                    fillOpacity: normalFillOpacity,
                    strokeColor: normalStrokeColor,
                    strokeOpacity: normalStrokeOpacity,

                    zIndex: polygonZ,
                });

                // make right-clicking the polygon show the menu for it
                google.maps.event.addListener(polygon, "rightclick", function (e) {
                    showMenu(polygon, e.latLng, mouseTracker);
                });

                // make clicking change the z-index, to cycle through
                // overlapping polygons.
                google.maps.event.addListener(polygon, "click", function (e) {
                    var newZIndex = polygonZ - 1;
                    polygon.setOptions({
                        zIndex: newZIndex,
                    });

                    // continue tracking the polygon's zIndex
                    polygonZ = newZIndex;
                });

                // make hovering over the polygon change its color
                google.maps.event.addListener(polygon, "mouseover", function (e) {
                    polygon.setOptions({
                        fillColor: highlightFillColor,
                        fillOpacity: highlightFillOpacity,
                        strokeColor: highlightStrokeColor,
                        strokeOpacity: highlightStrokeOpacity,
                    });
                });

                google.maps.event.addListener(polygon, "mouseout", function (e) {
                    polygon.setOptions({
                        fillColor: normalFillColor,
                        fillOpacity: normalFillOpacity,
                        strokeColor: normalStrokeColor,
                        strokeOpacity: normalStrokeOpacity,
                    });
                });
            }

            // remove the temporary polyline from the map and delete it
            polyline.setMap(null);
            polyline = null;
        }
    });

    // build the line if the collect key is held down
    google.maps.event.addListener(map, "click", function (e) {
        if (keypressTracker.isPressed(collectorKeyCode)) {
            // create the polyline if it doesn't exist yet
            if (polyline === null) {
                polyline = new google.maps.Polyline({
                    map: map,
                    editable: true,

                    strokeColor: normalStrokeColor,
                    strokeOpacity: normalStrokeOpacity,
                });
            }

            // add the clicked coordinates to the line
            polyline.getPath().push(e.latLng);
        }
    });
};

// shows the menu at the mouse location, and makes the options reference the
// given polygon.
var showMenu = function (polygon, clickLatLng, mouseTracker) {
    var menu = $("#menu");

    // get all menu items, and make sure they're visible (we disable selectively)
    var deleteVertexItem = $(".menu_item.delete_vertex").show();
    var deleteVertexSeparator = deleteVertexItem.next().show();
    var deletePolygonItem = $(".menu_item.delete_polygon").show();
    var exportItem = $(".menu_item.export").show();

    // remove old bindings for the menu items (they refer to old polygons)
    deleteVertexItem.unbind("click");
    deleteVertexItem.unbind("hover");
    deletePolygonItem.unbind("click");
    exportItem.unbind("click");

    // hide the 'delete vertex' item if there aren't enough vertices
    if (polygon.getPath().getLength() <= 2) {
        deleteVertexItem.hide();
        deleteVertexSeparator.hide();
    }

    // the marker for the vertex we'll delete if the menu item is clicked
    var deleteMarker = null;

    // remove the vertex delete marker if it exists
    var deleteVertexMarker = function () {
        if (deleteMarker !== null) {
            deleteMarker.setMap(null);
            deleteMarker = null;
        }
    };

    // make hovering over the 'delete vertex' show the vertex to be deleted
    deleteVertexItem.hover(function () {
        // only show the marker if there are enough vertices
        if (polygon.getPath().getLength() > 2) {
            var nearestIndex = getNearestVertex(polygon, clickLatLng);
            var nearestVertex = polygon.getPath().getAt(nearestIndex);

            // create set the delete marker
            deleteVertexMarker(); // prevent duplicates
            deleteMarker = new google.maps.Marker({
                map: polygon.getMap(),
                position: nearestVertex,
            });
        }
    }, deleteVertexMarker);

    // make clicking 'delete vertex' remove the nearest vertex
    deleteVertexItem.click(function () {
        // only remove a vertex if there are more than two
        if (polygon.getPath().getLength() > 2) {
            // remove the nearest vertex
            var vertexIndex = getNearestVertex(polygon, clickLatLng);
            polygon.getPath().removeAt(vertexIndex);
        }

        // remove the vertex delete marker if it exists
        deleteVertexMarker();
    });

    // make clicking 'delete polygon' remove the given polygon
    deletePolygonItem.click(function () {
        polygon.setMap(null);
    });

    // make clicking 'export' offer the current polygon for download
    exportItem.click(function () {
        exportPolygon(polygon);
    });

    // move the menu to the current mouse location and show it
    var mousePos = mouseTracker.getMousePos();
    menu.css("left", mousePos[0]);
    menu.css("top", mousePos[1]);
    menu.show();
};

// returns an the index in the polygon of the nearest vertex to the given coords
var getNearestVertex = function (polygon, coords) {
    var nearestIndex = -1;
    var nearestDistance = null;
    polygon.getPath().forEach(function (vertex, index) {
        // compute the distance between the click and the coord
        var dist = google.maps.geometry.spherical.computeDistanceBetween(
            vertex, coords);
        if (nearestIndex === -1 || dist < nearestDistance) {
            nearestIndex = index;
            nearestDistance = dist;
        }
    });

    return nearestIndex;
};

// offer up the given polygon for download
var exportPolygon = function (polygon) {
    var polyString = polygonToString(polygon);

    // create a data URI and put the encoded data in it. we use the MIME type of
    // application/octet-stream to force a file download.
    var uriContent = "data:application/octet-stream;charset=utf-8,";
    uriContent += encodeURIComponent(polyString);

    // tell the window to offer a download of the polygon data
    location.href = uriContent;
};

// collect the latitude/longitude vertices in a polygon as a string with the
// format: (lat0, lng0)\n(lat1, lng1)\n...(latN, lngN)\n
var polygonToString = function (polygon) {
    var stringData = "";
    var addCoord = function (coord) {
        // create line-separated tuples of (latitude, longitude)
        stringData += "(" + coord.lat() + ", " + coord.lng() + ")";
        stringData += "\n";
    };

    // gather the polygon's coordinates into a string
    polygon.getPath().forEach(function (coord) {
        addCoord(coord);
    });

    return stringData;
};
