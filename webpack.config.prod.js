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

const { mergeWithCustomize, customizeArray } = require("webpack-merge");
const common = require("./webpack.config.base.js");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

module.exports = mergeWithCustomize({
  customizeArray: customizeArray({
    "entry.*": "prepend",
  }),
})(common, {
  mode: "production",
  optimization: {
    usedExports: true,
    minimizer: [
      "...", // Preserve the native JS minifier
      new CssMinimizerPlugin(),
    ],
  },
  output: {
    filename: "[name]-[contenthash].min.js",
    chunkFilename: "[name]-[contenthash].bundle.min.js",
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: "css/[name]-[contenthash].min.css",
      chunkFilename: "css/[id]-[contenthash].min.css",
      ignoreOrder: false, // Enable to remove warnings about conflicting order
    }),
  ],
});
