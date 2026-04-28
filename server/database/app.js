/* jshint esversion: 8, sub: true */
const express = require("express");
require("dotenv").config();
const mongoose = require("mongoose");
const fs = require("fs");
const cors = require("cors");
const app = express();
let httpServer;
let isShuttingDown = false;

const requireEnv = (name) => {
  const value = process.env[name];
  if (!value || String(value).trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
};

const PORT = Number(requireEnv("PORT"));
const MONGODB_URI = requireEnv("MONGODB_URI");
const DB_NAME = requireEnv("DB_NAME");
const CORS_ORIGIN = requireEnv("CORS_ORIGIN");
const SEED_ON_START =
  requireEnv("SEED_ON_START").toLowerCase() === "true";

// Configure Mongo connection timeouts and monitor connection lifecycle events.
const MONGODB_OPTIONS = {
  dbName: DB_NAME,
  serverSelectionTimeoutMS: 10000,
  connectTimeoutMS: 10000,
  socketTimeoutMS: 45000,
};

mongoose.connection.on("connected", () => {
  console.log(`MongoDB connected: ${DB_NAME}`);
});

mongoose.connection.on("error", (error) => {
  console.error("MongoDB connection error:", error);
});

mongoose.connection.on("disconnected", () => {
  console.warn("MongoDB disconnected.");
});

app.use(cors({ origin: CORS_ORIGIN }));
app.use(express.json());
app.use(require("body-parser").urlencoded({ extended: false }));

const reviews_data = JSON.parse(
  fs.readFileSync(require("path").join(__dirname, "data", "reviews.json"), "utf8"),
);
const dealerships_data = JSON.parse(
  fs.readFileSync(require("path").join(__dirname, "data", "dealerships.json"), "utf8"),
);

const Reviews = require("./review");

const Dealerships = require("./dealership");

// Atomic ID generation for review inserts.
const CounterSchema = new mongoose.Schema(
  {
    _id: { type: String, required: true },
    seq: { type: Number, required: true, default: 0 },
  },
  { versionKey: false },
);
const Counter = mongoose.model("Counter", CounterSchema, "counters");

const getNextReviewId = async () => {
  const counter = await Counter.findOneAndUpdate(
    { _id: "reviews" },
    { $inc: { seq: 1 } },
    { new: true, upsert: true },
  );
  return counter.seq;
};

const syncReviewCounter = async () => {
  const maxReview = await Reviews.findOne().sort({ id: -1 }).select({ id: 1 });
  const maxReviewId = maxReview ? maxReview.id : 0;

  await Counter.updateOne(
    { _id: "reviews" },
    { $max: { seq: maxReviewId } },
    { upsert: true },
  );

  console.log(`[bootstrap] Review ID counter synced to at least ${maxReviewId}`);
};

// Step 3.4: Validate and normalize incoming review payloads before DB writes.
const validateReviewPayload = (data) => {
  if (!data || typeof data !== "object") {
    return { valid: false, message: "Request body must be a JSON object." };
  }

  const requiredTextFields = [
    "name",
    "review",
    "purchase_date",
    "car_make",
    "car_model",
  ];

  for (const field of requiredTextFields) {
    if (typeof data[field] !== "string" || data[field].trim() === "") {
      return {
        valid: false,
        message: `Field '${field}' is required.`,
      };
    }
  }

  const dealership = Number(data.dealership);
  if (!Number.isInteger(dealership) || dealership <= 0) {
    return {
      valid: false,
      message: "Field 'dealership' is required.",
    };
  }

  const carYear = Number(data.car_year);
  if (!Number.isInteger(carYear) || carYear < 1886) {
    return {
      valid: false,
      message: "Field 'car_year' is required.",
    };
  }

  let purchase = data.purchase;
  if (typeof purchase === "string") {
    if (purchase.toLowerCase() === "true") {
      purchase = true;
    } else if (purchase.toLowerCase() === "false") {
      purchase = false;
    }
  }

  if (typeof purchase !== "boolean") {
    return {
      valid: false,
      message: "Field 'purchase' is required.",
    };
  }

  return {
    valid: true,
    normalized: {
      name: data.name.trim(),
      dealership,
      review: data.review.trim(),
      purchase,
      purchase_date: data.purchase_date.trim(),
      car_make: data.car_make.trim(),
      car_model: data.car_model.trim(),
      car_year: carYear,
    },
  };
};

// Standard error response shape for all API failures.
const sendError = (res, status, code, message, details = undefined) => {
  const payload = {
    error: {
      code,
      message,
    },
  };

  if (details) {
    payload.error.details = details;
  }

  return res.status(status).json(payload);
};

// Step 3.3: Enforce id uniqueness at database level for seeded and runtime writes.
const ensureDatabaseIndexes = async () => {
  await Reviews.collection.createIndex({ id: 1 }, { unique: true });
  await Dealerships.collection.createIndex({ id: 1 }, { unique: true });
  console.log("[bootstrap] Ensured unique indexes on reviews.id and dealerships.id");
};

// Seed helper used during startup only when seeding is enabled.
// Keeps startup idempotent by inserting data only if collections are empty.
const seedDatabase = async () => {
  const reviewsCount = await Reviews.countDocuments();
  const dealershipsCount = await Dealerships.countDocuments();

  if (reviewsCount === 0) {
    await Reviews.insertMany(reviews_data.reviews);
    console.log(`Seeded ${reviews_data.reviews.length} review documents.`);
  } else {
    console.log("Reviews collection already has data; skipping seed.");
  }

  if (dealershipsCount === 0) {
    await Dealerships.insertMany(dealerships_data.dealerships);
    console.log(`Seeded ${dealerships_data.dealerships.length} dealership documents.`);
  } else {
    console.log("Dealerships collection already has data; skipping seed.");
  }
};

// Graceful shutdown handler to close HTTP server and MongoDB cleanly.
const gracefulShutdown = async (signal) => {
  if (isShuttingDown) {
    return;
  }

  isShuttingDown = true;
  console.log(`${signal} received. Starting graceful shutdown...`);

  // Stop accepting new traffic immediately while in-flight requests complete.
  if (httpServer) {
    httpServer.keepAliveTimeout = 1;
    httpServer.headersTimeout = 1000;
  }

  try {
    if (httpServer) {
      await new Promise((resolve, reject) => {
        httpServer.close((error) => {
          if (error) {
            reject(error);
            return;
          }
          resolve();
        });
      });
      console.log("HTTP server closed.");
    }

    if (mongoose.connection.readyState !== 0) {
      await mongoose.connection.close();
      console.log("MongoDB connection closed.");
    }

    process.exit(0);
  } catch (error) {
    console.error("Error during graceful shutdown:", error);
    process.exit(1);
  }
};

process.on("SIGINT", () => gracefulShutdown("SIGINT"));
process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));

// Express route to home
app.get("/", async (req, res) => {
  res.send("Welcome to the Mongoose API");
});

// Readiness endpoint for service checks (API health + Mongo connection state).
app.get("/health", (req, res) => {
  if (isShuttingDown) {
    return res.status(503).json({
      status: "draining",
      service: "database-api",
      database: {
        name: DB_NAME,
        state: "disconnecting",
      },
    });
  }

  const mongoStateMap = {
    0: "disconnected",
    1: "connected",
    2: "connecting",
    3: "disconnecting",
  };

  const mongoState = mongoose.connection.readyState;
  const isReady = mongoState === 1;

  res.status(isReady ? 200 : 503).json({
    status: isReady ? "ok" : "degraded",
    service: "database-api",
    database: {
      name: DB_NAME,
      state: mongoStateMap[mongoState] || "unknown",
    },
  });
});

// Express route to fetch all reviews
app.get("/fetchReviews", async (req, res) => {
  try {
    const documents = await Reviews.find();
    res.json(documents);
  } catch (error) {
    sendError(res, 500, "FETCH_REVIEWS_FAILED", "Failed to fetch reviews.");
  }
});

// Express route to fetch reviews by a particular dealer
app.get("/fetchReviews/dealer/:id", async (req, res) => {
  const dealerId = Number(req.params.id);
  if (!Number.isInteger(dealerId) || dealerId <= 0) {
    return sendError(
      res,
      400,
      "INVALID_DEALER_ID",
      "Dealer id must be a positive integer.",
    );
  }

  try {
    const documents = await Reviews.find({ dealership: dealerId });
    res.json(documents);
  } catch (error) {
    sendError(
      res,
      500,
      "FETCH_DEALER_REVIEWS_FAILED",
      "Failed to fetch dealer reviews.",
    );
  }
});

// Express route to fetch all dealerships
app.get("/fetchDealers", async (req, res) => {
  try {
    const documents = await Dealerships.find();
    res.json(documents);
  } catch (error) {
    sendError(res, 500, "FETCH_DEALERS_FAILED", "Failed to fetch dealers.");
  }
});

// Express route to fetch Dealers by a particular state
app.get("/fetchDealers/:state", async (req, res) => {
  try {
    const documents = await Dealerships.find({ state: req.params.state });
    res.json(documents);
  } catch (error) {
    sendError(
      res,
      500,
      "FETCH_DEALERS_BY_STATE_FAILED",
      "Failed to fetch dealers by state.",
    );
  }
});

// Express route to fetch dealer by a particular id
app.get("/fetchDealer/:id", async (req, res) => {
  const dealerId = Number(req.params.id);
  if (!Number.isInteger(dealerId) || dealerId <= 0) {
    return sendError(
      res,
      400,
      "INVALID_DEALER_ID",
      "Dealer id must be a positive integer.",
    );
  }

  try {
    const documents = await Dealerships.find({ id: dealerId });
    if (!documents || documents.length === 0) {
      return sendError(
        res,
        404,
        "DEALER_NOT_FOUND",
        "Dealer not found.",
      );
    }

    return res.json(documents);
  } catch (error) {
    return sendError(
      res,
      500,
      "FETCH_DEALER_FAILED",
      "Failed to fetch dealer.",
    );
  }
});

// Express route to update a dealership by id
app.put("/updateDealer/:id", async (req, res) => {
  const dealerId = Number(req.params.id);
  if (!Number.isInteger(dealerId) || dealerId <= 0) {
    return sendError(
      res,
      400,
      "INVALID_DEALER_ID",
      "Dealer id must be a valid ID.",
    );
  }

  const allowedFields = [
    "city", "state", "address", "zip", "lat", "long", "short_name", "full_name",
  ];
  const updates = {};
  for (const field of allowedFields) {
    if (req.body[field] !== undefined) {
      updates[field] = req.body[field];
    }
  }

  if (Object.keys(updates).length === 0) {
    return sendError(
      res,
      400,
      "NO_UPDATE_FIELDS",
      "At least one updatable field must be provided.",
    );
  }

  try {
    const updated = await Dealerships.findOneAndUpdate(
      { id: dealerId },
      { $set: updates },
      { new: true, runValidators: true },
    );
    if (!updated) {
      return sendError(res, 404, "DEALER_NOT_FOUND", "Dealer not found.");
    }
    return res.json(updated);
  } catch (error) {
    return sendError(
      res,
      500,
      "UPDATE_DEALER_FAILED",
      "Failed to update dealer.",
    );
  }
});

//Express route to insert review
app.post("/insert_review", async (req, res) => {
  const validation = validateReviewPayload(req.body);
  if (!validation.valid) {
    return sendError(
      res,
      400,
      "INVALID_REVIEW_PAYLOAD",
      validation.message,
    );
  }

  const data = validation.normalized;
  const dealershipExists = await Dealerships.exists({ id: data.dealership });
  if (!dealershipExists) {
    return sendError(
      res,
      404,
      "DEALERSHIP_NOT_FOUND",
      "Cannot insert review for a dealership that does not exist.",
    );
  }

  const new_id = await getNextReviewId();

  const review = new Reviews({
    id: new_id,
    name: data.name,
    dealership: data.dealership,
    review: data.review,
    purchase: data.purchase,
    purchase_date: data.purchase_date,
    car_make: data.car_make,
    car_model: data.car_model,
    car_year: data.car_year,
  });

  try {
    const savedReview = await review.save();
    return res.status(201).json(savedReview);
  } catch (error) {
    if (error && error.code === 11000) {
      return sendError(
        res,
        409,
        "DUPLICATE_REVIEW_ID",
        "Duplicate review id detected. Please retry request.",
      );
    }
    console.log(error);
    return sendError(
      res,
      500,
      "INSERT_REVIEW_FAILED",
      "Failed to insert review.",
    );
  }
});

// Express route to fetch a single review by id
app.get("/fetchReview/:id", async (req, res) => {
  const reviewId = Number(req.params.id);
  if (!Number.isInteger(reviewId) || reviewId <= 0) {
    return sendError(res, 400, "INVALID_REVIEW_ID", "Review id must be a positive integer.");
  }

  try {
    const document = await Reviews.findOne({ id: reviewId });
    if (!document) {
      return sendError(res, 404, "REVIEW_NOT_FOUND", "Review not found.");
    }
    return res.json(document);
  } catch (error) {
    return sendError(res, 500, "FETCH_REVIEW_FAILED", "Failed to fetch review.");
  }
});

// Express route to update a review by id
app.put("/updateReview/:id", async (req, res) => {
  const reviewId = Number(req.params.id);
  if (!Number.isInteger(reviewId) || reviewId <= 0) {
    return sendError(res, 400, "INVALID_REVIEW_ID", "Review id must be a positive integer.");
  }

  const allowedFields = ["review", "purchase", "purchase_date", "car_make", "car_model", "car_year"];
  const updates = {};
  for (const field of allowedFields) {
    if (req.body[field] !== undefined) {
      updates[field] = req.body[field];
    }
  }

  if (Object.keys(updates).length === 0) {
    return sendError(res, 400, "NO_UPDATE_FIELDS", "At least one updatable field must be provided.");
  }

  try {
    const updated = await Reviews.findOneAndUpdate(
      { id: reviewId },
      { $set: updates },
      { new: true, runValidators: true },
    );
    if (!updated) {
      return sendError(res, 404, "REVIEW_NOT_FOUND", "Review not found.");
    }
    return res.json(updated);
  } catch (error) {
    return sendError(res, 500, "UPDATE_REVIEW_FAILED", "Failed to update review.");
  }
});

// Express route to delete a review by id
app.delete("/deleteReview/:id", async (req, res) => {
  const reviewId = Number(req.params.id);
  if (!Number.isInteger(reviewId) || reviewId <= 0) {
    return sendError(res, 400, "INVALID_REVIEW_ID", "Review id must be a positive integer.");
  }

  try {
    const deleted = await Reviews.findOneAndDelete({ id: reviewId });
    if (!deleted) {
      return sendError(res, 404, "REVIEW_NOT_FOUND", "Review not found.");
    }
    return res.json({ message: "Review deleted." });
  } catch (error) {
    return sendError(res, 500, "DELETE_REVIEW_FAILED", "Failed to delete review.");
  }
});

// Explicit async startup wrapper for all bootstrap operations.
const startServer = async () => {
  try {
    // Structured startup logs to make bootstrap progress and failures clear.
    console.log("[bootstrap] Starting database API service...");
    console.log(
      `[bootstrap] Configuration loaded: PORT=${PORT}, DB_NAME=${DB_NAME}, SEED_ON_START=${SEED_ON_START}`,
    );
    // Deterministic startup order: connect DB -> optional seed -> start HTTP listener.
    await mongoose.connect(MONGODB_URI, MONGODB_OPTIONS);
    console.log(`Connected to MongoDB database: ${DB_NAME}`);
    await ensureDatabaseIndexes();

    if (SEED_ON_START) {
      console.log("[bootstrap] Seeding enabled. Running seed process...");
      await seedDatabase();
      console.log("Database seed completed.");
    } else {
      console.log("[bootstrap] Seeding disabled. Skipping seed process.");
    }

    await syncReviewCounter();

    httpServer = app.listen(PORT, () => {
      console.log(
        `[bootstrap] API service is ready at http://localhost:${PORT}`,
      );
    });
  } catch (error) {
    console.error("[bootstrap] Failed to bootstrap API service.");
    
    console.error(error);
    process.exit(1);
  }
};

startServer();
