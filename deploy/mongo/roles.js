// Users and collection-scoped roles (BSD §3.1, INFRASTRUCTURE §5.1). Idempotent: re-running updates
// roles and passwords. Run on the primary:
//   mongosh "<root url>" roles.js        (passwords from the files in SECRETS_DIR)
// The first run happens through the localhost exception, which only allows creating the root user;
// so this script creates root first, then authenticates as root for everything else.
const fs = require("fs");
const dir = process.env.SECRETS_DIR || "/run/secrets";
// provision.sh prepends `const SECRETS = {...}` on stdin; otherwise the files in SECRETS_DIR are read.
const secret = (name) =>
  typeof SECRETS !== "undefined" ? SECRETS[name] : fs.readFileSync(`${dir}/${name}`, "utf8").trim();

const admin = db.getSiblingDB("admin");
// The localhost exception allows createUser and nothing else (not even usersInfo), so just try it:
// it fails harmlessly once root exists.
try {
  admin.createUser({ user: "root", pwd: secret("mongo_root"), roles: ["root"] });
  print("created root");
} catch (e) {
  print("root exists");
}
admin.auth("root", secret("mongo_root"));

// Collection ownership (CLAUDE.md / BSD §3.1). A service only touches its own collections.
const OWN = {
  identity: ["accounts", "temp", "organisations", "auditlog"],
  catalog: ["product", "misc"],
  inventory: ["storage", "history", "stock"],
  order: ["orders"],
};
const READ_ONLY_VIEWS = { catalog: ["xuser"] };
const RW = ["find", "insert", "update", "remove", "createIndex", "dropIndex", "listIndexes", "collStats",
            "changeStream", "bypassDocumentValidation"];

function upsertRole(name, privileges, roles) {
  if (admin.getRole(name)) admin.updateRole(name, { privileges, roles });
  else admin.createRole({ role: name, privileges, roles });
}
function upsertUser(user, pwd, roles) {
  if (admin.getUser(user)) admin.updateUser(user, { pwd, roles });
  else admin.createUser({ user, pwd, roles });
}

for (const [svc, colls] of Object.entries(OWN)) {
  const privileges = colls.map((c) => ({ resource: { db: "inventory", collection: c }, actions: RW }));
  for (const v of READ_ONLY_VIEWS[svc] || []) {
    privileges.push({ resource: { db: "inventory", collection: v }, actions: ["find"] });
  }
  // createCollection / collMod for validators and listCollections for startup checks.
  privileges.push({ resource: { db: "inventory", collection: "" }, actions: ["listCollections", "createCollection", "collMod"] });
  upsertRole(`svc_${svc}`, privileges, []);
  upsertUser(`svc_${svc}`, secret(`mongo_svc_${svc}`), [{ role: `svc_${svc}`, db: "admin" }]);
  print(`user svc_${svc}: ${colls.join(", ")}`);
}

upsertUser("svc_backup", secret("mongo_svc_backup"), [{ role: "backup", db: "admin" }, { role: "clusterMonitor", db: "admin" }]);
// mongodb-exporter (INFRASTRUCTURE §8): server and replica set status only, no data.
upsertUser("svc_monitor", secret("mongo_svc_monitor"), [{ role: "clusterMonitor", db: "admin" }]);
upsertUser("admin_ops", secret("mongo_admin_ops"), [{ role: "readAnyDatabase", db: "admin" }, { role: "clusterMonitor", db: "admin" }]);
print("users ready");
