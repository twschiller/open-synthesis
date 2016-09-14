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
var path = require("path");
var webpack = require("webpack");
var BundleTracker = require("webpack-bundle-tracker");
var ExtractTextPlugin = require("extract-text-webpack-plugin");

module.exports = {
    context: __dirname,
    // entry point of our app. assets/js/index.js should require other js modules and dependencies it needs
    entry: "./assets/js/index",
    output: {
        path: path.resolve("./assets/bundles/"),
        filename: "[name]-[hash].js"
    },
    plugins: [
        new BundleTracker({filename: "./webpack-stats.json"}),
        // https://webpack.github.io/docs/list-of-plugins.html#provideplugin
        new webpack.ProvidePlugin({
            $: "jquery",
            jQuery: "jquery"
        }),
        new ExtractTextPlugin("style.css", {
            allChunks: true
        }),
        // https://webpack.github.io/docs/list-of-plugins.html#uglifyjsplugin
        new webpack.optimize.UglifyJsPlugin({
            compress: {
                warnings: false
            }
        }),
        // https://webpack.github.io/docs/list-of-plugins.html#dedupeplugin
        new webpack.optimize.DedupePlugin(),
        // https://webpack.github.io/docs/list-of-plugins.html#occurrenceorderplugin
        new webpack.optimize.OccurrenceOrderPlugin(true)
    ],
    module: {
        loaders: [
            {
                test: /\.css$/,
                loader: ExtractTextPlugin.extract("style-loader", "css-loader")
            },
            {
                test: /\.(eot|svg|ttf|woff|woff2)$/,
                loader: "file?name=public/fonts/[name].[ext]"
            }
        ]
    },
    resolve: {
        modulesDirectories: ["node_modules", "bower_components"],
        extensions: ["", ".js", ".jsx"]
    }
};
