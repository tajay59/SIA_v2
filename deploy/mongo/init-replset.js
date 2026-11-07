// Run once on the primary-to-be through the localhost exception (before any user exists):
//   mongosh --tls --tlsCAFile ca.pem --host <host> init-replset.js
// Member hosts come from MONGO_MEMBERS (comma separated, first = sia-host with priority 10).
// INFRASTRUCTURE §5.1. Idempotent: does nothing if the set is already initiated.
const members = (process.env.MONGO_MEMBERS ||
  "sia-host.cimh.local:27017,sia-pi-a.cimh.local:27017,sia-pi-b.cimh.local:27017").split(",");

let initiated = false;
try { initiated = rs.status().ok === 1; } catch (e) { initiated = false; }

if (!initiated) {
  rs.initiate({
    _id: "rs0",
    members: members.map((host, i) => ({ _id: i, host, priority: i === 0 ? 10 : 1 })),
    settings: { electionTimeoutMillis: 10000 },
  });
  print("replica set initiated: " + members.join(", "));
} else {
  print("replica set already initiated");
}

// Wait until this node is primary (priority 10 wins the first election).
for (let i = 0; i < 60 && !db.hello().isWritablePrimary; i++) sleep(1000);
if (!db.hello().isWritablePrimary) throw new Error("this node did not become primary");
