/**
 * smoke-test.js — Integration Smoke Test
 *
 * Runs end-to-end checks against every route in app.js.
 * Requires the service to already be running (npm start or Docker).
 *
 * Usage:
 *   node smoke-test.js
 *   node smoke-test.js --host localhost --port 3030
 */

/* jshint esversion: 8 */
"use strict";

const http = require("http");

// ---------------------------------------------------------------------------
// Config — override via CLI flags: --host <h> --port <p>
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : fallback;
};

const HOST = flag("host", "localhost");
const PORT = Number(flag("port", "3030"));
const BASE = `http://${HOST}:${PORT}`;

// ---------------------------------------------------------------------------
// ANSI colours for readable output
// ---------------------------------------------------------------------------
const GREEN  = "\x1b[32m";
const RED    = "\x1b[31m";
const YELLOW = "\x1b[33m";
const CYAN   = "\x1b[36m";
const RESET  = "\x1b[0m";
const BOLD   = "\x1b[1m";

// ---------------------------------------------------------------------------
// HTTP helper — returns { status, body } where body is parsed JSON if possible
// ---------------------------------------------------------------------------
const request = (method, path, payload) =>
  new Promise((resolve, reject) => {
    const bodyStr = payload ? JSON.stringify(payload) : null;

    const options = {
      hostname: HOST,
      port:     PORT,
      path,
      method,
      headers: {
        "Accept": "application/json",
        ...(bodyStr
          ? {
              "Content-Type":   "application/json",
              "Content-Length": Buffer.byteLength(bodyStr),
            }
          : {}),
      },
    };

    const req = http.request(options, (res) => {
      let raw = "";
      res.on("data", (chunk) => (raw += chunk));
      res.on("end", () => {
        let body;
        try {
          body = JSON.parse(raw);
        } catch {
          body = raw;
        }
        resolve({ status: res.statusCode, body });
      });
    });

    req.on("error", reject);
    if (bodyStr) req.write(bodyStr);
    req.end();
  });

// ---------------------------------------------------------------------------
// Assertion helpers
// ---------------------------------------------------------------------------
let passed = 0;
let failed = 0;
const failures = [];

const pass = (name) => {
  passed++;
  console.log(`  ${GREEN}✔${RESET} ${name}`);
};

const fail = (name, detail) => {
  failed++;
  const msg = detail ? `${name} — ${detail}` : name;
  failures.push(msg);
  console.log(`  ${RED}✘${RESET} ${name}`);
  if (detail) console.log(`    ${YELLOW}↳ ${detail}${RESET}`);
};

const check = (name, condition, detail) =>
  condition ? pass(name) : fail(name, detail);

// ---------------------------------------------------------------------------
// Test sections
// ---------------------------------------------------------------------------
const section = (title) =>
  console.log(`\n${BOLD}${CYAN}▸ ${title}${RESET}`);

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
const runTests = async () => {
  console.log(`\n${BOLD}Smoke test target:${RESET} ${BASE}\n`);

  // ── 5.2  Health ──────────────────────────────────────────────────────────
  section("5.2  Health endpoint");
  {
    const r = await request("GET", "/health");
    check("GET /health → 200", r.status === 200, `got ${r.status}`);
    check(
      'body.status === "ok"',
      r.body && r.body.status === "ok",
      `got ${JSON.stringify(r.body && r.body.status)}`,
    );
    check(
      'body.database.state === "connected"',
      r.body && r.body.database && r.body.database.state === "connected",
      `got ${JSON.stringify(r.body && r.body.database && r.body.database.state)}`,
    );
  }

  // ── 5.3  Dealer routes ───────────────────────────────────────────────────
  section("5.3  Dealer routes");
  {
    // All dealers
    const all = await request("GET", "/fetchDealers");
    check("GET /fetchDealers → 200", all.status === 200, `got ${all.status}`);
    check(
      "Returns a non-empty array",
      Array.isArray(all.body) && all.body.length > 0,
      `got ${Array.isArray(all.body) ? all.body.length + " items" : typeof all.body}`,
    );

    // Filter by state
    const byState = await request("GET", "/fetchDealers/Texas");
    check(
      "GET /fetchDealers/Texas → 200",
      byState.status === 200,
      `got ${byState.status}`,
    );
    check(
      "All results have state=Texas",
      Array.isArray(byState.body) &&
        byState.body.length > 0 &&
        byState.body.every((d) => d.state === "Texas"),
      `got ${JSON.stringify(byState.body && byState.body[0] && byState.body[0].state)}`,
    );

    // Single dealer — valid id
    const one = await request("GET", "/fetchDealer/1");
    check("GET /fetchDealer/1 → 200", one.status === 200, `got ${one.status}`);
    check(
      "Returns array with id=1",
      Array.isArray(one.body) &&
        one.body.length > 0 &&
        one.body[0].id === 1,
      `got id=${one.body && one.body[0] && one.body[0].id}`,
    );

    // Single dealer — non-existent id
    const missing = await request("GET", "/fetchDealer/99999");
    check(
      "GET /fetchDealer/99999 → 404",
      missing.status === 404,
      `got ${missing.status}`,
    );
    check(
      "Error code DEALER_NOT_FOUND",
      missing.body &&
        missing.body.error &&
        missing.body.error.code === "DEALER_NOT_FOUND",
      `got code=${JSON.stringify(missing.body && missing.body.error && missing.body.error.code)}`,
    );

    // Single dealer — invalid id type
    const bad = await request("GET", "/fetchDealer/abc");
    check(
      "GET /fetchDealer/abc → 400",
      bad.status === 400,
      `got ${bad.status}`,
    );
    check(
      "Error code INVALID_DEALER_ID",
      bad.body &&
        bad.body.error &&
        bad.body.error.code === "INVALID_DEALER_ID",
      `got code=${JSON.stringify(bad.body && bad.body.error && bad.body.error.code)}`,
    );
  }

  // ── 5.4  Review routes ───────────────────────────────────────────────────
  section("5.4  Review routes");
  {
    // Fetch reviews for a known dealer
    const rev = await request("GET", "/fetchReviews/dealer/15");
    check(
      "GET /fetchReviews/dealer/15 → 200",
      rev.status === 200,
      `got ${rev.status}`,
    );
    check(
      "Returns an array",
      Array.isArray(rev.body),
      `got ${typeof rev.body}`,
    );
    check(
      "All results have dealership=15",
      Array.isArray(rev.body) &&
        rev.body.length > 0 &&
        rev.body.every((r) => r.dealership === 15),
      `first item dealership=${rev.body && rev.body[0] && rev.body[0].dealership}`,
    );

    // Invalid dealer id
    const badId = await request("GET", "/fetchReviews/dealer/abc");
    check(
      "GET /fetchReviews/dealer/abc → 400",
      badId.status === 400,
      `got ${badId.status}`,
    );

    // Insert review — valid payload
    const validPayload = {
      name:          "Smoke Tester",
      dealership:    1,
      review:        "Integration smoke test review — can be deleted.",
      purchase:      true,
      purchase_date: "04/14/2026",
      car_make:      "Toyota",
      car_model:     "Camry",
      car_year:      2022,
    };
    const insert = await request("POST", "/insert_review", validPayload);
    check(
      "POST /insert_review (valid) → 201",
      insert.status === 201,
      `got ${insert.status} — ${JSON.stringify(insert.body)}`,
    );
    check(
      "Returned review has auto-generated numeric id",
      insert.body && Number.isInteger(insert.body.id) && insert.body.id > 0,
      `got id=${JSON.stringify(insert.body && insert.body.id)}`,
    );
    check(
      "Returned review name matches payload",
      insert.body && insert.body.name === validPayload.name,
      `got name=${JSON.stringify(insert.body && insert.body.name)}`,
    );

    // Insert review — missing required field
    const missingField = { ...validPayload };
    delete missingField.name;
    const badInsert = await request("POST", "/insert_review", missingField);
    check(
      "POST /insert_review (missing name) → 400",
      badInsert.status === 400,
      `got ${badInsert.status}`,
    );
    check(
      "Error code INVALID_REVIEW_PAYLOAD",
      badInsert.body &&
        badInsert.body.error &&
        badInsert.body.error.code === "INVALID_REVIEW_PAYLOAD",
      `got code=${JSON.stringify(
        badInsert.body && badInsert.body.error && badInsert.body.error.code,
      )}`,
    );
    check(
      "Error message mentions 'name'",
      badInsert.body &&
        badInsert.body.error &&
        badInsert.body.error.message.includes("name"),
      `got message=${JSON.stringify(
        badInsert.body && badInsert.body.error && badInsert.body.error.message,
      )}`,
    );

    // Insert review — dealership does not exist
    const unknownDealer = { ...validPayload, dealership: 99999 };
    const notFound = await request("POST", "/insert_review", unknownDealer);
    check(
      "POST /insert_review (unknown dealership) → 404",
      notFound.status === 404,
      `got ${notFound.status}`,
    );
    check(
      "Error code DEALERSHIP_NOT_FOUND",
      notFound.body &&
        notFound.body.error &&
        notFound.body.error.code === "DEALERSHIP_NOT_FOUND",
      `got code=${JSON.stringify(
        notFound.body && notFound.body.error && notFound.body.error.code,
      )}`,
    );

    // Insert review — empty body
    const empty = await request("POST", "/insert_review", {});
    check(
      "POST /insert_review (empty body) → 400",
      empty.status === 400,
      `got ${empty.status}`,
    );
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  const total = passed + failed;
  console.log(`\n${"─".repeat(50)}`);
  console.log(
    `${BOLD}Results: ${GREEN}${passed} passed${RESET}${BOLD}, ${
      failed > 0 ? RED : GREEN
    }${failed} failed${RESET}${BOLD} / ${total} total${RESET}`,
  );

  if (failures.length > 0) {
    console.log(`\n${RED}${BOLD}Failed checks:${RESET}`);
    failures.forEach((f) => console.log(`  ${RED}•${RESET} ${f}`));
  }

  console.log("");
  process.exit(failed > 0 ? 1 : 0);
};

// ---------------------------------------------------------------------------
// Entry point — catch connection refused early with a helpful message
// ---------------------------------------------------------------------------
runTests().catch((err) => {
  if (err.code === "ECONNREFUSED") {
    console.error(
      `\n${RED}${BOLD}Connection refused.${RESET} Is the service running at ${BASE}?\n` +
        `  Start it with:  npm start\n` +
        `  Or via Docker:  npm run compose:up\n`,
    );
  } else {
    console.error(`\n${RED}Unexpected error:${RESET}`, err);
  }
  process.exit(1);
});
