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
import "bootstrap";
import "bootstrap-datepicker";
import "selectize";

import "src/board_search";
import "src/notify";

import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-datepicker/dist/css/bootstrap-datepicker.min.css";
import "selectize/dist/css/selectize.css";
import "selectize/dist/css/selectize.bootstrap3.css";
import "css/sharing.css";
import "css/boards.css";

$("form[name='switchLanguageForm']").change(function(){
    $(this).submit();
});

$(".selectize").selectize();
