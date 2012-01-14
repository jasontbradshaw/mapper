$(function () {
    // force less.js to stop caching files while developing!
    destroyLessCache("css");

    // keep track of keyboard and mouse state
    var keypressTracker = setupKeypressTracker();
    var mouseTracker = setupMouseTracker();

    setupMenu();

    // build the main map and allow polygon creation
    var map = setupMap();
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

// make clicking create a polygon on the map, and right-clicking show its menu
var setupPolygon = function (map, keypressTracker, mouseTracker) {
    // keys for collection points and deleting polygons
    var collectorKeyCode = 16; // shift

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

                // make right-clicking the polygon show the menu for it
                google.maps.event.addListener(polygon, "rightclick", function (e) {
                    showMenu(polygon, mouseTracker);
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
                });
            }

            // add the clicked coordinates to the line
            polyline.getPath().push(e.latLng);
        }
    });
};

// shows the menu at the mouse location, and makes the options reference the
// given polygon.
var showMenu = function (selectedPolygon, mouseTracker) {
    var menu = $("#menu");
    var deleteItem = $(".menu_item.delete");
    var exportItem = $(".menu_item.export");

    // remove old bindings for the menu items
    deleteItem.unbind("click");
    exportItem.unbind("click");

    // make clicking 'delete' remove the given polygon
    deleteItem.click(function () {
        selectedPolygon.setMap(null);
    });

    // make clicking 'export' offer the current polygon for download
    exportItem.click(function () {
        exportPolygon(selectedPolygon);
    });

    // move the menu to the current mouse location and show it
    var mousePos = mouseTracker.getMousePos();
    menu.css("left", mousePos[0]);
    menu.css("top", mousePos[1]);
    menu.show();
};

// offer up the given polygon for download
var exportPolygon = function (polygon) {
    console.log("Exporting polygon...");
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
