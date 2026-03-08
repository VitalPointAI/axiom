const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

console.log("\n=== ACB POOL VERIFICATION ===");

// Check NEAR price at different times in 2025
console.log("\n=== NEAR PRICES IN 2025 (USD -> CAD @ 1.38) ===");
const prices = db.prepare(`
  SELECT date, price 
  FROM price_cache 
  WHERE coin_id = ? AND currency = ?
  AND date LIKE ?
  ORDER BY date
`).all("NEAR", "USD", "2025-%");

const sampleMonths = ["2025-01", "2025-04", "2025-07", "2025-10", "2025-12"];
sampleMonths.forEach(month => {
  const monthPrices = prices.filter(p => p.date.startsWith(month));
  if (monthPrices.length > 0) {
    const avg = monthPrices.reduce((s, p) => s + p.price, 0) / monthPrices.length;
    console.log(`  ${month}: ~$${avg.toFixed(2)} USD (~$${(avg * 1.38).toFixed(2)} CAD)`);
  }
});

// December 2025 specific
console.log("\n=== DECEMBER 2025 PRICE CHECK ===");
const dec2025 = prices.filter(p => p.date.startsWith("2025-12"));
if (dec2025.length > 0) {
  const avgDec = dec2025.reduce((s, p) => s + p.price, 0) / dec2025.length;
  console.log("  Avg Dec 2025 price: $" + avgDec.toFixed(2) + " USD = $" + (avgDec * 1.38).toFixed(2) + " CAD");
  
  // Check the biggest loss transaction
  // Sold 17,325 NEAR for $36,537.44 = $2.11/NEAR
  const pricePerNear = 36537.44 / 17325;
  console.log("  Biggest loss sold at: $" + pricePerNear.toFixed(2) + " CAD/NEAR");
  console.log("  Expected ~$" + (avgDec * 1.38).toFixed(2) + " CAD/NEAR");
  console.log("  Variance: " + (Math.abs((avgDec * 1.38) - pricePerNear) < 0.50 ? "REASONABLE ✓" : "CHECK ⚠"));
}

// Historical ACB check - when was NEAR bought at higher prices?
console.log("\n=== WHEN WAS NEAR EXPENSIVE? (for ACB ~$3.86) ===");
const expensivePeriods = db.prepare(`
  SELECT date, price
  FROM price_cache 
  WHERE coin_id = ? AND currency = ?
  AND price > 2.5
  ORDER BY date DESC
  LIMIT 10
`).all("NEAR", "USD");

expensivePeriods.forEach(p => {
  console.log(`  ${p.date}: $${p.price.toFixed(2)} USD = $${(p.price * 1.38).toFixed(2)} CAD`);
});

// Verify disposal calculation
console.log("\n=== VERIFY BIGGEST LOSS MATH ===");
console.log("  Sold: 17,325 NEAR");
console.log("  Proceeds: $36,537.44 CAD");
console.log("  ACB: $66,935.45 CAD");
console.log("  ACB per NEAR: $" + (66935.45 / 17325).toFixed(2));
console.log("  Proceeds per NEAR: $" + (36537.44 / 17325).toFixed(2));
console.log("  Loss per NEAR: $" + ((66935.45 - 36537.44) / 17325).toFixed(2));
console.log("  Total Loss: $" + (66935.45 - 36537.44).toFixed(2) + " (" + ((66935.45 - 36537.44) / 66935.45 * 100).toFixed(1) + "% loss)");
