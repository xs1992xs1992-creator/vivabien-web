import assert from "node:assert/strict";
import fs from "node:fs";
import { buildFanPriceMap, isInactiveFanSku, prepaidOfferValue } from "../src/checkout-offer.js";

const config = JSON.parse(fs.readFileSync(new URL("../../data/ventilador_techo.json", import.meta.url), "utf8"));
const prices = buildFanPriceMap(config);
const offer = config.checkout_offer;

assert.equal(prices.get("VB-FAN-E27-40"), 1250);
assert.equal(prices.get("VB-FAN-E27-40-P2"), 2150);
assert.equal(prices.get("VB-FAN-E27-40-P3"), 3000);
assert.equal(prices.has("VB-FAN-E27-30"), false);
assert.equal(isInactiveFanSku("VB-FAN-E27-30", config), true);
assert.equal(isInactiveFanSku("VB-FAN-E27-30-P2", config), true);
assert.equal(isInactiveFanSku("VB-FAN-E27-40", config), false);

const oneFan = [{ sku: "VB-FAN-E27-40", lineTotal: 1250 }];
assert.equal(prepaidOfferValue(oneFan, "cod", 1250, 0, offer), 0);
assert.equal(prepaidOfferValue(oneFan, "prepaid", 1250, 0, offer), 125);
assert.equal(prepaidOfferValue(oneFan, "prepaid", 1250, 100, offer), 125);
assert.equal(prepaidOfferValue([{ sku: "VB-FAN-E27-40-P2", lineTotal: 2150 }], "prepaid", 2150, 0, offer), 215);
assert.equal(prepaidOfferValue([{ sku: "VB-FAN-E27-40-P3", lineTotal: 3000 }], "prepaid", 3000, 0, offer), 300);
assert.equal(prepaidOfferValue([{ sku: "OTHER-SKU" }], "prepaid", 1250, 0, offer), 0);
assert.equal(prepaidOfferValue(oneFan, "prepaid", 100, 95, offer), 5);
assert.equal(prepaidOfferValue([
  { sku: "VB-FAN-E27-40", lineTotal: 1250 },
  { sku: "OTHER-SKU", lineTotal: 5000 },
], "prepaid", 6250, 0, offer), 125);

console.log("checkout offer tests passed");
