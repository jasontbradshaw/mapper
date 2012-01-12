$(function () {
    // force less.js to stop caching files while developing!
    destroyLessCache("css");
    var map = setupMap();
    var polygons = [];
    setupPolygon(map, polygons);
});

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
var setupPolygon = function (map, polygons) {
    // keep track of whether the the collector key key is pressed
    var collectorKeyCode = 16; // the 'shift' key
    var collectorKeyEngaged = false;

    // track whether we should delete a polygon when clicked
    var deleteKeyCode = 17; // the 'control' key
    var deleteKeyEngaged = false;

    // collect coordinates so we can later form a polygon
    var collectedCoords = [];
    var collectedMarkers = [];

    $(window).keydown(function (e) {
        if (e.which === collectorKeyCode) {
            collectorKeyEngaged = true;
        }

        if (e.which === deleteKeyCode) {
            deleteKeyEngaged = true;
        }
    });

    $(window).keyup(function (e) {
        // create a polygon when done collecting points
        if (e.which === collectorKeyCode) {
            collectorKeyEngaged = false;

            // turn the collected coordinates into a polygon
            if (collectedCoords.length >= 1) {

                // create a new polygon
                var polygon = new google.maps.Polygon({
                    paths: collectedCoords,
                    editable: true,
                });

                // add it to the map
                polygon.setMap(map);

                // make double-clicking the polygon remove it
                google.maps.event.addListener(polygon, "click", function (e) {
                    // delete the polygon if it was requested
                    if (deleteKeyEngaged) {
                        polygon.setMap(null);
                    }
                });

                // remove the progress markers
                for (var i = 0; i < collectedMarkers.length; i++) {
                    collectedMarkers[i].setMap(null);
                }

                // clear the coordinates and markers for the next polygon
                collectedCoords = [];
                collectedMarkers = [];
            }
        }
        // mark that we released the keycode
        else if (e.which === deleteKeyCode) {
            deleteKeyEngaged = false;
        }
    });

    google.maps.event.addListener(map, "click", function (e) {
        // collect coordinates if desired
        if (collectorKeyEngaged) {
            // add a marker where we clicked, to show our progress
            var marker = new google.maps.Marker({
                map: map,
                position: e.latLng,
                flat: true,
                title: e.latLng.lat() + ", " + e.latLng.lng(),
            });

            // store them so we can make a polygon from them later
            collectedCoords.push(e.latLng);
            collectedMarkers.push(marker);
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
