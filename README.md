# Bulk Operations Automation

[![Odoo](https://img.shields.io/badge/Odoo-18.0-714b67?logo=odoo)](https://www.odoo.com)
[![License](https://img.shields.io/badge/license-LGPL--3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-18.0.1.0.0-green)](__manifest__.py)

Upload a daily CSV or XLSX of customer sales data and, in one click, generate Sales Orders, Deliveries, Returns, Invoices, and consolidated Purchase Orders.

---

## Table of Contents

- [Overview](#overview)
- [Workflow](#workflow)
- [Quick Start](#quick-start)
- [File Format](#file-format)
- [How Resolution Works](#how-resolution-works)
  - [Product Resolution](#product-resolution)
  - [Customer Resolution](#customer-resolution)
  - [Location Resolution](#location-resolution)
- [Generated Documents](#generated-documents)
  - [Sales Orders](#sales-orders)
  - [Deliveries](#deliveries)
  - [Returns](#returns)
  - [Invoices & Payments](#invoices--payments)
  - [Purchase Orders](#purchase-orders)
- [Duplicate Protection](#duplicate-protection)
- [Weekend Handling](#weekend-handling)
- [Import Modes](#import-modes)
  - [Quick Import](#quick-import)
  - [Standard Import Wizard](#standard-import-wizard)
- [Reviewing Data](#reviewing-data)
- [Dependencies](#dependencies)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Stock Locations](#stock-locations)
  - [Partner Route Location](#partner-route-location)
  - [Default Supplier](#default-supplier)
- [Development & Testing](#development--testing)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

This module automates the end-to-end order-to-cash cycle for businesses that distribute products to customers from route-based stock locations on a daily schedule.

**What it does:**

| Step | What happens |
|---|---|
| **Import** | Parse a CSV/XLSX with customer, product, quantity, and returns data |
| **Resolve** | Automatically match each row to Odoo Partners, Products, and Locations |
| **Sales Order** | One SO per customer per effective date |
| **Delivery** | Confirmed stock moves from the route's internal location |
| **Returns** | Same-day return pickings, crediting stock back |
| **Invoice** | Posted, fully-paid invoice per SO |
| **Purchase Order** | Consolidated PO per supplier for net quantities sold |

---

## Workflow

```
 ┌─────────┐     ┌──────────┐     ┌───────────┐
 │  Draft   │ ──→ │ Imported │ ──→ │ Processed │
 └─────────┘     └──────────┘     └───────────┘
      ↑               ↑                 ↑
 Create batch   Upload file &      Click "Batch
                click "Import      Process" to
                File"              generate all
                                   documents
```

**Processing order:** All customers for a given day are processed first, then the next day — ensuring each day's batch is complete before moving on.

---

## Quick Start

1. **Create a Batch** — *Bulk Operations → Batches → New*
2. **Select mode** — choose **Quick Import** (predefined column map) or **Standard Import** (custom column mapping)
3. **Upload file** — attach a CSV or XLSX via the *Import File* field
4. **Click Import File** — rows are parsed, matched, and staged as reviewable lines
5. **Review** — click *View Imported Data* to check matches; fix mismatches inline
6. **Click Batch Process** — all SOs, deliveries, returns, invoices, and POs are created in one pass

---

## File Format

### Quick Import — Expected Columns

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
| `returns` | returned | Quantity returned | Yes |

> **Custom headers?** Edit the `COLUMN_MAP` dict in `models/bulk_operation_batch.py` — nothing else in the import logic needs to change.

### Standard Import Wizard

Use this mode when your file has different column names, multiple sheets, or you want to choose which columns to import. The wizard auto-detects headers and lets you map each column to a field.

---

## How Resolution Works

### Product Resolution

Each `edition` value is searched in priority order:

1. `default_code` — **exact** match
2. `default_code` — **case-insensitive** (`=ilike`)
3. `name` — **exact** match
4. `name` — **case-insensitive** (`=ilike`)
5. `barcode` — **exact** match

For large imports, all unique edition values are resolved in **batched** queries (using `('default_code', 'in', [...])`) — reducing thousands of individual round-trips to a handful.

### Customer Resolution

Each customer is matched by:

1. `ref` — exact match on `customerid`
2. `name` — exact match on `name1`
3. `name` — case-insensitive match (`=ilike`)

### Location Resolution

Each branch/route is resolved from the `bulkname` column:

1. Search `stock.location` by **name** (case-insensitive, `usage='internal'`)
2. If not found, search by **complete_name** (e.g. `WH/Chogoria`)
3. If still not found, the line is flagged with an error for manual fixing

> No hardcoded fallbacks — location is read exclusively from the file.

---

## Generated Documents

### Sales Orders

- **One SO per customer per effective date** — all their products are grouped into a single order
- Automatically **confirmed** after creation
- Saturday/Sunday entries roll to Monday (see [Weekend Handling](#weekend-handling))

### Deliveries

- Source location is the resolved route/branch location from the file
- Stock moves are **assigned and validated** automatically
- Falls back to the main warehouse stock if the route location has insufficient inventory

### Returns

- **Incoming pickings** created for returned quantities
- Source: customer's delivery address
- Destination: the same route/branch location (stock is credited back)

### Invoices & Payments

- One **posted invoice** per Sales Order
- Automatically **paid** via the configured cash/bank journal

### Purchase Orders

- **One consolidated PO per supplier**, aggregating net demand across all customers
- Products are grouped by their configured vendor (`product.seller_ids`)
- Falls back to a configurable **default supplier** (system parameter `bulk_operations.default_supplier`)
- If net demand is zero (all items returned), no PO is created

---

## Duplicate Protection

Three layers prevent accidental re-imports:

| Layer | Mechanism | Scope |
|---|---|---|
| **Database constraint** | `UNIQUE(batch_id, date, customer_code, edition, branch_name, delivered, returned)` | Within the same batch |
| **Cross-batch detection** | `_find_existing_lines()` checks all other batches in `imported` state for overlapping `(date, customer_code, edition, branch_name)` tuples | Across different batches |
| **Process-time filter** | Lines flagged with `error_message` (including duplicates) are skipped during batch processing | During processing |

Imports that overlap with existing data in another batch are still imported but flagged with a visible error — you can review and delete them before processing.

---

## Weekend Handling

Saturday and Sunday delivery dates are automatically rolled to the following Monday, preventing customers from receiving separate weekend Sales Orders.

| Original Date | Effective Date |
|---|---|
| Monday–Friday | Same day |
| Saturday | Following Monday |
| Sunday | Following Monday |

---

## Import Modes

### Quick Import

Uses the predefined `COLUMN_MAP` to match file columns to fields. Best for files with a stable, known format.

### Standard Import Wizard

Opens a wizard where you can:
- Upload CSV or XLSX files (multi-sheet support)
- Choose the field separator (CSV)
- Map each column to an Odoo field
- Preview sample data before importing

---

## Reviewing Data

After importing, click **View Imported Data** to inspect the staged rows:

| View | What you see |
|---|---|
| **List** | Every row exactly as in the file, with resolved links and editable fields. Rows with errors are highlighted in red. |
| **Pivot** | Aggregated summary by date, customer, branch, and edition — with totals for delivered, returned, net, and revenue. |
| **Graph** | Visual chart of delivered vs returned quantities over time. |

The batch form also includes inline tabs for:
- **Sales** — staged lines with inline editing
- **Purchases** — generated Purchase Orders
- **Deliveries** — generated stock pickings
- **Sales Orders & Invoices** — links to generated documents

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

### Partner Route Location

A convenience field `x_route_location_id` is available on the partner form's *Sales & Purchase* tab. This is for reference only — the module reads the delivery location exclusively from the import file.

### Default Supplier

Set a custom default supplier for products that have no configured vendor:

1. Go to *Settings → Technical → System Parameters*
2. Create or edit `bulk_operations.default_supplier`
3. Set the value to the supplier's name (default: "Deen Innovations")

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

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---|---|---|
| "Found multiple matches for value..." | Using Odoo's standard import button | Use the module's **Quick Import** or **Standard Import Wizard** instead |
| "cursor already closed" | Too many individual queries for large files | Use the latest version which batch-resolves all entities upfront |
| "No rows could be parsed" | Empty file or all rows have missing dates | Check that the `deliverydate` column is present and populated |
| Line flagged "duplicate" | Same data already exists in another batch | Review both batches and delete the duplicate lines before processing |
| "location not found" | Branch name doesn't match any internal location | Verify the location exists at *Inventory → Configuration → Locations* |
| "customer not found" | No partner matches the code or name | Check the partner's `ref` field or name in *Contacts* |
| "product not found" | Edition doesn't match any product | Verify the product's `default_code`, `name`, or `barcode` |

---

## License

This module is licensed under the **LGPL-3**. See the [LICENSE](LICENSE) file for details.
