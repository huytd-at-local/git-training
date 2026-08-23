#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const sjcl = require(path.join(__dirname, "..", "vendor", "sjcl.js"));

const passcode = process.env.BREVIARY_EN_PASSCODE;
if (!passcode) {
  throw new Error("BREVIARY_EN_PASSCODE is required");
}

const request = JSON.parse(fs.readFileSync(0, "utf8"));
if (!request.pages || !request.pages.length || !request.pages[0].id) {
  throw new Error("The unlock page must be encrypted first");
}

const params = { iter: 2000, ks: 256, ts: 128, mode: "ccm", cipher: "aes" };
const details = {};
const result = {};

const first = sjcl.json.ja(passcode, request.pages[0].html, params, details);
result[request.pages[0].id] = sjcl.json.encode(first);

for (let index = 1; index < request.pages.length; index += 1) {
  const page = request.pages[index];
  result[page.id] = sjcl.json.encrypt(details.key, page.html, params);
}

process.stdout.write(JSON.stringify(result));
