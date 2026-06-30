# Bulk Operations Automation

[![Odoo](https://img.shields.io/badge/Odoo-18.0-714b67?logo=odoo)](https://www.odoo.com)
[![License](https://img.shields.io/badge/license-LGPL--3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-18.0.1.0.0-green)](__manifest__.py)

Upload a daily CSV or XLSX of customer sales data and, in one click, generate Sales Orders, Deliveries, Returns, Invoices, and consolidated Purchase Orders — all in the background, with live progress tracking.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture & Design Decisions](#architecture--design-decisions)
  - [Why Background Processing](#why-background-processing)
  - [Chunked Processing & Periodic Commits](#chunked-processing--periodic-commits)
  - [Error Isolation via Savepoints](#error-isolation-via-savepoints)
  - [Pre-fetched Resources](#pre-fetched-resources)
- [Complete Processing Flow](#complete-processing-flow)
  - [Step 1: Import](#step-1-import)
  - [Step 2: Validation](#step-2-validation)
  - [Step 3: Grouping](#step-3-grouping)
  - [Step 4: Batch Processing](#step-4-batch-processing)
- [Documents Generated Per Group](#documents-generated-per-group)
  - [Sales Orders](#sales-orders)
  - [Deliveries](#deliveries)
  - [Returns](#returns)
  - [Invoices & Payments](#invoices--payments)
  - [Purchase Orders](#purchase-orders)
- [Stock & Inventory Behavior](#stock--inventory-behavior)
  - [Delivery Stock Flow](#delivery-stock-flow)
  - [Return Stock Flow](#return-stock-flow)
  - [Location Accuracy Caveat](#location-accuracy-caveat)
  - [Fallback to Main Warehouse](#fallback-to-main-warehouse)
- [Error Scenarios & Recovery](#error-scenarios--recovery)
  - [Server Crash Mid-Processing](#server-crash-mid-processing)
  - [Partial Group Failure](#partial-group-failure)
  - [Invalid Data in a Row](#invalid-data-in-a-row)
  - [Timeout Prevention](#timeout-prevention)
- [File Format](#file-format)
  - [Quick Import — Column Mapping](#quick-import--column-mapping)
  - [Standard Import Wizard](#standard-import-wizard)
- [How Resolution Works](#how-resolution-works)
  - [Customer Resolution](#customer-resolution)
  - [Product Resolution](#product-resolution)
  - [Location Resolution](#location-resolution)
- [Import Modes](#import-modes)
- [Progress Tracking](#progress-tracking)
- [Weekend Handling](#weekend-handling)
- [Dependencies](#dependencies)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Stock Locations](#stock-locations)
  - [Default Supplier](#default-supplier)
- [Performance Characteristics](#performance-characteristics)
- [Development & Testing](#development--testing)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

This module automates the end-to-end order-to-cash cycle for businesses that distribute products to customers from route-based stock locations on a daily schedule.

**What it does at a glance:**

| Step | What happens |
|---|---|
| **Import** | Parse a CSV/XLSX with customer, product, quantity, and returns data |
| **Resolve** | Batch-match each row to Odoo Partners, Products, and Locations (N+1-safe) |
| **Background process** | Runs asynchronously to avoid HTTP timeouts; progress visible on the form |
| **Sales Order** | One SO per customer per effective date, with all products as order lines |
| **Delivery** | Confirmed stock moves from the route's internal location |
| **Returns** | Same-day incoming pickings, crediting stock back to the route |
| **Invoice** | Posted, fully-paid invoice per SO |
| **Purchase Order** | Consolidated PO per supplier for net quantities sold |

---

## Quick Start

1. **Create a Batch** — *Bulk Operations → Batches → New*
2. **Select mode** — choose **Quick Import** (predefined column map) or **Standard Import** (custom mapping)
3. **Upload file** — attach a CSV or XLSX via the *Import File* field
4. **Click Import File** — rows are parsed, matched, and staged as reviewable lines
5. **Review** — click *View Imported Data* to check matches; fix mismatches inline
6. **Click Batch Process** — processing starts in the background; refresh the page to see progress
7. **Wait for completion** — the progress bar reaches 100%, state changes to "Processed"

---

## Architecture & Design Decisions

### Why Background Processing

The original implementation ran all processing inside the Odoo HTTP request handler. For large files (>500 rows) this consistently hit the default 120-second request timeout, triggering a server reload and `cursor already closed` errors.

**Decision:** Processing now runs in a **daemon background thread** with its own database cursor and environment. The HTTP request returns immediately with a notification; the actual work happens outside the request/response cycle. This eliminates the timeout ceiling entirely.

```python
# action_batch_process() returns instantly
threading.Thread(target=self._process_in_background, ...).start()
return notification_to_user()

# Heavy work runs in a separate cursor
with odoo.sql_db.db_connect(db_name).cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    batch = env['bulk.operation.batch'].browse(batch_id)
    batch._execute_batch_process()
    cr.commit()
```

### Chunked Processing & Periodic Commits

Within the background thread, groups are processed in **chunks of 15** (configurable via `chunk_size`). After each chunk:

1. Progress percentage and status text are written to the batch record
2. `cr.commit()` persists all work done so far — including SOs, deliveries, invoices, payments, and line statuses
3. The loop continues with the next chunk

**Why this matters:**
- If the server crashes mid-way, only the current uncommitted chunk is lost. Previous chunks are permanently saved.
- Re-clicking "Batch Process" after a crash skips already-processed lines (`is_processed = True`) and resumes from where processing stopped.
- The user can refresh the form and see live progress (progress bar + "Processed 45/120 groups").

```python
for idx, (eff_date, partner, lines) in enumerate(groups, start=1):
    with self.env.cr.savepoint():
        # ... create SO, deliver, invoice, pay ...
        lines.write({'is_processed': True})

    if idx % chunk_size == 0 or idx == total:
        self.write({'processing_progress': progress, 'processing_status': status})
        self.env.cr.commit()  # Persist everything so far
```

### Error Isolation via Savepoints

Each customer-date group runs inside its own **SQL savepoint** (`self.env.cr.savepoint()`). If a single group fails (e.g., missing stock, accounting error):

- That group's changes are rolled back to the savepoint
- The line is marked with an error message (written outside the savepoint, in the current transaction)
- All other groups continue unaffected

This means a single bad row never blocks an entire batch of thousands.

### Pre-fetched Resources

The following shared resources are fetched **once** before the processing loop, rather than once per group:

- **Warehouse** (used by every SO) — fetched via `_get_warehouse()`
- **Payment journal** and **payment method** (used by every invoice) — fetched via `_get_payment_journal()`

This eliminates hundreds or thousands of redundant SQL queries for large imports.

---

## Complete Processing Flow

### Step 1: Import

User uploads a CSV/XLSX file on the batch form. `action_import_file()`:

1. Decodes the file (auto-detects CSV vs XLSX, handles UTF-8/Windows encodings)
2. Collects all unique edition codes, customer identifiers, and branch names
3. **Batch-resolves** all partners, products, and locations using `IN` queries (not N×5 individual searches)
4. Creates `bulk.operation.line` records — one per CSV row — with resolved foreign keys and any error messages

**Key detail:** Lines with unresolvable partners/products/locations are still imported with an error flag. The user can fix them inline in the list view before processing.

### Step 2: Validation

When "Batch Process" is clicked, `_execute_batch_process()` re-validates every line:

| Condition | Result |
|---|---|
| Missing partner | Line flagged with error, skipped |
| Missing product | Line flagged with error, skipped |
| Missing location | Line flagged with error, skipped |
| `returned > delivered` | Line flagged with error, skipped |
| All valid | Line proceeds to grouping |

This re-validation catches manual fixes the user may have made in the list view since import.

### Step 3: Grouping

Valid lines are grouped by **(effective date, partner)**:

- `effective_date` = delivery date, with Saturday/Sunday rolled to Monday
- All lines for the same customer on the same date form one group
- Each group will produce exactly one Sales Order

This ensures a customer never receives multiple SOs for the same day. All their products are consolidated into a single order with multiple order lines.

### Step 4: Batch Processing

Groups are processed in **chunks of 15**. For each group:

1. **Create Sales Order** — one SO with all products as order lines
2. **Confirm SO** — Odoo creates draft pickings
3. **Validate delivery** — stock moves from the route location; falls back to main warehouse if insufficient
4. **Process returns** — incoming pickings for returned quantities
5. **Create & post invoice** — one invoice per SO
6. **Register payment** — fully pays the invoice

After all groups are processed:

7. **Create consolidated Purchase Orders** — one PO per supplier based on net demand
8. **Link everything** — SOs, invoices, and POs are attached to the batch
9. **State changes** to "Processed"
10. **Summary posted** to the chatter

---

## Documents Generated Per Group

### Sales Orders

```
Customer: Alice
Date:     2026-06-22
SO-001:
  Line 1: Newspaper A × 30  @ 50.00
  Line 2: Magazine B  × 20  @ 75.00
```

- **One SO per customer per effective date** — all products are order lines within that single SO
- Automatically **confirmed** after creation (transitions to `sale` state)
- Origin field links back to the batch reference

### Deliveries

- Stock moves originate from the **route/branch location** specified in the CSV
- If the route location has insufficient stock, the system falls back to the **main warehouse stock location** (`wh.lot_stock_id`)
- All moves are force-validated (`move.quantity = move.product_uom_qty`, then `button_validate()` with `skip_backorder=True`)
- If validation still fails (e.g., zero stock everywhere), the group is flagged with an error and skipped

### Returns

- Returns are **incoming pickings** — stock flows back from the customer's delivery address to the route/branch location
- Created only for lines where `returned > 0` in the CSV
- Validated immediately (same forced-validation pattern as deliveries)
- Returns **increase** inventory at the route location

### Invoices & Payments

- One **posted invoice** per Sales Order (via `sale_order._create_invoices()`)
- Automatically **paid** via the configured cash or bank journal
- If no suitable journal is found, the invoice is left unpaid and a warning is posted in the chatter

### Purchase Orders

- **One consolidated PO per supplier** for net quantities sold across all customers
- Net quantity for purchasing = `delivered - returned` (only counted when positive)
- Products are grouped by their configured vendor (`product.seller_ids`)
- Products without a configured vendor fall back to the **default supplier** (configurable via system parameter `bulk_operations.default_supplier`)
- If net demand is zero for all products (everything returned), no PO is created

---

## Stock & Inventory Behavior

### Delivery Stock Flow

```
Route Location (source) → Customer (destination)
        ↓
   Stock decreases at the route location
```

Stock is consumed from the route/branch location specified in the CSV's `bulkname` column. This is an **internal** stock location (not a customer location).

### Return Stock Flow

```
Customer (source) → Route Location (destination)
        ↓
   Stock increases at the route location
```

Returns credit stock **back to the same route location** that was used for delivery. The source is the customer's delivery address.

### Location Accuracy Caveat

If the delivery used the **fallback warehouse** (because the route location had insufficient stock), but the return credits back to the route location, inventory can shift between locations over time:

| Operation | Location | Effect |
|---|---|---|
| Deliver 30 units | Main warehouse stock | -30 at warehouse |
| Return 5 units | Route location | +5 at route |

The route location gains 5 units it never actually lost. Whether this matters depends on whether you track per-location accuracy. If you need precise reconciliation, ensure each route location has sufficient stock to cover its deliveries so the fallback is never triggered.

### Fallback to Main Warehouse

When a route location has insufficient stock to fulfill a delivery, the system:

1. Detects moves with `product_uom_qty > 0` but zero reserved quantity
2. Switches the picking's source location to `wh.lot_stock_id` (the main warehouse stock location)
3. Re-assigns and validates from there

This is a pragmatic trade-off: the delivery goes through even if the route is understocked, at the cost of location accuracy.

---

## Error Scenarios & Recovery

### Server Crash Mid-Processing

| Scenario | What happens | Recovery |
|---|---|---|
| Crash during chunk N | Chunks 1 through N-1 are already committed. Chunk N is lost (rolled back). | Re-click "Batch Process" — already-processed lines (`is_processed = True`) are skipped, unprocessed lines resume. |
| Crash during final purchase order creation | All groups are processed and committed. Only the PO creation + state change is lost. | Re-click "Batch Process" — all lines are already processed, so it skips to PO creation and finalization. |

### Partial Group Failure

One customer-date group fails (e.g., accounting error during invoice posting). The savepoint catches it:

- The failed group's SO, delivery, invoice, etc. are rolled back
- The line is marked with `error_message` containing the exception text
- Other groups continue processing normally
- The failure is listed in the final summary posted to the chatter

### Invalid Data in a Row

| Input | Handling |
|---|---|
| Empty delivery date | Row skipped during import, not imported |
| Unparseable date | Row skipped during import |
| Non-numeric quantity | Row skipped during import |
| Negative returns | `abs()` is applied, so `-5` becomes `5` |
| Returns > delivered | Line flagged as invalid during validation, not processed |
| Missing partner/product/location | Line imported with error, not processed until fixed |

### Timeout Prevention

Processing runs in a **background thread** with an independent database cursor. The HTTP request returns immediately (within milliseconds). The 120-second Odoo worker timeout no longer applies.

---

## File Format

### Quick Import — Column Mapping

| CSV Header | Maps To | Description | Required |
|---|---|---|---|
| `distributorid` | distributor_id | Distributor / route identifier | No |
| `customerid` | customer_code | Customer `ref` in Odoo | Preferred |
| `name1` | customer_name | Customer name (fallback) | If no code |
| `customergroup` | customer_group | Customer group label | No |
| `bulkname` | branch_name | Stock location name | Recommended |
| `edition` | edition | Product code (`default_code`, `name`, or `barcode`) | Yes |
| `deliverydate` | date | Delivery date (any common format) | Yes |
| `delivered` | delivered | Quantity delivered | Yes |
| `returns` | returned | Quantity returned (can be negative) | Yes |

**Custom headers?** Edit the `COLUMN_MAP` dict in `models/bulk_operation_batch.py` — nothing else in the import logic needs to change.

### Standard Import Wizard

Use this mode when your file has different column names, multiple sheets, or you want to choose which columns to import. The wizard:

1. Auto-detects headers and data types
2. Pre-populates column-to-field mappings (editable)
3. Shows sample values for each column
4. Supports multi-sheet XLSX files
5. Supports CSV separator selection

---

## How Resolution Works

### Customer Resolution

Each CSV row is matched to an Odoo `res.partner` using this priority:

1. `ref` — exact match on `customerid`
2. `name` — exact match on `name1`
3. `name` — case-insensitive match (`=ilike`)

For large imports, all unique customer codes are resolved in **batched queries** (`('ref', 'in', [...])`), then names.

### Product Resolution

Each `edition` value is searched in priority order:

1. `default_code` — exact match (batched via `IN` query)
2. `default_code` — case-insensitive (`=ilike`)
3. `name` — exact match
4. `name` — case-insensitive (`=ilike`)
5. `barcode` — exact match

For large imports, unique editions are resolved in **one batched query** for step 1, then individual fallback searches for only the unmatched editions.

### Location Resolution

Each branch/route is resolved from the `bulkname` column:

1. Search `stock.location` by **name** (case-insensitive, `usage='internal'`)
2. If not found, search by **complete_name** (e.g., `WH/Chogoria`)
3. If still not found, the line is flagged with an error for manual fixing

---

## Import Modes

| Feature | Quick Import | Standard Import |
|---|---|---|
| Column mapping | Predefined (`COLUMN_MAP`) | User-defined per import |
| Multi-sheet XLSX | First sheet only | All sheets, user selects |
| CSV separator | Auto-detect | User selects (comma/semicolon/tab) |
| Sample preview | No | Yes |
| Best for | Daily exports with stable format | One-off files with varying formats |

---

## Progress Tracking

Two fields on the batch form track background processing:

| Field | Widget | Shows |
|---|---|---|
| `processing_progress` | Progress bar (0–100%) | How far through the groups we are |
| `processing_status` | Text | Current step: "Starting...", "Processed 45/120 groups", "Creating purchase orders...", "Completed" |

**How to view progress:** Refresh the batch form page during processing. The progress bar updates after every chunk commit (every 15 groups).

**When processing completes:**
- Progress bar reaches 100%
- Status reads "Completed"
- Batch state changes from "Imported" to "Processed"
- A summary message is posted in the chatter (success count, failure count, and individual failure messages)

---

## Weekend Handling

Saturday and Sunday delivery dates are automatically rolled to the following Monday:

| Original Date | Effective Date |
|---|---|
| Monday–Friday | Same day |
| Saturday | Following Monday |
| Sunday | Following Monday |

This ensures that weekend deliveries are grouped into Monday's Sales Orders rather than creating separate weekend orders.

---

## Dependencies

| Module | Purpose |
|---|---|
| `sale_management` | Sales Order creation and management |
| `purchase` | Purchase Order creation |
| `stock` | Stock moves, deliveries, returns, locations |
| `account` | Invoicing and payment registration |

---

## Installation

1. Place the `mobipine_odoo_bulk_operations` directory in your Odoo addons path
2. Update the apps list (Apps → Update Apps List)
3. Search for "Bulk Operations Automation" and click **Install**

```bash
# Example addons path structure
/odoo/addons/
└── mobipine_odoo_bulk_operations/
    ├── __manifest__.py
    ├── models/
    ├── views/
    ├── security/
    ├── data/
    └── tests/
```

To apply updates:
```bash
odoo -d <database> -u mobipine_odoo_bulk_operations
```

---

## Configuration

### Stock Locations

Create internal stock locations for your routes/branches at *Inventory → Configuration → Locations*:

```
WH/
├── Stock/
├── Chogoria Route        (usage: internal)
├── Garissa Route         (usage: internal)
└── Nairobi Route         (usage: internal)
```

These are referenced by the `bulkname` column in your import file.

### Default Supplier

For products that have no configured vendor (`product.seller_ids`), the system uses a fallback supplier:

1. Go to *Settings → Technical → System Parameters*
2. Create or edit `bulk_operations.default_supplier`
3. Set the value to the supplier's name (default: "Deen Innovations")

If the named supplier doesn't exist, it is created automatically with `supplier_rank = 1`.

---

## Performance Characteristics

| Metric | Typical Value |
|---|---|
| Processing speed | 1–3 seconds per customer-date group |
| Chunk size | 15 groups |
| Commit frequency | Every ~15–45 seconds |
| Max file size (practical) | 10,000+ rows (tested) |
| SQL queries per import | ~5–10 total (batch-resolved) |
| SQL queries per group | ~20–40 (SO + delivery + invoice + payment) |
| Timeout protection | None (background processing) |

**Bottlenecks:**
- Stock picking validation (`button_validate()`) is the most expensive operation per group
- Payment registration (`action_create_payments()`) involves accounting reconciliation
- Both are Odoo core operations and cannot be further optimized from the module level

---

## Development & Testing

The module includes a full test suite using Odoo's `TransactionCase`:

```bash
# Run all tests
odoo -d <database> --test-tags post_install -u mobipine_odoo_bulk_operations

# Run specific test class
odoo -d <database> --test-tags TestBulkOperationBatch -u mobipine_odoo_bulk_operations
```

Test coverage includes:
- CSV import parsing and error handling
- Partner, product, and location resolution (including edge cases)
- Full batch processing (SO, delivery, return, invoice, payment, PO)
- Weekend date rolling
- Savepoint isolation (one failure doesn't block the batch)
- Computed fields (net_qty, subtotal, line counts)
- Payment registration
- Inventory impact (quant creation and consumption)

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---|---|---|
| "No lines are ready to process" | All lines already processed or none imported | Check lines in *View Imported Data*; verify the import succeeded |
| Progress bar stuck at X% | Processing still running in background | Refresh the page; check server logs for errors |
| Processing never completes | Background thread crashed | Check Odoo server logs for traceback; re-click "Batch Process" to resume |
| "cursor already closed" | Previous timeout before async upgrade | Upgrade to the latest version (background processing) |
| "No cash or bank journal found" | No payment journal configured for the company | Create a cash or bank journal at *Accounting → Configuration → Journals* |
| "location not found" | Branch name doesn't match any internal location | Verify the location exists at *Inventory → Configuration → Locations* |
| "customer not found" | No partner matches the code or name | Check the partner's `ref` field or name in *Contacts* |
| "product not found" | Edition doesn't match any product | Verify the product's `default_code`, `name`, or `barcode` |
| Stock moves from wrong location | Route location had insufficient stock | Check that route locations have adequate inventory; this is expected fallback behavior |
| Return not credited to correct location | Fallback was used during delivery | See [Location Accuracy Caveat](#location-accuracy-caveat) |

---

## License

This module is licensed under the **LGPL-3**. See the [LICENSE](LICENSE) file for details.
