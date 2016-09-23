/*
 * Open Synthesis, an open platform for intelligence analysis
 * Copyright (C) 2016  Todd Schiller
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

// Adapted from: https://github.com/django-notifications/django-notifications/blob/master/notifications/static/notifications/notify.js
"use strict";

var $ = require("jquery");

// sessionStorage key for the last known number of unread notifications
var NOTIFICATION_KEY = "unread_notifications";
var NOTIFY_REFRESH_PERIOD_MILLIS = 15 * 1000;
var MAX_RETRIES = 5;

/**
 * Returns a function that queries the number of unread notifications and sets the text of badge to the number.
 *
 * Re-queries the server every NOTIFY_REFRESH_PERIOD_MILLIS milliseconds. Stops querying the server if more than
 * MAX_RETRIES consecutive requests fail.
 *
 * @param badge the badge JQuery selector
 * @param {string} url the url to request
 * @returns {Function} function that updates the unread notification count
 */
function fetch_api_data(badge, url) {
    var consecutiveMisfires = 0;
    return function() {
        $.get(url, function(data){
            consecutiveMisfires = 0;
            badge.text(data.unread_count);
            window.sessionStorage.setItem(NOTIFICATION_KEY, data.unread_count);
        })
        .fail(function(){
            consecutiveMisfires++;
        })
        .always(function(){
            if (consecutiveMisfires <= MAX_RETRIES) {
                setTimeout(fetch_api_data(badge, url), NOTIFY_REFRESH_PERIOD_MILLIS);
            } else {
                badge.text("!");
                badge.prop("title", "No connection to server");
            }
        });
    };
}

// NOTE: in practice, there will only be one element that has a data-notify-api-url attribute
$("[data-notify-api-url]").each(function(index, badge){
    var elt = $(badge);
    setTimeout(fetch_api_data(elt, elt.data("notify-api-url")), 1000);
    var previous = window.sessionStorage.getItem(NOTIFICATION_KEY);
    if (previous !== null) {
        elt.text(previous);
    }
});
