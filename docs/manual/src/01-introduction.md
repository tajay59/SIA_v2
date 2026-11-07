# 1. Introduction

[← Manual home](README.md) · [Next: Users, roles and apps →](02-users-roles-apps.md)

## 1.1 What the platform is

The CIMH Stores Platform lets **member-state meteorological and hydrological organisations** request instruments, spares and supplies from CIMH, and lets **CIMH staff** manage the stock, source items from suppliers and fulfil requests.

| App | Address / form | Used by | Purpose |
|---|---|---|---|
| **SHOP** | `store.cimh.edu.bb` (web) | Customers (member-state staff) | Browse the catalogue (no prices), request items, review and accept quotes, track requests |
| **SIA** | `sia.cimh.edu.bb` (web) | CIMH staff and admins | Products, inventory, request desk (quotes, purchasing, shipping), account approvals, settings |
| **SIA Mobile** | Android 11+ app | Warehouse staff | Scan shelves and units: lookup, stow, pick, pick for requests, shipping |

## 1.2 How ordering works (no online payment)

There is **no checkout or payment**. Customers submit **order requests**:

- **Paid items:** staff collect quotes from suppliers and send them to the customer. If CIMH already holds the **full requested quantity** of an item, the customer also gets a **CIMH stock quote** (catalogue cost plus admin fee) and chooses, item by item, CIMH stock or supplier. The customer accepts (committing to pay) or declines. After acceptance, staff purchase, ship and deliver.
- **Pro Bono items:** free items supplied from CIMH stock. There is no quote step: staff approve, pick, ship and deliver. Staff can limit the quantity of each Pro Bono item per request.
- Quotes are in **BBD or USD** (one currency per request, never both) and are valid for **30 days**.
- Carriers are **FedEx, DHL or hand delivery**. Staff enter the tracking number by hand; there is no carrier integration.

The full flows are in [Chapter 5](05-workflows.md).

## 1.3 Goals

| Goal | Target |
|---|---|
| Scale | Up to **1,000,000 registered users** · about 20,000 concurrent · 1,000 requests/s at peak |
| Speed | p95 < 300 ms for reads, < 500 ms for writes |
| Availability | 99.5% per month |
| Recovery | Lose at most 24 h of data (RPO); restore within 4 h (RTO) |
| Security | Zero critical findings at the pre-launch security review |
| Account control | Every new non-CIMH account approved by an admin before first login |
| Stock accuracy | No unit ever sold or reserved twice |

## 1.4 Why v2

The current system (Flask API + two Vue apps) works but:
- had **critical security flaws**: code injection through `eval`, routes with no login check, and users able to read other users' data by changing an id in the request;
- **couldn't scale**: it opened a new database connection for every query, kept login tokens in SQLite, and stored files on one machine;
- modelled orders as "buy now", which isn't how CIMH sources items;
- let anyone with a verified email use the store.

v2 is a rebuild using **microservices**, Kafka and a MongoDB replica set, **keeping the existing data** (reference database `inventory` on `172.16.0.203`: 83 products, 697 storage units, 39 orders, 65 accounts).

## 1.5 Key numbers at a glance

| Item | Value |
|---|---|
| Roles | `admin`, `staff`, `user` |
| Services | 6 microservices + media worker |
| Database | MongoDB replica set (1 host + 2 Raspberry Pi 5), database `inventory` |
| Messaging | Kafka, 3 brokers, 7 topic families |
| Hardware | Main host: 16 cores, 32 GB RAM, 2 × 6 GB GPU |
| Deployment | Docker Compose only |
| Quote validity | 30 days |
| Currencies | BBD, USD |
| Minimum Android | 11 |

## 1.6 Source documents

| Document | Covers |
|---|---|
| [PRD](../PRD.md) | What the product does, feature by feature (requirement IDs such as A3, O5a) |
| [TRD](../TRD.md) | Tools, versions, numeric technical requirements (IDs such as TR-AUTH-1) |
| [TAD](../TAD.md) | How the system is built and why (services, events, workflows, ADRs) |
| [BSD](../BSD.md) | Where data lives, field-level schemas, indexes, access, retention |
| [Documentation Index](../DOCUMENTATION_INDEX.md) | Every project document, before, during and after the build |
