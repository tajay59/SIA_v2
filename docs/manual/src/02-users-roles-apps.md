# 2. Users, roles and apps

[← Introduction](01-introduction.md) · [Manual home](README.md) · [Next: Architecture →](03-architecture.md)

## 2.1 Roles

The platform has exactly three roles. One account has one role.

| Role | Who | Apps | Can see requests | Can change |
|---|---|---|---|---|
| `user` (member organisation) | Staff of member-state organisations, approved by an admin | SHOP | Their own **and** their organisation's | Own cart; own requests (accept, decline, cancel) |
| `user` (`@cimh.edu.bb`) | CIMH email addresses; **skip admin approval** | SHOP (browse only) | None | **Cannot** add to cart or submit requests |
| `staff` | CIMH stores and procurement staff | SHOP (browse), SIA, Mobile | All | Products, stock, request processing, quotes, purchasing, shipping |
| `admin` | System administrators | All | All | Everything + account approvals, organisations, roles, settings, audit log |

Notes:
- `@cimh.edu.bb` accounts become active as soon as their email is verified. An admin then gives them `staff` or `admin` if they need SIA.
- Only the person who submitted a request (or an admin) can accept, decline or cancel it, even though colleagues in the same organisation can see it.
- Every approval, role change, suspension and status change is recorded in the **audit log**.

## 2.2 Account life cycle

![Account status flow](images/10-account-status.svg)

| Status | Meaning | Can log in? |
|---|---|---|
| `PENDING_VERIFICATION` | Registered; waiting for the 6-digit email code (valid 15 min) | No |
| `PENDING_APPROVAL` | Email verified; waiting for an admin | No ("awaiting approval" page) |
| `ACTIVE` | Approved (or `@cimh.edu.bb`) | **Yes** |
| `REJECTED` | Denied by an admin, with a reason | No |
| `EXPIRED` | Not verified within 24 h | No |
| `SUSPENDED` | Suspended by an admin; all sessions revoked immediately | No |

When approving, the admin links the account to an **organisation** (picking an existing one or creating a new one), because users type their organisation's name in free text. Rejected and expired accounts are deleted after 90 days.

## 2.3 SHOP (customer store)

![SHOP navigation map](images/19-shop-sitemap.svg)

| Area | Features |
|---|---|
| Home | Featured met and radar products; first-visit tour |
| Catalogue | Browse by type (met, radar, equipment, supplies, misc, projects) and department; search by name, make, model, serial, keyword; product detail with images, specs and **availability** (in stock / on request). **No prices.** |
| Pro Bono items | Separate section of free items; maximum quantity per request shown on each item |
| Cart | Saved across devices; choose **BBD or USD**; submit. A cart with both paid and Pro Bono items becomes **two requests** |
| My requests | Own and organisation requests; filter by status, year and requester; timeline; quotes (supplier + CIMH option); choose per item; accept/decline; documents; carrier + tracking link |
| Account | Sign up → verify → awaiting approval → login; password reset; profile, saved addresses |

## 2.4 SIA (staff web app)

![SIA navigation map](images/20-sia-sitemap.svg)

| Area | Features |
|---|---|
| Request desk | Queue filtered by status, year, customer, organisation and ID, showing how long each request has been waiting. Request detail: start quoting (automatic stock check), upload supplier quotes, CIMH option (exchange rate for USD), send quote, purchase orders, ship (carrier + tracking), deliver, cancel |
| Catalogue | Create and edit products (cost visible to staff only), images with automatic background removal, sellable and Pro Bono flags, Pro Bono per-item limits |
| Inventory | Sites, locations, shelves (QR codes); stow, pick, relocate, self-assign; lookup; batch unit labels (PDF/CSV) |
| Reports | Stock levels and low-stock alerts; who has what; movement history |
| Admin | Pending accounts (approve/deny in bulk), users and roles, suspend/reactivate, organisations (merge duplicates), email lists, admin fee, departments/types/projects, audit log |

## 2.5 SIA Mobile (Android)

![SIA Mobile navigation map](images/21-mobile-sitemap.svg)

| Area | Features |
|---|---|
| Login | Staff only; tokens kept in Android Keystore-encrypted storage |
| Lookup | Scan a shelf or product; paged results; product detail with locations |
| Stow / Pick | Scan shelf → scan units; pick with a reason |
| Orders | Approved requests; pick by scanning (units must be reserved for that request); record carrier + tracking |
| Create | Products (with photos), locations |
| Offline | Scans are queued (Room + WorkManager) and synced later. A per-scan idempotency key prevents duplicates |

Minimum **Android 11 (API 30)**. Scanning uses CameraX + ML Kit.
