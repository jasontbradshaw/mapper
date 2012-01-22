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

    // build the main map and allow polygon creation
    var map = setupMap();
    setupOfflineMapType(map);
    setupViewPersistence(map);
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

// add our custom offline map type to the map
var setupOfflineMapType = function (map) {
    var offlineMapType = new google.maps.ImageMapType({
        tileSize: new google.maps.Size(256, 256),

        name: "Map (Offline)",
        alt: "Offline Road Map",

        maxZoom: 21,
        minZoom: 0,

        // returns a URL to our local server that returns the map from a cache
        getTileUrl: function (coord, zoom) {
            var mapType = "m";
            var x = coord.x;
            var y = coord.y;

            // build our map request URL
            var url = "http://127.0.0.1:9000/";
            url += mapType;
            url += "?x=" + x;
            url += "&y=" + y;
            url += "&zoom=" + zoom;

            return url;
        },
    });

    var mapTypeId = "offline_roadmap";

    // make the map controls a dropdown menu
    map.setOptions({
        mapTypeControlOptions: {
            mapTypeIds: [mapTypeId, google.maps.MapTypeId.ROADMAP],
            style: google.maps.MapTypeControlStyle.DROPDOWN_MENU,
        },
    });

    // add the coord map type to the map as an overlay
    map.mapTypes.set(mapTypeId, offlineMapType);
    map.setMapTypeId(mapTypeId);
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
