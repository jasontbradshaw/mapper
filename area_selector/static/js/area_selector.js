$(function () {
    // force less.js to stop caching files while developing!
    destroyLessCache("css");
    setupMap();
});

var setupMap = function () {
    var mapCanvas = $("#map");

    var mapOptions = {
        center: new google.maps.LatLng(0, 0),
        zoom: 2,
        mapTypeId: google.maps.MapTypeId.ROADMAP,

        // customize the UI
        disableDefaultUI: true,
        panControl: true,
        zoomControl: true,
        mapTypeControl: true,
    };

    var map = new google.maps.Map(mapCanvas.get(0), mapOptions);
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
