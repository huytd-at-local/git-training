#!/usr/bin/env node
"use strict";

// Build-time companion to encrypt_breviary.js. It is used only to repaginate
// an already encrypted learner edition in the Actions workspace; plaintext is
// returned over the local process pipe and is never written to the repository.
const fs = require("fs");
const path = require("path");
const sjcl = require(path.join(__dirname, "..", "vendor", "sjcl.js"));

const passcode = process.env.BREVIARY_EN_PASSCODE;
if (!passcode) {
  throw new Error("BREVIARY_EN_PASSCODE is required");
}

const request = JSON.parse(fs.readFileSync(0, "utf8"));
if (!request.pages || !request.pages.length || !request.pages[0].id) {
  throw new Error("At least one encrypted page is required");
}

const result = {};
const first = request.pages[0];
if (typeof first.ciphertext !== "string") {
  throw new Error("Each encrypted page requires an id and ciphertext");
}
const details = {};
result[first.id] = sjcl.json.decrypt(passcode, first.ciphertext, {}, details);

for (const page of request.pages.slice(1)) {
  if (!page.id || typeof page.ciphertext !== "string") {
    throw new Error("Each encrypted page requires an id and ciphertext");
  }
  result[page.id] = sjcl.json.decrypt(details.key, page.ciphertext);
}

process.stdout.write(JSON.stringify(result));
