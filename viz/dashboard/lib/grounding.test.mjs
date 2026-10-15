import assert from "node:assert/strict";
import { test } from "node:test";
import { allowedValues, extractNumbers, groundObject, groundText } from "./grounding.mjs";

const src = { p: 0.565, gbp: { low: -11954.2, high: 4417.4 }, reasons: ["AEVA s.3(1) not assessed: range 0-100%"], tier: 2 };
const allowed = allowedValues(src);

test("extracts numbers with precision, skipping identifiers", () => {
  const n = extractNumbers("R157 PM1 careful_a moved 56.5% and £11,954 at tier 2");
  assert.deepEqual(n.map((x) => x.value), [56.5, 11954, 2]);
  assert.equal(n[0].decimals, 1);
});

test("keeps grounded sentences, allowing rounding and percentages", () => {
  const g = groundText("P(avoid) is 57%. Worst case −£11,954. Tier 2 evidence.", allowed);
  assert.equal(g.dropped.length, 0);
});

test("drops sentences with invented numbers", () => {
  const g = groundText("P(avoid) is 57%. Recovery is likely £25,000. See s.3(1).", allowed);
  assert.deepEqual(g.dropped, ["Recovery is likely £25,000."]);
  assert.equal(g.text, "P(avoid) is 57%. See s.3(1).");
});

test("rounding tolerance follows written precision", () => {
  assert.equal(groundText("It is 56.6%.", allowed).dropped.length, 1);
  assert.equal(groundText("It is 56.5%.", allowed).dropped.length, 0);
});

test("groundObject walks nested output", () => {
  const dropped = [];
  const o = groundObject({ a: ["Fine at 57%.", "Bad 12345 figure."], b: { c: "No numbers here." } }, allowed, dropped);
  assert.deepEqual(o, { a: ["Fine at 57%.", ""], b: { c: "No numbers here." } });
  assert.equal(dropped.length, 1);
});
