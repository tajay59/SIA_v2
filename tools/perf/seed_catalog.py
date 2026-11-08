"""Bulk-seed synthetic catalogue products for performance checks (TEST_STRATEGY §6, IMPLEMENTATION_PLAN P3 exit).

    python tools/perf/seed_catalog.py --mongo mongodb://mongo:27017/?replicaSet=rs0 --products 200000
    python tools/perf/seed_catalog.py --mongo ... --cleanup      # remove every perf product again

Products look like real stores items (make + instrument + model) so that text search terms hit realistic
match counts: a make matches ~1/30 of the catalogue, an instrument word ~1/50, a model number a handful.
Every document carries `seedTag: "perf"` so `--cleanup` removes exactly what this script added.
Synthetic data only; refuses non-local hosts unless --force (never production).
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

DB = "inventory"
TAG = "perf"
SAFE_HOSTS = {"localhost", "127.0.0.1", "mongo", "host.docker.internal"}
NUMBER_BASE = 5_000_000  # far above the legacy counter, so seeded numbers never clash

MAKES = [
    "Vaisala", "Campbell", "Davis", "Gill", "Lufft", "OTT", "Thies", "Kipp", "Hach", "Sutron",
    "Young", "Apogee", "Hukseflux", "Delta-T", "Onset", "Texas Electronics", "Met One", "Biral",
    "Stevens", "Geonor", "Seba", "Pessl", "Eltek", "Licor", "Teledyne", "Belfort", "Sontay",
    "Friedrichs", "Selex", "Baron",
]  # fmt: skip
ITEMS: dict[str, list[str]] = {
    "MET": [
        "anemometer", "wind vane", "barometer", "rain gauge", "tipping bucket", "pyranometer", "hygrometer",
        "thermometer", "data logger", "radiation shield", "ceilometer", "disdrometer", "evaporation pan",
        "soil moisture probe", "present weather sensor", "visibility sensor", "weather station",
    ],
    "RAD": ["magnetron", "waveguide", "klystron", "radome panel", "pedestal motor", "receiver module", "rotary joint"],
    "EQUIP": [
        "mast", "tripod", "solar panel", "battery", "charge controller", "modem", "enclosure", "ups",
        "laptop", "gps receiver", "satellite transmitter", "multimeter",
    ],
    "SUPP": ["cable", "connector", "mounting bracket", "fuse", "desiccant pack", "cable tie", "sealant"],
    "MISC": ["toolkit", "safety harness", "printer toner", "manual", "tarpaulin"],
    "PRO": ["training kit", "starter rain gauge", "school weather kit", "thermometer set"],
}  # fmt: skip
TYPE_WEIGHTS = {"MET": 40, "RAD": 10, "EQUIP": 20, "SUPP": 15, "MISC": 10, "PRO": 5}
DEPARTMENTS = ["Meteorology", "Radar", "Climate", "Hydrology", "IT"]
PROJECTS = [None, None, None, "CREWS", "WISER", "CariCOF"]
FILLER = [
    "Supplied", "with", "mounting", "hardware", "and", "calibration", "certificate.", "Suitable", "for",
    "automatic", "weather", "stations", "in", "tropical", "marine", "climates.", "Spare", "parts", "on", "request.",
]  # fmt: skip


def product(rng: random.Random, i: int, base: datetime) -> dict[str, Any]:
    ptype = rng.choices(list(TYPE_WEIGHTS), weights=list(TYPE_WEIGHTS.values()))[0]
    make = rng.choice(MAKES)
    item = rng.choice(ITEMS[ptype])
    model = f"{make[:3].upper()}{rng.randint(100, 9999)}"
    probono = ptype == "PRO" or rng.random() < 0.02
    sellable = probono or rng.random() < 0.6
    stamp = base + timedelta(seconds=i)
    doc: dict[str, Any] = {
        "id": f"{ptype}{rng.getrandbits(128):032x}",
        "number": NUMBER_BASE + i,
        "name": f"{make} {item} {model}",
        "description": " ".join(rng.sample(FILLER, k=rng.randint(8, len(FILLER)))),
        "make": make,
        "modelname": item.title(),
        "modelnumber": f"{model}-{rng.randint(1, 99):02d}",
        "type": ptype,
        "department": rng.choice(DEPARTMENTS),
        "project": rng.choice(PROJECTS),
        "sellable": sellable,
        "probono": probono,
        "probonoMaxPerRequest": rng.choice([None, 2, 5]) if probono else None,
        "cost": f"{rng.randint(5, 25000)}.{rng.randint(0, 99):02d}",
        "threshold": rng.randint(0, 10),
        "unitquantity": 1,
        "keywords": [ptype.lower(), *item.split()],
        "images": [],
        "inStock": rng.random() < 0.7,
        "active": rng.random() < 0.97,
        "createdAt": stamp,
        "updatedAt": stamp,
        "version": 1,
        "outbox": [],
        "seedTag": TAG,
    }
    if rng.random() < 0.3:  # staff serial search (sparse fields)
        doc["sn"] = f"SN{rng.getrandbits(40):010X}"
    return doc


def generate(seed: int, n: int) -> Iterator[dict[str, Any]]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not security
    base = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(1, n + 1):
        yield product(rng, i, base)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://localhost:27017/?directConnection=true")
    ap.add_argument("--products", type=int, default=200_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--batch", type=int, default=5_000)
    ap.add_argument("--cleanup", action="store_true", help="delete every product with seedTag=perf, then exit")
    ap.add_argument("--force", action="store_true", help="allow a non-local host (disposable test DB only)")
    args = ap.parse_args(argv)

    host = urlparse(args.mongo).hostname or ""
    if host not in SAFE_HOSTS and not args.force:
        print(f"refusing non-local host {host!r} (use --force for a disposable test DB)", file=sys.stderr)
        return 2

    from pymongo import MongoClient

    coll = MongoClient(args.mongo, serverSelectionTimeoutMS=5000)[DB]["product"]
    if args.cleanup:
        print("deleted", coll.delete_many({"seedTag": TAG}).deleted_count, "perf products")
        return 0
    if coll.count_documents({"seedTag": TAG}, limit=1):
        print("perf products already present; run --cleanup first", file=sys.stderr)
        return 1

    batch: list[dict[str, Any]] = []
    done = 0
    for doc in generate(args.seed, args.products):
        batch.append(doc)
        if len(batch) == args.batch:
            coll.insert_many(batch, ordered=False)
            done += len(batch)
            batch = []
            print(f"\r{done}/{args.products}", end="", flush=True)
    if batch:
        coll.insert_many(batch, ordered=False)
        done += len(batch)
    print(f"\rseeded {done} perf products; product now has {coll.estimated_document_count()} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
