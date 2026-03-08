const Database = require("better-sqlite3");
const db = new Database("../neartax.db");

// Get any valid session
const session = db.prepare("SELECT s.id, u.near_account_id FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.expires_at > datetime('now') LIMIT 1").get();
console.log("Session:", session ? session.id.substring(0, 20) + "..." : "none");

if (session) {
  // Test the API call
  fetch("http://localhost:3003/api/portfolio/history", {
    headers: { "Cookie": "neartax_session=" + session.id }
  })
  .then(r => r.json())
  .then(d => {
    console.log("\nAPI Response:");
    console.log("  currentNear:", d.currentNear);
    console.log("  currentValue:", d.currentValue);
    console.log("  history length:", d.history?.length);
    if (d.history && d.history.length > 0) {
      console.log("  first point:", d.history[0]);
      console.log("  last point:", d.history[d.history.length - 1]);
    }
    if (d.error) console.log("  error:", d.error);
  })
  .catch(e => console.log("Error:", e.message));
}
