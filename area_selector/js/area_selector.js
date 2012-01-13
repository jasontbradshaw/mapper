$(function () {
    // force less.js to stop caching files while developing!
    destroyLessCache("css");

    // keep track of currently active polygons
    var polygons = [];

    // keep track of currently pressed keys
    var pressedKeys = setupKeypressTracker();

    // build the main map
    var map = setupMap();

    // allow creation of polygons
    setupPolygon(map, polygons, pressedKeys);
});

// creates and returns an object that tracks currently pressed keyboard keys
var setupKeypressTracker = function () {
    // an object for tracking pressed keys
    var PressedKeys = function () {
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
    var pressedKeys = new PressedKeys();

    // update it when keys are pressed/released
    $(window).keydown(function (e) { pressedKeys.__addPressed(e.which); });
    $(window).keyup(function (e) { pressedKeys.__removePressed(e.which); });

    return pressedKeys;
};

// initialize the main map
var setupMap = function () {
    var mapCanvas = $("#map");

    var mapOptions = {
        center: new google.maps.LatLng(0, 0),
        zoom: 2,
        mapTypeId: google.maps.MapTypeId.ROADMAP,

        // pare the UI down to the bare necessities
        disableDefaultUI: true,
        panControl: true,
        zoomControl: true,
        mapTypeControl: true,
    };

    var map = new google.maps.Map(mapCanvas.get(0), mapOptions);
    return map;
};

// make clicking create a polygon on the map
var setupPolygon = function (map, polygons, pressedKeys) {
    // keys for collection points and deleting polygons
    var collectorKeyCode = 16; // shift
    var deleteKeyCode = 17; // control

    // collect coordinates as a line that we can convert to a polygon later
    var polyline = null;

    $(window).keyup(function (e) {
        // create a polygon when done collecting points
        if (e.which === collectorKeyCode) {

            // turn the polyline into a polygon if it's long enough
            if (polyline.getPath().getLength() > 1) {
                // create a new polygon on the map from the temporary polyline
                var polygon = new google.maps.Polygon({
                    map: map,
                    paths: polyline.getPath(),
                    editable: true,
                });

                // make clicking the polygon with the delete key held remove it
                google.maps.event.addListener(polygon, "click", function (e) {
                    if (pressedKeys.isPressed(deleteKeyCode)) {
                        polygon.setMap(null);
                    }
                });
            }

            // remove the temporary polyline from the map and delete it
            polyline.setMap(null);
            polyline = null;
        }
    });

    // build the line if the collect key is held down
    google.maps.event.addListener(map, "click", function (e) {
        if (pressedKeys.isPressed(collectorKeyCode)) {
            // create the polyline if it doesn't exist yet
            if (polyline === null) {
                polyline = new google.maps.Polyline({
                    map: map,
                    editable: true,
                });
            }

            // add the clicked coordinates to the line
            polyline.getPath().push(e.latLng);
        }
    });
};

// destroys the localStorage copy of CSS that less.js creates
var destroyLessCache = function (pathToCss) { // e.g. '/css/' or '/stylesheets/'
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
};
