/*
 * Open Synthesis, an open platform for intelligence analysis
 * Copyright (C) 2016-2020 Open Synthesis Contributors. See CONTRIBUTING.md
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

const path = require('path');
const merge = require('webpack-merge');
const common = require('./webpack.config.base.js');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = merge.strategy({plugins: 'prepend'})(common, {
    mode: 'development',
    devtool: 'inline-source-map',
    // https://webpack.js.org/configuration/watch/
    // https://webpack.js.org/configuration/watch/#saving-in-webstorm
    watchOptions: {
        ignored: /node_modules/
    },
    output: {
        filename: '[name].js' ,
        chunkFilename: '[name].bundle.js',
    },
    plugins: [
        new MiniCssExtractPlugin({
            path: path.resolve('./openach-frontend/bundles/css/'),
            filename: 'css/[name].css',
            chunkFilename: 'css/[id].css',
            ignoreOrder: false, // Enable to remove warnings about conflicting order
        }),
    ],
    optimization: {
        minimize: false,
    }
});
