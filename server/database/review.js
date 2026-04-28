/* jshint esversion: 8, sub: true */
const mongoose = require("mongoose");

const Schema = mongoose.Schema;

const reviews = new Schema({
  id: {
    type: Number,
    required: true,
  },
  name: {
    type: String,
    required: true,
  },
  dealership: {
    type: Number,
    required: true,
  },
  review: {
    type: String,
    required: true,
  },
  purchase: {
    type: Boolean,
    required: true,
  },
  purchase_date: {
    type: String,
    required: true,
  },
  car_make: {
    type: String,
    required: true,
  },
  car_model: {
    type: String,
    required: true,
  },
  car_year: {
    type: Number,
    required: true,
  },
  author_id: {
    type: Number,
    default: null,
  },
  author_username: {
    type: String,
    default: null,
  },
});

module.exports = mongoose.model("reviews", reviews);
