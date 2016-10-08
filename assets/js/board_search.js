/*
 * Open Synthesis, an open platform for intelligence analysis
 * Copyright (C) 2016 Open Synthesis Contributors. See CONTRIBUTING.md
 * file at the top-level directory of this distribution.
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

var $ = require("jquery");

require("selectize");

$(document).ready(function(){
    $("#board-search").selectize({
        valueField: "url",
        labelField: "board_title",
        searchField: ["board_title", "board_desc"],
        maxItems: 1,
        create: false,
        render: {
            option: function(item){
                return "<div>"+ item.board_title + "</div>";
            }
        },
        load: function(query, callback){
            if(!query.length) return callback();
            $.ajax({
                url: "/api/boards/?query="+query,
                type: "GET",
                error: function(){
                    callback();
                },
                success: function(data){
                    callback(data);
                }
            });
        },
        onItemAdd: function(value){
            window.location.href = value;
        }
    });
});
