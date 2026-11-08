"""Generates the draw.io diagrams for the CIMH Stores Platform manual.

Usage:  python _generate.py            (writes *.drawio next to this script)
Export: see ../index.html, section "Editing diagrams".

Each diagram can also be edited by hand in draw.io afterwards; if you do, stop
regenerating that file (or move your change into this script) so edits aren't lost.
"""
from pathlib import Path
from xml.sax.saxutils import quoteattr

OUT = Path(__file__).parent

# ---------------------------------------------------------------- palette
C = {
    "client":   ("#dae8fc", "#6c8ebf"),
    "edge":     ("#e1d5e7", "#9673a6"),
    "service":  ("#d5e8d4", "#82b366"),
    "worker":   ("#fff2cc", "#d6b656"),
    "data":     ("#f8cecc", "#b85450"),
    "platform": ("#ffe6cc", "#d79b00"),
    "external": ("#f5f5f5", "#666666"),
    "actor":    ("#ffffff", "#333333"),
    "state":    ("#dae8fc", "#6c8ebf"),
    "final":    ("#d5e8d4", "#82b366"),
    "bad":      ("#f8cecc", "#b85450"),
    "note":     ("#fff2cc", "#d6b656"),
}
FONT = "fontFamily=Helvetica;fontSize=12;"


def box(kind, extra=""):
    f, s = C[kind]
    return f"rounded=1;whiteSpace=wrap;html=1;fillColor={f};strokeColor={s};{FONT}{extra}"


def cyl(kind="data"):
    f, s = C[kind]
    return f"shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=10;fillColor={f};strokeColor={s};{FONT}"


ACTOR = f"shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;{FONT}"
GROUP = "rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor=none;strokeColor=#999999;verticalAlign=top;align=left;spacingLeft=8;fontStyle=1;" + FONT
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;" + FONT + "fontSize=11;labelBackgroundColor=#ffffff;"
EDGE_DASH = EDGE + "dashed=1;"
TITLE = "text;html=1;fontSize=18;fontStyle=1;align=left;verticalAlign=middle;"
NOTE = f"shape=note;whiteSpace=wrap;html=1;size=14;fillColor={C['note'][0]};strokeColor={C['note'][1]};align=left;spacingLeft=6;{FONT}fontSize=11;"


class Diagram:
    def __init__(self, name, title):
        self.name, self.title = name, title
        self.cells, self.n = [], 1
        self.text(title, 20, 10, 900, 30, TITLE)

    def _id(self):
        self.n += 1
        return f"c{self.n}"

    def node(self, label, x, y, w=140, h=50, style=None):
        i = self._id()
        self.cells.append(
            f'<mxCell id="{i}" value={quoteattr(label)} style={quoteattr(style or box("service"))} vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return i

    def text(self, label, x, y, w, h, style="text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;" + FONT):
        return self.node(label, x, y, w, h, style)

    def edge(self, a, b, label="", style=EDGE):
        i = self._id()
        self.cells.append(
            f'<mxCell id="{i}" value={quoteattr(label)} style={quoteattr(style)} edge="1" parent="1" source="{a}" target="{b}">'
            f'<mxGeometry relative="1" as="geometry"/></mxCell>')
        return i

    def line(self, x1, y1, x2, y2, label="", style=EDGE, label_dy=0):
        i = self._id()
        self.cells.append(
            f'<mxCell id="{i}" value={quoteattr(label)} style={quoteattr(style)} edge="1" parent="1">'
            f'<mxGeometry relative="1" y="{label_dy}" as="geometry"><mxPoint x="{x1}" y="{y1}" as="sourcePoint"/>'
            f'<mxPoint x="{x2}" y="{y2}" as="targetPoint"/></mxGeometry></mxCell>')
        return i

    def save(self):
        xml = ('<mxfile host="generator"><diagram name=' + quoteattr(self.title) + ' id="' + self.name + '">'
               '<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
               'arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0"><root>'
               '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cells) +
               '</root></mxGraphModel></diagram></mxfile>')
        (OUT / f"{self.name}.drawio").write_text(xml, encoding="utf-8")


def sequence(name, title, participants, steps, col=170, top=70, step=46):
    """participants: list of (key, label, kind). steps: (from, to, label) | ('note', key, text) | ('alt', text)."""
    d = Diagram(name, title)
    xs = {}
    for i, (k, label, kind) in enumerate(participants):
        x = 20 + i * col
        style = ACTOR if kind == "actor" else box(kind, "fontStyle=1;")
        if kind == "actor":
            d.node(label, x + 55, top, 30, 40, style)
        else:
            d.node(label, x, top, col - 30, 44, style)
        xs[k] = x + (col - 30) / 2
    y = top + 80
    for s in steps:
        if s[0] == "note":
            _, k, txt = s
            d.node(txt, xs[k] - 70, y - 14, col * 1.6, 34, NOTE)
            y += step
        elif s[0] == "alt":
            d.node(s[1], 20, y - 14, col * len(participants) - 30, 24,
                   "rounded=0;html=1;fillColor=#f5f5f5;strokeColor=#bbbbbb;fontStyle=2;align=left;spacingLeft=8;" + FONT + "fontSize=11;")
            y += step - 10
        else:
            a, b, label = s
            if a == b:
                d.node(label, xs[a] + 8, y - 12, col * 1.5, 24,
                       "rounded=0;html=1;fillColor=#ffffff;strokeColor=#82b366;align=left;spacingLeft=6;" + FONT + "fontSize=11;")
            else:
                d.line(xs[a], y, xs[b], y, label,
                       (EDGE_DASH if label.startswith("(") else EDGE) + "edgeStyle=none;labelBackgroundColor=none;",
                       label_dy=-10)
            y += step
    for k, x in xs.items():  # lifelines behind
        d.cells.insert(0, f'<mxCell id="ll{k}" style="endArrow=none;dashed=1;html=1;strokeColor=#aaaaaa;" edge="1" parent="1">'
                          f'<mxGeometry relative="1" as="geometry"><mxPoint x="{x}" y="{top + 50}" as="sourcePoint"/>'
                          f'<mxPoint x="{x}" y="{y}" as="targetPoint"/></mxGeometry></mxCell>')
    d.save()


DOWN = "exitX={ex};exitY=1;entryX={en};entryY=0;"


def states(name, title, layout, transitions, w=150, h=44, layout_w=None):
    layout_w = layout_w or {}
    """layout: {state: (x, y, kind)}; transitions: (from, to, label)."""
    d = Diagram(name, title)
    ids = {}
    for st, (x, y, kind) in layout.items():
        if st == "START":
            ids[st] = d.node("", x, y, 24, 24, "ellipse;html=1;fillColor=#333333;strokeColor=#333333;")
        elif st == "END":
            ids[st] = d.node("", x, y, 28, 28, "ellipse;html=1;shape=doubleEllipse;fillColor=#333333;strokeColor=#333333;")
        else:
            ids[st] = d.node(f"<b>{st}</b>", x, y, layout_w.get(st, w), h, box(kind, "arcSize=40;"))
    for t in transitions:
        a, b, label = t[:3]
        d.edge(ids[a], ids[b], label, EDGE + (t[3] if len(t) > 3 else ""))
    d.save()


# =================================================================== 01 context
d = Diagram("01-system-context", "System context: CIMH Stores Platform v2")
cu = d.node("Customer<br>(member-state org staff)", 40, 120, 30, 50, ACTOR)
st = d.node("CIMH Staff / Admin", 40, 280, 30, 50, ACTOR)
wh = d.node("Warehouse staff<br>(Android)", 40, 440, 30, 50, ACTOR)
grp = d.node("CIMH Stores Platform v2", 230, 80, 520, 460, GROUP)
shop = d.node("<b>SHOP</b><br>store.cimh.edu.bb", 270, 120, 170, 60, box("client"))
sia = d.node("<b>SIA web</b><br>sia.cimh.edu.bb", 270, 280, 170, 60, box("client"))
mob = d.node("<b>SIA Mobile</b><br>Android 11+", 270, 440, 170, 60, box("client"))
be = d.node("<b>Backend services</b><br>nginx · 6 microservices · Kafka<br>MongoDB replica set · Redis", 520, 250, 200, 120, box("service"))
mail = d.node("CIMH mail server", 860, 150, 170, 60, box("external"))
bak = d.node("Backup store<br>(other CIMH site)", 860, 290, 170, 60, cyl("external"))
car = d.node("FedEx / DHL<br>public tracking pages", 860, 430, 170, 60, box("external"))
d.edge(cu, shop, "browse, request, accept quotes")
d.edge(st, sia, "manage stock, requests, accounts")
d.edge(wh, mob, "scan, stow, pick")
for c in (shop, sia, mob):
    d.edge(c, be, "HTTPS /api")
d.edge(be, mail, "SMTP/TLS")
d.edge(be, bak, "restic nightly")
d.edge(shop, car, "tracking link only", EDGE_DASH)
d.save()

# =================================================================== 02 containers
d = Diagram("02-containers", "Container view")
d.node("Clients", 20, 50, 1100, 100, GROUP)
s1 = d.node("<b>SHOP SPA</b><br>Vue 3 · TS · Vuetify 4", 80, 85, 200, 50, box("client"))
s2 = d.node("<b>SIA SPA</b><br>Vue 3 · TS · Vuetify 4", 470, 85, 200, 50, box("client"))
s3 = d.node("<b>SIA Mobile</b><br>Kotlin · Compose", 860, 85, 200, 50, box("client"))
ngx = d.node("<b>nginx</b><br>TLS · routing · rate limits · static SPAs · X-Accel-Redirect", 320, 190, 500, 50, box("edge"))
for s in (s1, s2, s3):
    d.edge(s, ngx, "HTTPS")
d.node("Application services (FastAPI)", 20, 280, 1100, 200, GROUP)
svc = {}
for i, (k, lbl) in enumerate([("id", "identity-svc"), ("cat", "catalog-svc"), ("inv", "inventory-svc"),
                               ("ord", "order-svc"), ("doc", "document-svc")]):
    svc[k] = d.node(f"<b>{lbl}</b>", 50 + i * 215, 320, 170, 50, box("service"))
    d.edge(ngx, svc[k], "/api/" + lbl.split("-")[0])
svc["not"] = d.node("<b>notification-svc</b><br>(consumers only)", 50, 405, 200, 50, box("service"))
svc["mw"] = d.node("<b>media-worker</b> ×2<br>GPU · rembg", 300, 405, 200, 50, box("worker"))
svc["rel"] = d.node("<b>outbox relays</b><br>one per service", 550, 405, 200, 50, box("worker"))
d.node("Platform", 20, 520, 1100, 150, GROUP)
k = d.node("<b>Kafka ×3</b><br>KRaft + Apicurio", 60, 570, 170, 70, box("platform"))
r = d.node("<b>Redis</b><br>revocation · limits · cache", 270, 570, 170, 70, cyl("platform"))
m = d.node("<b>MongoDB</b><br>replica set<br>host + 2 Pis", 480, 560, 170, 90, cyl())
v = d.node("<b>File volume</b><br>/srv/sia-data", 690, 570, 170, 70, cyl("platform"))
p = d.node("<b>Prometheus</b><br>+ Alertmanager", 900, 570, 170, 70, box("platform"))
d.node("<b>CIMH mail</b><br>(SMTP from notification-svc)", 800, 405, 260, 50, box("external"))
d.node("<b>Connections:</b> every service reads/writes MongoDB (its own collections only), uses Redis, and produces/consumes "
       "Kafka (through its outbox relay). document-svc and media-worker write to the file volume, which nginx serves. "
       "Prometheus scrapes every service and exporter. See diagram 03 for who talks to whom.", 20, 690, 1100, 50, NOTE)
d.save()

# =================================================================== 03 service communication
d = Diagram("03-service-communication", "Synchronous HTTP calls between services (internal network, service tokens)")
o = d.node("<b>order-svc</b>", 420, 230, 200, 60, box("service"))
cat = d.node("<b>catalog-svc</b>", 60, 80, 200, 60, box("service"))
inv = d.node("<b>inventory-svc</b>", 780, 80, 200, 60, box("service"))
doc = d.node("<b>document-svc</b>", 780, 390, 200, 60, box("service"))
nt = d.node("<b>notification-svc</b>", 60, 390, 200, 60, box("service"))
d.edge(o, cat, "product snapshots · admin fee · Pro Bono limits", EDGE + "exitX=0;exitY=0.3;entryX=1;entryY=0.5;")
d.edge(o, inv, "availability (full qty per line?)", EDGE + "exitX=1;exitY=0.3;entryX=0;entryY=0.5;")
d.edge(doc, o, "access check (owner / organisation)", EDGE + "exitX=0;exitY=0.5;entryX=1;entryY=0.7;")
d.edge(nt, cat, "email lists (cached 5 min)", EDGE + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
idn = d.node("<b>identity-svc</b>", 420, 390, 200, 60, box("service"))
d.edge(nt, idn, "claim code once (codes never in Kafka)", EDGE + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
d.node("Rules: never through nginx · 2 s timeout · max 2 retries on reads · circuit breaker · "
       "on failure return 503, never write partial data.<br>Everything else between services goes through Kafka; see diagram 04.",
       60, 500, 920, 50, NOTE)
d.save()

# =================================================================== 04 kafka topics
d = Diagram("04-kafka-topics", "Kafka topics: producers → topic → consumers")
topics = [
    ("identity.user.events", "identity", "order, notification", "compacted"),
    ("catalog.product.events", "catalog", "inventory, order", "compacted"),
    ("inventory.stock.events", "inventory", "catalog, order, notification", "7 d"),
    ("order.events", "order", "inventory, document, notification", "7 d"),
    ("document.events", "document", "order, notification", "7 d"),
    ("media.jobs / media.results", "catalog / media-worker", "media-worker / catalog", "3 d"),
    ("audit.events", "all services", "identity", "30 d"),
]
for i, (t, p, c, ret) in enumerate(topics):
    y = 60 + i * 70
    a = d.node(p, 40, y, 190, 44, box("service"))
    b = d.node(f"<b>{t}</b><br><font style='font-size:10px'>key = entity id · retention {ret}</font>", 330, y - 4, 280, 52, box("platform"))
    c_ = d.node(c, 710, y, 250, 44, box("service"))
    d.edge(a, b, "produce")
    d.edge(b, c_, "consume")
d.node("Every topic has <b>.retry</b> and <b>.dlq</b> companions. Replication 3, min.insync.replicas 2, acks=all, idempotent producers. "
       "Envelope: eventId · type · version · occurredAt · correlationId · actorId · payload.", 40, 560, 920, 50, NOTE)
d.save()

# =================================================================== 05 outbox
sequence("05-outbox-relay", "Outbox: change and event saved together, then published", [
    ("api", "Service API", "service"), ("db", "MongoDB<br>(owning collection)", "data"),
    ("rel", "Outbox relay", "worker"), ("k", "Kafka", "platform"), ("c", "Consumer service", "service")], [
    ("api", "db", "updateOne({_id, status: expected}, {$set: new, $push: {outbox: event}})"),
    ("note", "db", "State and event written in ONE operation (or one transaction)"),
    ("db", "rel", "(change stream / 30 s sweep)"),
    ("rel", "k", "produce(event, key = entity id), acks=all"),
    ("k", "rel", "(ack)"),
    ("rel", "db", "$pull sent event from outbox"),
    ("k", "c", "deliver"),
    ("c", "c", "SET NX eventId in Redis (skip duplicates)"),
    ("c", "c", "apply with conditional update; on failure → .retry → .dlq"),
], col=210)

# =================================================================== 06 deployment
d = Diagram("06-deployment", "Deployment: main host + 2 Raspberry Pi 5 (Docker Compose)")
d.node("Main host: 16 cores · 32 GB RAM · 2 × 6 GB GPU · Compose project sia-prod", 20, 50, 760, 520, GROUP)
d.node("<b>nginx + certbot</b><br>:80 / :443", 50, 90, 200, 50, box("edge"))
d.node("<b>identity · catalog · inventory<br>order · document · notification</b><br>×2 replicas each", 280, 90, 230, 70, box("service"))
d.node("<b>outbox relays</b>", 540, 90, 210, 50, box("worker"))
d.node("<b>media-worker ×2</b><br>GPU 0 / GPU 1", 50, 190, 200, 50, box("worker"))
d.node("<b>Kafka ×3</b> + Apicurio", 280, 190, 230, 50, box("platform"))
d.node("<b>Redis</b>", 540, 190, 210, 50, cyl("platform"))
d.node("<b>/srv/sia-data</b><br>files volume (restic nightly → other site)", 50, 290, 200, 70, cyl("platform"))
d.node("<b>Prometheus + Alertmanager</b><br>+ exporters", 280, 290, 230, 60, box("platform"))
m1 = d.node("<b>mongo1</b><br>PRIMARY · priority 10", 540, 290, 210, 70, cyl())
d.node("<b>sia-staging</b> (separate Compose project, started on demand)", 50, 400, 700, 50, box("external", "dashed=1;"))
d.node("Memory budget ≈ 28–30 GB of 32 GB · every container has mem_limit", 50, 480, 700, 40, NOTE)
d.node("Raspberry Pi 5 A · 8 GB · NVMe", 860, 50, 260, 150, GROUP)
m2 = d.node("<b>mongo2</b><br>SECONDARY · priority 1", 880, 100, 220, 70, cyl())
d.node("Raspberry Pi 5 B · 8 GB · NVMe", 860, 260, 260, 230, GROUP)
m3 = d.node("<b>mongo3</b><br>SECONDARY · priority 1", 880, 300, 220, 70, cyl())
bk = d.node("<b>backup job</b><br>mongodump + restic", 880, 410, 220, 50, box("worker"))
off = d.node("<b>Other CIMH site</b><br>encrypted backups", 880, 560, 220, 60, cyl("external"))
d.edge(m1, m2, "replication (TLS)", EDGE + "exitX=1;exitY=0.3;entryX=0;entryY=0.5;")
d.edge(m1, m3, "replication (TLS)", EDGE + "exitX=1;exitY=0.6;entryX=0;entryY=0.5;")
d.edge(bk, off, "restic nightly", EDGE + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
d.node("UPS covers all three machines ≥ 15 min", 20, 600, 400, 30, NOTE)
d.save()

# =================================================================== 07 networks
d = Diagram("07-networks", "Docker networks and firewall (main host)")
inet = d.node("Internet / CIMH LAN", 40, 70, 180, 50, box("external"))
d.node("network: edge", 260, 50, 220, 110, GROUP)
ng = d.node("<b>nginx</b>", 290, 90, 160, 50, box("edge"))
d.node("network: app", 520, 50, 260, 110, GROUP)
sv = d.node("<b>services</b>", 570, 90, 160, 50, box("service"))
d.node("network: data (internal, not routable)", 260, 210, 520, 120, GROUP)
mo = d.node("<b>MongoDB</b>", 290, 255, 140, 50, cyl())
ka = d.node("<b>Kafka</b>", 450, 255, 140, 50, box("platform"))
re = d.node("<b>Redis</b>", 610, 255, 140, 50, cyl("platform"))
pis = d.node("<b>Pi A / Pi B</b><br>fixed IPs", 860, 240, 160, 60, cyl())
d.edge(inet, ng, ":443 only")
d.edge(ng, sv, "proxy")
d.edge(sv, mo, "")
d.edge(sv, ka, "")
d.edge(sv, re, "")
d.edge(pis, mo, "27017: Pis + host only<br>(ufw/nftables)")
d.save()

# =================================================================== 08 data ownership
d = Diagram("08-data-ownership", "Data ownership: one inventory database, each collection owned by one service")
groups = [
    ("identity-svc", ["accounts", "temp", "organisations (new)", "auditlog (new)"], 20),
    ("catalog-svc", ["product", "xuser (view)", "misc"], 290),
    ("inventory-svc", ["storage", "history", "stock (new)"], 560),
    ("order-svc", ["orders (incl. carts)"], 830),
]
coll = {}
for svcname, cols, x in groups:
    d.node(svcname, x, 60, 250, 70 + 60 * len(cols), GROUP)
    for i, c in enumerate(cols):
        coll[c.split(" ")[0]] = d.node(f"<b>{c}</b>", x + 30, 100 + i * 60, 190, 44, cyl())
d.node("document-svc and notification-svc own no collections: file metadata is stored in orders.files[]; "
       "files live on /srv/sia-data.", 20, 380, 1060, 40, NOTE)
d.save()

# =================================================================== 09 ER
d = Diagram("09-entity-relationships", "Key relationships between collections (by id, no joins across services)")
e = {}
spots = {"organisations": (60, 80), "accounts": (60, 300), "orders": (460, 300), "product": (860, 80),
         "storage": (860, 300), "history": (860, 520), "auditlog": (60, 520)}
fields = {
    "organisations": "id · name · country · domains[]",
    "accounts": "id · email · role · status<br>organisationId · statusHistory[]",
    "orders": "id · status · type (PAID/PROBONO) · customer<br>organisationId · currency · lines[]<br>quotes[] · cimhQuote · acceptance<br>shipping · files[] · history[] · outbox[]",
    "product": "id · name · make · model · type<br>sellable · probono · probonoMaxPerRequest · cost",
    "storage": "barcode · product · site/location/shelf<br>stowed · picked · reservedFor",
    "history": "operation · barcode · user · date",
    "auditlog": "actor · action · entity · at · reason",
}
for k, (x, y) in spots.items():
    e[k] = d.node(f"<b>{k}</b><hr>{fields[k]}", x, y, 300, 110 if k == "orders" else 80,
                  "swimlane;html=1;startSize=0;rounded=1;whiteSpace=wrap;align=left;spacingLeft=8;verticalAlign=top;" +
                  f"fillColor={C['data'][0]};strokeColor={C['data'][1]};" + FONT)
REL = EDGE + "endArrow=ERmany;startArrow=ERone;endFill=0;startFill=0;"
d.edge(e["organisations"], e["accounts"], "organisationId", REL)
d.edge(e["accounts"], e["orders"], "customer", REL)
d.edge(e["organisations"], e["orders"], "organisationId", REL + "exitX=1;exitY=0.75;entryX=0.2;entryY=0;")
d.edge(e["product"], e["storage"], "product", REL)
d.edge(e["orders"], e["storage"], "reservedFor", REL)
d.edge(e["product"], e["orders"], "lines[].productId", REL + "exitX=0;exitY=0.75;entryX=0.8;entryY=0;")
d.edge(e["storage"], e["history"], "barcode", REL)
d.edge(e["accounts"], e["auditlog"], "actor / entity", REL)
d.save()

# =================================================================== 10–12 state machines
states("10-account-status", "Account status flow", {
    "START": (20, 212, ""), "PENDING_VERIFICATION": (80, 200, "state"), "PENDING_APPROVAL": (400, 200, "state"),
    "ACTIVE": (720, 200, "final"), "REJECTED": (400, 350, "bad"), "EXPIRED": (80, 350, "bad"), "SUSPENDED": (720, 350, "bad")},
    [("START", "PENDING_VERIFICATION", "register"), ("PENDING_VERIFICATION", "PENDING_APPROVAL", "email verified"),
     ("PENDING_APPROVAL", "ACTIVE", "admin approves"), ("PENDING_APPROVAL", "REJECTED", "admin denies (reason)"),
     ("PENDING_VERIFICATION", "EXPIRED", "24 h"), ("ACTIVE", "SUSPENDED", "admin suspends", "exitX=0.2;exitY=1;entryX=0.2;entryY=0;"),
     ("SUSPENDED", "ACTIVE", "admin reactivates", "exitX=0.8;exitY=0;entryX=0.8;entryY=1;"),
     ("PENDING_VERIFICATION", "ACTIVE", "@cimh.edu.bb: skip approval", "exitX=0.5;exitY=0;entryX=0.5;entryY=0;")], w=200)

states("11-paid-request-status", "Paid order request status flow", {
    "START": (20, 112, ""), "SUBMITTED": (80, 100, "state"), "QUOTING": (290, 100, "state"), "QUOTED": (500, 100, "state"),
    "AWAITING_AGREEMENT": (830, 100, "state"), "ACCEPTED": (1220, 100, "state"), "PURCHASING": (1460, 100, "state"),
    "SHIPPED": (1460, 250, "state"), "DELIVERED": (1460, 400, "final"), "DECLINED": (560, 250, "bad"),
    "CANCELLED": (80, 400, "bad"), "END": (1670, 408, "")},
    [("START", "SUBMITTED", ""), ("SUBMITTED", "QUOTING", "staff start<br>quoting"), ("QUOTING", "QUOTED", "send<br>quote(s)"),
     ("QUOTED", "AWAITING_AGREEMENT", "chooses options", "exitX=1;exitY=0.25;entryX=0;entryY=0.25;"),
     ("AWAITING_AGREEMENT", "QUOTED", "changes choices", "exitX=0;exitY=0.75;entryX=1;entryY=0.75;"),
     ("AWAITING_AGREEMENT", "ACCEPTED", "signed agreement", "exitX=1;exitY=0.25;entryX=0;entryY=0.25;"),
     ("ACCEPTED", "AWAITING_AGREEMENT", "signature rejected", "exitX=0;exitY=0.75;entryX=1;entryY=0.75;"),
     ("ACCEPTED", "PURCHASING", "verified +<br>POs placed"),
     ("PURCHASING", "SHIPPED", "carrier + tracking<br>(supplier items direct)"), ("SHIPPED", "DELIVERED", ""), ("DELIVERED", "END", ""),
     ("QUOTED", "QUOTED", "quote revised", "exitX=0.75;exitY=0;entryX=0.25;entryY=0;"),
     ("QUOTED", "DECLINED", "customer declines", DOWN.format(ex=0.75, en=0.48)),
     ("SUBMITTED", "CANCELLED", "cancel", DOWN.format(ex=0.5, en=0.058)),
     ("QUOTING", "CANCELLED", "cancel", DOWN.format(ex=0.5, en=0.219)),
     ("QUOTED", "CANCELLED", "expired (30 d)", DOWN.format(ex=0.12, en=0.337)),
     ("DECLINED", "CANCELLED", "", DOWN.format(ex=0.5, en=0.427)),
     ("AWAITING_AGREEMENT", "CANCELLED", "expired /<br>cancel", DOWN.format(ex=0.5, en=0.658)),
     ("ACCEPTED", "CANCELLED", "cancel<br>(release stock)", DOWN.format(ex=0.5, en=0.935))],
    layout_w={"CANCELLED": 1300, "AWAITING_AGREEMENT": 210})

states("12-probono-request-status", "Pro Bono request status flow: no quote", {
    "START": (40, 112, ""), "SUBMITTED": (100, 100, "state"), "APPROVED": (330, 100, "state"), "PICKING": (560, 100, "state"),
    "SHIPPED": (790, 100, "state"), "DELIVERED": (790, 240, "final"), "REJECTED": (40, 260, "bad"), "CANCELLED": (260, 260, "bad")},
    [("START", "SUBMITTED", ""), ("SUBMITTED", "APPROVED", "staff approve<br>(reserve stock)"), ("APPROVED", "PICKING", ""),
     ("PICKING", "SHIPPED", ""), ("SHIPPED", "DELIVERED", ""),
     ("SUBMITTED", "REJECTED", "staff reject", DOWN.format(ex=0.2, en=0.6)),
     ("SUBMITTED", "CANCELLED", "cancel", DOWN.format(ex=0.8, en=0.2)),
     ("APPROVED", "CANCELLED", "cancel<br>(release stock)", DOWN.format(ex=0.5, en=0.8))])

# =================================================================== 13 registration
sequence("13-registration-flow", "Registration, verification and admin approval", [
    ("u", "Registrant", "actor"), ("shop", "SHOP", "client"), ("id", "identity-svc", "service"),
    ("k", "Kafka", "platform"), ("n", "notification-svc", "service"), ("a", "Admin (SIA)", "actor")], [
    ("u", "shop", "fill sign-up form"),
    ("shop", "id", "POST /accounts"),
    ("id", "id", "PENDING_VERIFICATION + code in temp (hashed + sealed copy)"),
    ("id", "k", "user.registered (codeRef only)"),
    ("k", "n", "user.registered"),
    ("n", "id", "GET /internal/codes/{codeRef} (once)"),
    ("n", "u", "email with 6-digit code"),
    ("u", "shop", "enter 6-digit code"),
    ("shop", "id", "POST /accounts/verify"),
    ("alt", "if email ends with @cimh.edu.bb → ACTIVE immediately (cannot request items)"),
    ("alt", "else (member-state user)"),
    ("id", "id", "PENDING_APPROVAL"),
    ("id", "k", "user.verified"),
    ("k", "n", "email admins + 'awaiting approval' to user"),
    ("a", "id", "approve (organisation, role) / deny (reason)"),
    ("id", "k", "user.approved / user.rejected + audit"),
    ("k", "n", "email user the decision"),
], col=180)

# =================================================================== 14 paid request
sequence("14-paid-request-flow", "Paid request: quote, CIMH stock option, acceptance, fulfilment", [
    ("c", "Customer", "actor"), ("o", "order-svc", "service"), ("cat", "catalog-svc", "service"),
    ("i", "inventory-svc", "service"), ("d", "document-svc", "service"), ("k", "Kafka", "platform"), ("s", "Staff", "actor")], [
    ("c", "o", "submit cart (currency BBD | USD)"),
    ("o", "cat", "product snapshots, Pro Bono limits"),
    ("o", "o", "split → PAID (+ Pro Bono) request"),
    ("o", "k", "order.submitted"),
    ("s", "o", "start quoting"),
    ("o", "i", "availability (full qty per line?)"),
    ("o", "o", "build CIMH option (cost + fee, rate if USD)"),
    ("s", "d", "upload supplier quote PDFs"),
    ("s", "o", "send quote (expires in 30 d)"),
    ("o", "k", "order.quoted"),
    ("k", "d", "generate CIMH quote PDF"),
    ("c", "o", "choose CIMH or SUPPLIER per line → AWAITING_AGREEMENT"),
    ("o", "k", "order.agreement_requested"),
    ("k", "d", "generate agreement PDF (total)"),
    ("c", "d", "download, sign, upload signed agreement"),
    ("c", "o", "accept (signed file id) → ACCEPTED"),
    ("o", "k", "order.accepted"),
    ("k", "i", "reserve CIMH lines (transaction)"),
    ("alt", "if stock no longer available → stock.reservation_failed → staff requote that line"),
    ("s", "o", "verify signature + purchase orders → PURCHASING"),
    ("alt", "supplier items ship direct to the customer (no stock); staff pick CIMH-stock lines only"),
    ("s", "o", "ship: carrier + tracking → SHIPPED"),
    ("s", "o", "→ DELIVERED"),
    ("k", "d", "generate invoice"),
], col=165)

# =================================================================== 15 reservation
d = Diagram("15-stock-reservation", "Stock reservation in inventory-svc (MongoDB transaction)")
steps = [
    ("Event order.accepted / order.probono_approved", "client"),
    ("Start transaction<br>readConcern snapshot · writeConcern majority", "service"),
    ("For each line: find N units<br>product = X · stowed · not picked · reservedFor = null", "service"),
    ("updateMany({_id ∈ ids, reservedFor: null},<br>{$set: {reservedFor: orderId}})", "service"),
]
prev = None
for i, (t, kind) in enumerate(steps):
    cur = d.node(t, 330, 60 + i * 95, 340, 60, box(kind))
    if prev:
        d.edge(prev, cur)
    prev = cur
dec = d.node("modified count<br>= requested?", 420, 450, 160, 90, "rhombus;whiteSpace=wrap;html=1;" + f"fillColor={C['note'][0]};strokeColor={C['note'][1]};" + FONT)
d.edge(prev, dec)
ok = d.node("Push <b>stock.reserved</b> to outbox<br>COMMIT", 640, 580, 260, 60, box("final"))
bad = d.node("ABORT<br>publish <b>stock.reservation_failed</b>", 100, 580, 260, 60, box("bad"))
d.edge(dec, ok, "yes")
d.edge(dec, bad, "no")
d.node("TransientTransactionError → retry up to 3 times.<br>Release on cancel: updateMany({reservedFor: orderId}, {$set: {reservedFor: null}}): safe to repeat.",
       640, 450, 340, 70, NOTE)
d.save()

# =================================================================== 16 stow / pick
d = Diagram("16-stow-pick-flow", "Stow and pick (SIA web or SIA Mobile)")
a = d.node("Scan shelf QR", 40, 80, 160, 50, box("client"))
b = d.node("GET /inventory/v1/shelves/{barcode}<br>shelf valid?", 250, 70, 230, 70, box("service"))
c = d.node("Scan unit barcode", 530, 80, 160, 50, box("client"))
dd = d.node("POST /inventory/v1/stow or /pick<br>Idempotency-Key = scan id", 740, 70, 260, 70, box("service"))
e_ = d.node("Update storage unit<br>(location, stowby/pickedby, dates)", 740, 200, 260, 60, box("service"))
f = d.node("Add history record", 740, 300, 260, 50, cyl())
g = d.node("Publish unit.stowed / unit.picked<br>+ stock.changed", 740, 390, 260, 60, box("platform"))
off = d.node("Mobile offline? Scan is queued in Room/WorkManager and resent later; the same Idempotency-Key prevents doubles.",
             40, 200, 440, 60, NOTE)
pk = d.node("Picking for a request: the unit must be reserved for that orderId.", 40, 300, 440, 40, NOTE)
for x_, y_ in [(a, b), (b, c), (c, dd), (dd, e_), (e_, f), (f, g)]:
    d.edge(x_, y_)
d.edge(g, c, "next unit", EDGE_DASH)
d.save()

# =================================================================== 17 file download
sequence("17-protected-download", "Protected file download (X-Accel-Redirect)", [
    ("u", "User", "actor"), ("n", "nginx", "edge"), ("d", "document-svc", "service"), ("o", "order-svc", "service")], [
    ("u", "n", "GET /api/documents/v1/files/{fileId}"),
    ("n", "d", "proxy"),
    ("d", "d", "verify token, file → requestId"),
    ("alt", "staff / admin → allowed"),
    ("alt", "customer → ask order-svc"),
    ("d", "o", "GET /internal/requests/{id}/access?user="),
    ("o", "d", "(owner or same organisation → allowed)"),
    ("d", "n", "200 + X-Accel-Redirect: /_protected/{uuid}  (or 403)"),
    ("n", "u", "file streamed by nginx"),
], col=240)

# =================================================================== 18 auth / tokens
sequence("18-auth-tokens", "Login, token refresh and revocation", [
    ("c", "Client", "client"), ("id", "identity-svc", "service"), ("r", "Redis", "data"), ("s", "Any service", "service")], [
    ("c", "id", "POST /auth/login (email, password)"),
    ("id", "id", "status ACTIVE? Argon2id verify · lockout after 5 fails"),
    ("id", "c", "(access 15 min + refresh 7 d; cookies or Bearer)"),
    ("c", "s", "request with access token"),
    ("s", "s", "verify EdDSA signature with cached JWKS"),
    ("s", "r", "jti revoked?"),
    ("c", "id", "POST /auth/refresh"),
    ("id", "c", "(new access + NEW refresh; old refresh invalid)"),
    ("note", "id", "Reused old refresh token → revoke whole session family"),
    ("c", "id", "POST /auth/logout"),
    ("id", "r", "store revoked jti until expiry"),
], col=230)

# =================================================================== 19–21 app maps
def sitemap(name, title, root, children, kind="client"):
    d = Diagram(name, title)
    r_ = d.node(f"<b>{root}</b>", 40 + (len(children) * 190) / 2 - 90, 60, 180, 50, box("edge"))
    for i, (label, subs) in enumerate(children):
        x = 40 + i * 190
        c_ = d.node(f"<b>{label}</b>", x, 170, 170, 46, box(kind))
        d.edge(r_, c_)
        prev = c_
        for j, s in enumerate(subs):
            sn = d.node(s, x + 10, 250 + j * 62, 150, 46, box("external"))
            d.edge(prev, sn)
            prev = sn
    d.save()


sitemap("19-shop-sitemap", "SHOP: navigation map", "store.cimh.edu.bb", [
    ("Home", ["Featured met / radar", "Tour"]),
    ("Catalogue", ["Search / filter", "Product detail", "Add to cart"]),
    ("Pro Bono items", ["Pro Bono detail", "Add (max per item)"]),
    ("Cart", ["Choose currency", "Submit request", "Request placed"]),
    ("My requests", ["Request detail", "Review quotes", "Accept / decline", "Documents & tracking"]),
    ("Account", ["Sign up", "Verify email", "Awaiting approval", "Login / reset", "Profile & addresses"]),
])
sitemap("20-sia-sitemap", "SIA web: navigation map", "sia.cimh.edu.bb (staff / admin)", [
    ("Request desk", ["Queue (filters)", "Request detail", "Start quoting", "Upload quotes / send", "POs · ship · deliver"]),
    ("Catalogue", ["Products", "Create / edit", "Images (bg removal)", "Pro Bono limits"]),
    ("Inventory", ["Sites / shelves", "Stow", "Pick / relocate", "Lookup", "Labels (QR)"]),
    ("Reports", ["Stock levels", "Who has what", "Movement history"]),
    ("Admin", ["Pending accounts", "Users & roles", "Organisations", "Email lists · fees", "Audit log"]),
])
sitemap("21-mobile-sitemap", "SIA Mobile: navigation map", "SIA Mobile (staff)", [
    ("Login", ["Secure token storage"]),
    ("Lookup", ["Scan shelf / product", "Results (paged)", "Product detail"]),
    ("Stow", ["Scan shelf", "Scan units"]),
    ("Pick", ["Scan unit", "Reason"]),
    ("Orders", ["Approved requests", "Pick order", "Ship (carrier + tracking)"]),
    ("Create", ["Product (+ photos)", "Location"]),
])

# =================================================================== 22 transition
# 22 (legacy transition / cut-over) is generated after flow() is defined, see below

# =================================================================== 23 documentation map
d = Diagram("23-documentation-map", "How the project documents depend on each other")
docs = {"PRD": (60, 120), "TRD": (300, 60), "TAD": (300, 180), "BSD": (540, 60), "API Spec": (540, 180),
        "APD": (540, 300), "Design Brief": (780, 300), "Security": (780, 60), "Migration": (780, 180),
        "Implementation Plan": (1020, 180)}
dn = {k: d.node(f"<b>{k}</b>", x, y, 170, 50, box("final" if k in ("PRD", "TRD", "TAD") else "client")) for k, (x, y) in docs.items()}
for a_, b_ in [("PRD", "TRD"), ("PRD", "TAD"), ("TRD", "TAD"), ("TAD", "BSD"), ("TAD", "API Spec"), ("PRD", "APD"),
               ("APD", "Design Brief"), ("TAD", "Security"), ("BSD", "Migration"), ("API Spec", "Implementation Plan"),
               ("Migration", "Implementation Plan"), ("Design Brief", "Implementation Plan"), ("Security", "Implementation Plan")]:
    d.edge(dn[a_], dn[b_])
d.text("Green = drafted · Blue = planned", 60, 380, 400, 30)
d.save()

# =================================================================== 24–27 user journeys (APD)
DEC = "rhombus;whiteSpace=wrap;html=1;" + f"fillColor={C['note'][0]};strokeColor={C['note'][1]};" + FONT + "fontSize=11;"
KINDS = {"screen": lambda: box("client"), "sys": lambda: box("service"), "email": lambda: NOTE,
         "ok": lambda: box("final", "arcSize=40;fontStyle=1;"), "bad": lambda: box("bad", "arcSize=40;fontStyle=1;"),
         "dec": lambda: DEC, "staff": lambda: box("edge")}


def flow(name, title, nodes, edges, legend=True):
    """nodes: key -> (label, x, y, kind[, w, h]); edges: (a, b, label[, extra style])."""
    d = Diagram(name, title)
    ids = {}
    for k, v in nodes.items():
        label, x, y, kind = v[:4]
        w = v[4] if len(v) > 4 else (130 if kind == "dec" else 170)
        h = v[5] if len(v) > 5 else (80 if kind == "dec" else 50)
        ids[k] = d.node(label, x, y, w, h, KINDS[kind]())
    for e in edges:
        d.edge(ids[e[0]], ids[e[1]], e[2], EDGE + (e[3] if len(e) > 3 else ""))
    if legend:
        lx = 20
        for lbl, kind in [("Screen (customer)", "screen"), ("Screen (staff/admin)", "staff"), ("System step", "sys"),
                          ("Email", "email"), ("Decision", "dec"), ("Good end", "ok"), ("Stopped", "bad")]:
            d.node(lbl, lx, 44, 120, 22, KINDS[kind]() + "fontSize=10;")
            lx += 130
    d.save()


flow("24-journey-registration", "J-01 Registration and approval", {
    "signup": ("<b>S-13 Sign up</b>", 40, 110, "screen"),
    "create": ("Create account<br>PENDING_VERIFICATION", 280, 110, "sys"),
    "mail1": ("Email: 6-digit code", 520, 110, "email", 170, 50),
    "verify": ("<b>S-14 Verify email</b>", 760, 110, "screen"),
    "code": ("Code<br>correct?", 780, 200, "dec"),
    "cimh": ("@cimh<br>.edu.bb?", 780, 320, "dec"),
    "active1": ("ACTIVE<br>(cannot request items)", 1000, 335, "ok"),
    "pending": ("PENDING_APPROVAL", 520, 335, "sys"),
    "wait": ("<b>S-15 Awaiting approval</b>", 280, 335, "screen"),
    "mail2": ("Email admins<br>(registration list)", 520, 440, "email"),
    "a16": ("<b>A-16 Pending accounts</b>", 520, 540, "staff"),
    "decide": ("Approve?", 540, 640, "dec"),
    "approved": ("ACTIVE + organisation<br>+ role; email user", 760, 655, "ok"),
    "rejected": ("REJECTED (reason);<br>email user", 280, 655, "bad"),
    "login": ("<b>S-16 Log in</b>", 1000, 655, "screen"),
    "requests": ("<b>S-10 My requests</b>", 1000, 760, "screen"),
}, [
    ("signup", "create", "submit"), ("create", "mail1", ""), ("mail1", "verify", ""), ("verify", "code", "enter code"),
    ("code", "verify", "no (5 tries,<br>resend 3/h)", "exitX=1;exitY=0.5;entryX=1;entryY=0.5;"),
    ("code", "cimh", "yes"), ("cimh", "active1", "yes"), ("cimh", "pending", "no"),
    ("pending", "wait", ""), ("pending", "mail2", ""), ("mail2", "a16", ""), ("a16", "decide", ""),
    ("decide", "approved", "yes"), ("decide", "rejected", "no"), ("approved", "login", ""),
    ("active1", "login", "", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"), ("login", "requests", ""),
])

flow("25-journey-quote-acceptance", "J-02 / J-03 Customer: cart → request → quote → signed agreement", {
    "browse": ("<b>S-02 / S-04 / S-06</b><br>browse, Pro Bono, search", 40, 110, "screen", 190, 55),
    "detail": ("<b>S-03 Product</b><br>Add to request", 290, 110, "screen", 170, 55),
    "cart": ("<b>S-07 Cart</b>", 520, 110, "screen"),
    "submit": ("<b>S-08 Submit</b><br>address, BBD/USD, notes", 760, 110, "screen", 190, 55),
    "mixed": ("Paid AND<br>Pro Bono?", 1010, 100, "dec"),
    "two": ("Two requests<br>PAID + PROBONO", 1200, 50, "sys"),
    "one": ("One request", 1200, 160, "sys"),
    "done": ("<b>S-09 Submitted</b>", 1200, 260, "screen"),
    "quotemail": ("Email: quote ready", 960, 380, "email"),
    "s11": ("<b>S-11 Request</b><br>supplier + CIMH options", 720, 370, "screen", 190, 60),
    "accept": ("Proceed?", 500, 360, "dec"),
    "decline": ("DECLINED → CANCELLED", 260, 375, "bad", 190, 50),
    "choose": ("<b>S-12 step 1</b><br>choose CIMH / SUPPLIER per line", 470, 490, "screen", 200, 60),
    "awaiting": ("AWAITING_AGREEMENT<br>agreement PDF generated", 470, 600, "sys", 200, 55),
    "sign": ("<b>S-12 step 2</b><br>download + sign", 470, 710, "screen", 200, 55),
    "upload": ("<b>S-12 step 3</b><br>upload signed copy", 470, 820, "screen", 200, 55),
    "accepted": ("ACCEPTED<br>(commitment to pay)", 760, 820, "ok", 190, 55),
    "track": ("<b>S-11</b> track: PURCHASING →<br>SHIPPED (tracking) → DELIVERED", 1010, 820, "screen", 230, 55),
    "expired": ("Quote expired (30 d)<br>→ CANCELLED", 160, 600, "bad", 190, 55),
    "rejected": ("Email: signature rejected", 760, 930, "email", 190, 45),
}, [
    ("browse", "detail", ""), ("detail", "cart", ""), ("cart", "submit", "continue"), ("submit", "mixed", "submit"),
    ("mixed", "two", "yes"), ("mixed", "one", "no"), ("two", "done", "", "exitX=1;exitY=0.5;entryX=1;entryY=0.3;"), ("one", "done", ""),
    ("done", "quotemail", "staff quote", EDGE_DASH[len(EDGE):]), ("quotemail", "s11", ""), ("s11", "accept", ""),
    ("accept", "decline", "decline"), ("accept", "choose", "choose options"), ("choose", "awaiting", "confirm"),
    ("awaiting", "sign", ""), ("sign", "upload", ""), ("upload", "accepted", "accept"),
    ("awaiting", "choose", "change choices", "exitX=1;exitY=0.5;entryX=1;entryY=0.5;"),
    ("awaiting", "expired", "no upload in time"), ("accepted", "track", ""),
    ("accepted", "rejected", "staff rejects<br>signature", "dashed=1;"),
    ("rejected", "upload", "upload again", "exitX=0;exitY=0.5;entryX=0.5;entryY=1;"),
])

flow("26-journey-staff-desk", "J-05 / J-06 / J-07 Staff request desk (SIA)", {
    "a01": ("<b>A-01 Dashboard</b><br>counters", 40, 110, "staff"),
    "a02": ("<b>A-02 Queue</b><br>sorted by waiting", 270, 110, "staff"),
    "a03": ("<b>A-03 Request</b><br>allowedActions", 500, 110, "staff"),
    "type": ("Type?", 750, 100, "dec"),
    "start": ("Start quoting<br>(stock check) → QUOTING", 940, 40, "sys", 200, 55),
    "a04": ("<b>A-04 Quote builder</b><br>supplier PDFs + prices,<br>CIMH option, exchange rate", 1190, 30, "staff", 210, 75),
    "send": ("Send quote → QUOTED<br>(customer emailed)", 1190, 150, "sys", 210, 55),
    "cust": ("Customer chooses, signs,<br>uploads → ACCEPTED", 1190, 260, "email", 210, 55),
    "verify": ("Signature<br>OK?", 1230, 370, "dec"),
    "rej": ("Reject signature →<br>AWAITING_AGREEMENT", 1450, 385, "bad", 190, 55),
    "po": ("☑ verified + POs →<br>PURCHASING", 1190, 490, "sys", 210, 55),
    "pick": ("<b>A-10 / M-07 Pick</b><br>CIMH-stock + Pro Bono lines only", 860, 490, "staff", 230, 55),
    "approve": ("Approve?", 770, 250, "dec"),
    "pbrej": ("REJECTED (reason)", 520, 265, "bad"),
    "pbok": ("APPROVED<br>(stock reserved)", 760, 380, "sys"),
    "ship": ("<b>Ship</b> ⧉ carrier, tracking<br>(not HAND) → SHIPPED", 560, 600, "staff", 220, 55),
    "deliver": ("<b>Deliver</b> → DELIVERED<br>invoice generated", 240, 600, "ok", 210, 55),
}, [
    ("a01", "a02", ""), ("a02", "a03", "open"), ("a03", "type", ""),
    ("type", "start", "PAID"), ("start", "a04", ""), ("a04", "send", "send"), ("send", "cust", "", "dashed=1;"),
    ("cust", "verify", ""), ("verify", "rej", "no"), ("verify", "po", "yes"),
    ("rej", "cust", "re-upload", "exitX=0.5;exitY=0;entryX=1;entryY=0.5;dashed=1;"),
    ("po", "pick", "CIMH lines"), ("pick", "ship", ""),
    ("type", "approve", "PROBONO"), ("approve", "pbrej", "no"), ("approve", "pbok", "yes"), ("pbok", "pick", ""),
    ("ship", "deliver", ""),
    ("po", "ship", "supplier items<br>ship direct", "exitX=0.5;exitY=1;entryX=1;entryY=0.5;dashed=1;"),
])

flow("27-journey-mobile-scan", "J-09 Warehouse scanning (SIA Mobile)", {
    "home": ("<b>M-02 Home</b><br>offline badge", 40, 110, "screen"),
    "stow": ("<b>M-04 Stow</b><br>scan shelf", 280, 110, "screen"),
    "shelfok": ("Shelf<br>valid?", 300, 200, "dec"),
    "unit": ("Scan unit", 280, 320, "screen"),
    "online": ("Online?", 300, 410, "dec"),
    "send": ("POST /stow<br>Idempotency-Key = scan id", 500, 425, "sys", 210, 55),
    "queue": ("Save in Room<br>queued chip (grey)", 60, 425, "sys", 190, 55),
    "res": ("Result?", 780, 410, "dec"),
    "ok": ("✓ chip + beep", 990, 425, "ok", 150, 50),
    "err": ("✗ error chip + vibrate<br>(not found, already stowed)", 990, 530, "bad", 230, 55),
    "sync": ("WorkManager sync<br>failures → <b>M-11</b>", 60, 540, "sys", 190, 55),
    "orders": ("<b>M-06 Orders</b><br>to pick / ship", 560, 110, "screen"),
    "pickorder": ("<b>M-07 Pick order</b><br>scan per line", 800, 110, "screen"),
    "lineok": ("Reserved for<br>this request?", 1030, 95, "dec", 140, 90),
    "lineerr": ("✗ UNIT_NOT_RESERVED_FOR_ORDER /<br>LINE_NOT_PICKABLE", 975, 240, "bad", 250, 55),
    "alldone": ("All lines<br>picked → <b>M-08 Ship</b>", 1250, 110, "ok", 200, 55),
}, [
    ("home", "stow", ""), ("stow", "shelfok", ""), ("shelfok", "stow", "no: rescan", "exitX=0;exitY=0.5;entryX=0;entryY=0.5;"),
    ("shelfok", "unit", "yes"), ("unit", "online", ""), ("online", "send", "yes"), ("online", "queue", "no"),
    ("send", "res", ""), ("res", "ok", "200"), ("res", "err", "4xx", "exitX=0.5;exitY=1;entryX=0;entryY=0.5;"), ("queue", "sync", ""), ("sync", "send", "when online", "dashed=1;"),
    ("ok", "unit", "next unit", "exitX=0.5;exitY=0;entryX=1;entryY=0.5;dashed=1;"),
    ("home", "orders", "", "exitX=0.5;exitY=0;entryX=0.5;entryY=0;"), ("orders", "pickorder", ""), ("pickorder", "lineok", "scan"),
    ("lineok", "alldone", "yes"), ("lineok", "lineerr", "no", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"),
])

# =================================================================== 28 design tokens (Design Brief)
d = Diagram("28-design-tokens", "Design tokens: colour (light / dark), status chips, type and shape")


def swatch(x, y, name, hexv, text="#FFFFFF", w=150):
    d.node(f"<b>{name}</b><br>{hexv}", x, y, w, 64,
           f"rounded=1;arcSize=12;whiteSpace=wrap;html=1;fillColor={hexv};strokeColor=#3A4552;fontColor={text};"
           + FONT + "fontSize=11;align=left;spacingLeft=8;")


d.text("<b>Light theme</b>", 20, 50, 300, 24)
row = [("primary", "#006FA8", "#FFFFFF"), ("brand-logo", "#0084C8", "#FFFFFF"), ("primary-subtle", "#E6F4FB", "#0F1A24"),
       ("accent-probono", "#F5C400", "#0F1A24"), ("ink", "#0F1A24", "#FFFFFF"), ("ink-muted", "#53606C", "#FFFFFF"),
       ("bg", "#F5F7FA", "#0F1A24"), ("surface", "#FFFFFF", "#0F1A24")]
for i, (n, h, t) in enumerate(row):
    swatch(20 + i * 160, 80, n, h, t)
row = [("success", "#1A7F37", "#FFFFFF"), ("warning", "#B54708", "#FFFFFF"), ("error", "#B42318", "#FFFFFF"),
       ("hairline", "#E1E6EC", "#0F1A24"), ("hairline-strong", "#C7D0DA", "#0F1A24"), ("surface-2", "#F0F3F7", "#0F1A24")]
for i, (n, h, t) in enumerate(row):
    swatch(20 + i * 160, 154, n, h, t)

d.text("<b>Dark theme</b>", 20, 240, 300, 24)
row = [("primary", "#5CC2FF", "#0D1117"), ("brand-logo", "#0084C8", "#FFFFFF"), ("primary-subtle", "#0B2A3D", "#E6EDF3"),
       ("accent-probono", "#F5C400", "#0F1A24"), ("ink", "#E6EDF3", "#0D1117"), ("ink-muted", "#9AA7B4", "#0D1117"),
       ("bg", "#0D1117", "#E6EDF3"), ("surface", "#161B22", "#E6EDF3")]
for i, (n, h, t) in enumerate(row):
    swatch(20 + i * 160, 270, n, h, t)
row = [("success", "#3FB950", "#0D1117"), ("warning", "#F2B13A", "#0D1117"), ("error", "#F97066", "#0D1117"),
       ("hairline", "#2A323C", "#E6EDF3"), ("surface-2", "#1C232C", "#E6EDF3"), ("surface-3", "#242C36", "#E6EDF3")]
for i, (n, h, t) in enumerate(row):
    swatch(20 + i * 160, 344, n, h, t)

d.text("<b>Status chips</b> (icon + word + colour)", 20, 430, 500, 24)
chips = [("○ Submitted", "#F0F3F7", "#53606C", "#C7D0DA"), ("◷ Quoted", "#E6F4FB", "#006FA8", "#7FB8D8"),
         ("⚠ Awaiting agreement", "#FDF1E7", "#B54708", "#E8B48C"), ("✓ Accepted", "#E8F5EC", "#1A7F37", "#8CC9A0"),
         ("✓ Delivered", "#E8F5EC", "#1A7F37", "#8CC9A0"), ("✕ Cancelled", "#FDECEA", "#B42318", "#E8A39C"),
         ("♥ Pro Bono", "#F5C400", "#0F1A24", "#F5C400")]
x = 20
for label, bg, fg, br in chips:
    w = 70 + len(label) * 6
    d.node(f"<b>{label}</b>", x, 460, w, 28,
           f"rounded=1;arcSize={50 if 'Pro Bono' in label else 16};whiteSpace=wrap;html=1;fillColor={bg};strokeColor={br};fontColor={fg};"
           + FONT + "fontSize=12;")
    x += w + 12

d.text("<b>Type scale</b> (Inter; JetBrains Mono for ids)", 20, 520, 600, 24)
ty = [("Display 36/600", 36), ("H1 28/600", 28), ("H2 22/600", 22), ("H3 18/600", 18), ("Body 14/400", 14), ("Caption 12/400", 12)]
y = 550
for t, sz in ty:
    d.node(t, 20, y, 520, sz + 14, f"text;html=1;fontSize={sz};fontStyle={1 if sz >= 18 else 0};fontFamily=Inter, Helvetica;align=left;verticalAlign=middle;")
    y += sz + 18
d.node("ORD0b6b3ecc3b5d · BBD 1,250.00", 20, y, 520, 26, "text;html=1;fontSize=13;fontFamily=JetBrains Mono, Consolas, monospace;align=left;verticalAlign=middle;")

d.text("<b>Shape and spacing</b>", 640, 520, 400, 24)
for i, (lbl, r) in enumerate([("r-sm 4px · chips", 4), ("r-md 8px · buttons, inputs", 8), ("r-lg 12px · cards, dialogs", 12)]):
    d.node(lbl, 640, 556 + i * 62, 260, 48,
           f"rounded=1;absoluteArcSize=1;arcSize={r * 2};whiteSpace=wrap;html=1;fillColor=#161B22;strokeColor=#3A4552;fontColor=#E6EDF3;" + FONT)
d.node("<b>Primary</b>", 930, 556, 120, 40,
       "rounded=1;absoluteArcSize=1;arcSize=16;whiteSpace=wrap;html=1;fillColor=#006FA8;strokeColor=#006FA8;fontColor=#FFFFFF;" + FONT)
d.node("Secondary", 1070, 556, 120, 40,
       "rounded=1;absoluteArcSize=1;arcSize=16;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#C7D0DA;fontColor=#E6EDF3;" + FONT)
d.node("Danger", 1210, 556, 100, 40,
       "rounded=1;absoluteArcSize=1;arcSize=16;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#F97066;fontColor=#F97066;" + FONT)
d.node("Spacing: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64 px (base 4)", 930, 620, 380, 40, NOTE)
# exact colours: own dark background + light text; exported WITHOUT theme adaptation (see EXACT_COLOUR below)
d.cells = [c.replace('style="text;', 'style="fontColor=#E6EDF3;text;') for c in d.cells]
d.cells.insert(0, '<mxCell id="bg" value="" style="rounded=0;html=1;fillColor=#121212;strokeColor=none;" vertex="1" parent="1">'
                  '<mxGeometry x="0" y="0" width="1330" height="830" as="geometry"/></mxCell>')
d.save()
EXACT_COLOUR = ["28-design-tokens"]  # export these with --svg-theme light (no colour adaptation)

# =================================================================== 29 trust boundaries (Security)
d = Diagram("29-trust-boundaries", "Trust boundaries (TB1–TB8) and where controls sit")
TBS = "rounded=1;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;fillColor=none;strokeColor=#F97066;strokeWidth=2;verticalAlign=top;align=left;spacingLeft=8;fontStyle=1;fontColor=#F97066;" + FONT
d.node("Internet / CIMH LAN users", 20, 60, 260, 330, GROUP)
web = d.node("<b>SHOP / SIA browsers</b>", 50, 110, 200, 50, box("client"))
mob = d.node("<b>SIA Mobile</b><br>Keystore tokens", 50, 200, 200, 55, box("client"))
atk = d.node("Attacker / bots", 50, 300, 200, 50, box("bad"))
d.node("TB1 TLS · rate limits · headers", 310, 60, 220, 330, TBS)
ngx = d.node("<b>nginx</b><br>5 req/min auth · 20 req/s API<br>20 MB · CSP/HSTS", 330, 160, 180, 90, box("edge"))
d.node("TB2/TB3 app network · every request authenticated · service tokens", 560, 60, 330, 330, TBS)
svc = d.node("<b>Services</b><br>role + ownership checks<br>Pydantic forbid-extra<br>audit events", 600, 110, 250, 90, box("service"))
fil = d.node("<b>document-svc</b><br>magic bytes · ClamAV<br>X-Accel after permission check", 600, 240, 250, 80, box("service"))
d.node("TB4 data network (internal, no ports)", 920, 60, 300, 330, TBS)
db = d.node("<b>MongoDB</b> per-service users", 950, 100, 240, 50, cyl())
kf = d.node("<b>Kafka</b> SASL + topic ACLs", 950, 170, 240, 50, box("platform"))
rd = d.node("<b>Redis</b> ACL · revocations", 950, 240, 240, 50, cyl("platform"))
vol = d.node("<b>/srv/sia-data</b> protected files", 950, 310, 240, 50, cyl("platform"))
d.node("TB5 replication TLS + keyfile · firewall (3 IPs)", 920, 420, 300, 120, TBS)
pis = d.node("<b>Pi A / Pi B</b><br>LUKS-encrypted SSD", 960, 460, 220, 60, cyl())
d.node("TB6 encrypted backups", 1260, 420, 230, 120, TBS)
bak = d.node("<b>Other CIMH site</b><br>restic (append-only)", 1280, 460, 190, 60, cyl("external"))
d.node("TB7 CI/CD", 560, 420, 330, 120, TBS)
ci = d.node("<b>GitHub Actions</b><br>scans · approval gate · signed images", 600, 455, 250, 60, box("worker"))
for a_, b_, l_ in [(web, ngx, "HTTPS"), (mob, ngx, "HTTPS (TB8)"), (atk, ngx, "blocked / limited"), (ngx, svc, "/api/*"),
                   (svc, db, ""), (svc, kf, ""), (fil, vol, "")]:
    d.edge(a_, b_, l_)
d.edge(svc, rd, "", EDGE + "exitX=1;exitY=0.8;entryX=0;entryY=0.5;")
d.edge(db, pis, "replication", EDGE + "exitX=1;exitY=0.5;entryX=1;entryY=0.5;")
d.edge(pis, bak, "nightly")
d.edge(ci, svc, "deploy", EDGE_DASH + "exitX=0;exitY=0.5;entryX=0;entryY=0.75;")
d.save()

# =================================================================== 22 cut-over (Migration Plan)
flow("22-legacy-transition", "Legacy → v2: single data cut-over (Migration Plan §8)", {
    "dr": ("Dry runs DR-1 → DR-3<br>(staging, copies of 172.16.0.203)", 40, 110, "sys", 220, 60),
    "notify": ("Email all accounts<br>(T-5 d)", 310, 115, "email", 170, 50),
    "freeze": ("<b>Maintenance mode</b><br>stop Flask (no writes)", 530, 110, "staff", 200, 60),
    "dump": ("Final mongodump +<br>copy files (checksums)", 780, 110, "sys", 200, 60),
    "migrate": ("migrate --apply<br>M01–M09 → rs0", 1030, 110, "sys", 190, 60),
    "verify": ("migrate --verify<br>+ staff spot-check", 1030, 230, "sys", 190, 60),
    "go": ("Go?", 1060, 340, "dec"),
    "switch": ("Switch nginx: all /api/* +<br>new SHOP/SIA + mobile v2", 760, 355, "sys", 230, 60),
    "smoke": ("Smoke tests →<br>lift maintenance", 500, 355, "ok", 190, 60),
    "nogo": ("No-go: discard target,<br>restart Flask (no data lost)", 1260, 355, "bad", 220, 60),
    "keep": ("Legacy read-only 30 days<br>rollback ≤ 48 h, then archive", 240, 355, "email", 220, 60),
}, [
    ("dr", "notify", ""), ("notify", "freeze", "T-0"), ("freeze", "dump", ""), ("dump", "migrate", ""),
    ("migrate", "verify", ""), ("verify", "go", ""), ("go", "switch", "yes"), ("go", "nogo", "no"),
    ("switch", "smoke", ""), ("smoke", "keep", ""),
])

# =================================================================== 30 test pipeline (Test Strategy)
flow("30-test-pipeline", "Test levels and CI gates", {
    "pr": ("<b>Pull request</b>", 40, 110, "staff", 150, 50),
    "fast": ("Lint · types · <b>unit</b><br>integration (testcontainers)<br>contract · <b>authz/IDOR</b> · component", 230, 95, "sys", 240, 80),
    "scan": ("SAST · deps · secrets<br>a11y (components)", 510, 105, "sys", 190, 60),
    "g1": ("All green +<br>coverage?", 740, 95, "dec", 140, 80),
    "fix": ("Fix", 760, 230, "bad", 100, 44),
    "main": ("<b>Merge to main</b><br>build · Trivy · cosign", 920, 105, "staff", 200, 60),
    "stg": ("Deploy <b>staging</b><br>E2E smoke J-01/02/03/09", 1160, 105, "sys", 210, 60),
    "night": ("<b>Nightly</b>: full E2E (3 browsers)<br>Android instrumented · ZAP", 1260, 230, "email", 230, 60),
    "rc": ("<b>Release candidate</b><br>regression · k6 · resilience<br>manual a11y · UAT", 900, 340, "sys", 230, 75),
    "g2": ("0 S1/S2 +<br>targets met?", 640, 335, "dec", 140, 85),
    "prod": ("<b>Production</b> (approval)<br>health + smoke, auto-rollback", 360, 345, "ok", 230, 65),
}, [
    ("pr", "fast", ""), ("fast", "scan", ""), ("scan", "g1", ""), ("g1", "main", "yes"), ("g1", "fix", "no"),
    ("fix", "pr", "", "exitX=0;exitY=0.5;entryX=0.5;entryY=1;"),
    ("main", "stg", ""), ("stg", "night", "", "dashed=1;exitX=0.8;exitY=1;entryX=0.3;entryY=0;"), ("stg", "rc", "", "exitX=0.2;exitY=1;entryX=1;entryY=0.5;"),
    ("rc", "g2", ""), ("g2", "prod", "yes"), ("g2", "fix", "no"),
])

# =================================================================== 31 implementation timeline (Gantt)
d = Diagram("31-implementation-timeline", "Implementation timeline (weeks from start, estimate for 1 developer + Claude Code)")
WK, X0, Y0, ROW = 27, 260, 80, 40
phases = [("P0 Legacy security fixes", 1, 2, "bad"), ("P1 Foundations", 3, 7, "platform"),
          ("P2 Identity and access", 8, 11, "service"), ("P3 Catalogue and media", 12, 14, "service"),
          ("P4 Inventory and warehouse", 15, 17, "service"), ("P5 Orders, quotes, agreements", 18, 23, "service"),
          ("P6 Documents and notifications", 24, 26, "service"), ("P7 Web frontends complete", 27, 30, "client"),
          ("P8 Mobile on v2 API", 31, 34, "client"), ("P9 Hardening, pen test, migration DR, UAT", 35, 39, "worker"),
          ("P10 Cut-over (+30 d hypercare)", 40, 40, "final")]
for w in range(1, 41):
    d.node(str(w) if w % 2 == 0 or w == 1 else "", X0 + (w - 1) * WK, Y0 - 30, WK, 22, "text;html=1;align=center;fontSize=10;fontColor=#9AA7B4;")
    d.cells.insert(0, f'<mxCell id="grid{w}" style="endArrow=none;html=1;strokeColor=#2A323C;" edge="1" parent="1">'
                      f'<mxGeometry relative="1" as="geometry"><mxPoint x="{X0 + (w - 1) * WK}" y="{Y0 - 6}" as="sourcePoint"/>'
                      f'<mxPoint x="{X0 + (w - 1) * WK}" y="{Y0 + ROW * len(phases)}" as="targetPoint"/></mxGeometry></mxCell>')
for i, (name, s_, e_, kind) in enumerate(phases):
    y = Y0 + i * ROW
    d.node(name, 20, y + 4, 232, 28, "text;html=1;align=right;verticalAlign=middle;fontSize=12;spacingRight=8;")
    d.node("", X0 + (s_ - 1) * WK + 2, y + 6, (e_ - s_ + 1) * WK - 4, 24, box(kind, "arcSize=30;"))
ms = [("MS1", 2), ("MS2", 7), ("MS3", 11), ("MS4", 17), ("MS5", 26), ("MS6", 34), ("MS7", 39), ("MS8", 40)]
ym = Y0 + ROW * len(phases) + 14
for lbl, w in ms:
    d.node("", X0 + w * WK - WK / 2 - 12, ym, 24, 24, "rhombus;html=1;fillColor=#F5C400;strokeColor=#F5C400;")
    d.node(lbl, X0 + w * WK - WK / 2 - 22, ym + 26, 44, 18, "text;html=1;align=center;fontSize=10;")
d.node("Milestones: MS1 legacy secured · MS2 platform ready · MS3 accounts · MS4 catalogue+inventory · MS5 request lifecycle · "
       "MS6 feature complete · MS7 go decision · MS8 live (MS9 legacy retired at +30 d)", 20, ym + 56, 1300, 30, NOTE)
d.save()

print("generated", len(list(OUT.glob("*.drawio"))), "diagrams")
