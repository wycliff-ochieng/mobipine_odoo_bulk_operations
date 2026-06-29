from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BulkOperationBase


@tagged('post_install', '-at_install')
class TestBulkOperationBatch(BulkOperationBase):

    # ── Creation & naming ───────────────────────────────────────

    def test_batch_sequence_name(self):
        batch = self.env['bulk.operation.batch'].create({})
        self.assertTrue(batch.name)
        self.assertIn('BOP/', batch.name)

    def test_batch_draft_state(self):
        batch = self.env['bulk.operation.batch'].create({})
        self.assertEqual(batch.state, 'draft')

    # ── _parse_cell_date ────────────────────────────────────────

    def test_parse_cell_date_string(self):
        batch = self.env['bulk.operation.batch'].create({})
        result = batch._parse_cell_date('2026-06-22')
        self.assertEqual(result, date(2026, 6, 22))

    def test_parse_cell_date_date_obj(self):
        batch = self.env['bulk.operation.batch'].create({})
        result = batch._parse_cell_date(date(2026, 6, 22))
        self.assertEqual(result, date(2026, 6, 22))

    def test_parse_cell_date_datetime_obj(self):
        batch = self.env['bulk.operation.batch'].create({})
        from datetime import datetime
        result = batch._parse_cell_date(datetime(2026, 6, 22, 10, 30))
        self.assertEqual(result, date(2026, 6, 22))

    def test_parse_cell_date_invalid(self):
        batch = self.env['bulk.operation.batch'].create({})
        result = batch._parse_cell_date('not-a-date')
        self.assertFalse(result)

    def test_parse_cell_date_empty(self):
        batch = self.env['bulk.operation.batch'].create({})
        result = batch._parse_cell_date('')
        self.assertFalse(result)

    # ── _resolve_partner ────────────────────────────────────────

    def test_resolve_partner_by_code(self):
        batch = self.env['bulk.operation.batch'].create({})
        partner = batch._resolve_partner('CUST-001', 'Alice')
        self.assertEqual(partner, self.partner_alice)

    def test_resolve_partner_by_name(self):
        batch = self.env['bulk.operation.batch'].create({})
        partner = batch._resolve_partner('', 'Alice')
        self.assertEqual(partner, self.partner_alice)

    def test_resolve_partner_case_insensitive(self):
        batch = self.env['bulk.operation.batch'].create({})
        partner = batch._resolve_partner('', 'alice')
        self.assertEqual(partner, self.partner_alice)

    def test_resolve_partner_not_found(self):
        batch = self.env['bulk.operation.batch'].create({})
        partner = batch._resolve_partner('', 'NonExistent')
        self.assertFalse(partner)

    def test_resolve_partner_code_takes_precedence(self):
        # Create partner with same name but different ref
        other = self.env['res.partner'].create({
            'name': 'Alice',
            'ref': 'CUST-999',
        })
        batch = self.env['bulk.operation.batch'].create({})
        partner = batch._resolve_partner('CUST-001', 'Alice')
        self.assertEqual(partner, self.partner_alice)
        other.unlink()

    # ── _resolve_product ────────────────────────────────────────

    def test_resolve_product_by_code(self):
        batch = self.env['bulk.operation.batch'].create({})
        product = batch._resolve_product('NP-A')
        self.assertEqual(product, self.product_a)

    def test_resolve_product_not_found(self):
        batch = self.env['bulk.operation.batch'].create({})
        product = batch._resolve_product('NONEXISTENT')
        self.assertFalse(product)

    def test_resolve_product_empty(self):
        batch = self.env['bulk.operation.batch'].create({})
        product = batch._resolve_product('')
        self.assertFalse(product)

    # ── _resolve_location ───────────────────────────────────────

    def test_resolve_location_by_complete_name(self):
        batch = self.env['bulk.operation.batch'].create({})
        location = batch._resolve_location('WH/Chuka', self.partner_alice)
        wh_chuka = self.env['stock.location'].search([('name', '=', 'WH/Chuka')], limit=1)
        if wh_chuka:
            self.assertEqual(location, wh_chuka)

    def test_resolve_location_empty_returns_false(self):
        batch = self.env['bulk.operation.batch'].create({})
        location = batch._resolve_location('', self.partner_alice)
        self.assertFalse(location)

    def test_resolve_location_by_branch_name(self):
        batch = self.env['bulk.operation.batch'].create({})
        location = batch._resolve_location('Chogoria Route', self.partner_alice)
        self.assertEqual(location, self.location_chogoria)

    def test_resolve_location_with_branch_name_only(self):
        batch = self.env['bulk.operation.batch'].create({})
        location = batch._resolve_location('Chogoria Route', self.partner_alice)
        self.assertEqual(location, self.location_chogoria)

    def test_resolve_location_returns_false_when_specified_not_found(self):
        batch = self.env['bulk.operation.batch'].create({})
        location = batch._resolve_location('NonExistent Branch', self.partner_alice)
        self.assertFalse(location)

    def test_resolve_location_no_branch_no_partner_route(self):
        batch = self.env['bulk.operation.batch'].create({})
        location = batch._resolve_location('', self.partner_no_route)
        self.assertFalse(location)

    # ── _get_effective_date ─────────────────────────────────────

    def test_effective_date_monday(self):
        batch = self.env['bulk.operation.batch'].create({})
        monday = date(2026, 6, 22)  # known Monday
        self.assertEqual(batch._get_effective_date(monday), monday)

    def test_effective_date_tuesday(self):
        batch = self.env['bulk.operation.batch'].create({})
        tuesday = date(2026, 6, 23)
        self.assertEqual(batch._get_effective_date(tuesday), tuesday)

    def test_effective_date_friday(self):
        batch = self.env['bulk.operation.batch'].create({})
        friday = date(2026, 6, 26)
        self.assertEqual(batch._get_effective_date(friday), friday)

    def test_effective_date_saturday_rolls_to_monday(self):
        batch = self.env['bulk.operation.batch'].create({})
        saturday = date(2026, 6, 27)
        expected = date(2026, 6, 29)
        self.assertEqual(batch._get_effective_date(saturday), expected)

    def test_effective_date_sunday_rolls_to_monday(self):
        batch = self.env['bulk.operation.batch'].create({})
        sunday = date(2026, 6, 28)
        expected = date(2026, 6, 29)
        self.assertEqual(batch._get_effective_date(sunday), expected)

    # ── CSV import (action_import_file) ─────────────────────────

    def test_import_valid_csv(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', 'GRP-A', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '5'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        self.assertEqual(batch.state, 'imported')
        self.assertEqual(len(batch.line_ids), 1)
        line = batch.line_ids[0]
        self.assertEqual(line.partner_id, self.partner_alice)
        self.assertEqual(line.product_id, self.product_a)
        self.assertEqual(line.location_id, self.location_chogoria)
        self.assertEqual(line.delivered, 30.0)
        self.assertEqual(line.returned, 5.0)

    def test_import_multiple_rows(self):
        rows = [
            ('D001', 'CUST-001', 'Alice', 'GRP-A', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '5'),
            ('D002', 'CUST-002', 'Ben', 'GRP-B', 'Garissa Route', 'MG-B', '2026-06-22', '20', '2'),
        ]
        csv_content = self._make_csv_content(rows)
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        self.assertEqual(len(batch.line_ids), 2)

    def test_import_missing_customer(self):
        csv_content = self._make_csv_content([
            ('D001', 'NONEXIST', 'Ghost', '', '', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        line = batch.line_ids
        self.assertTrue(line.error_message)

    def test_import_missing_product(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'BAD-CODE', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        line = batch.line_ids
        self.assertTrue(line.error_message)

    def test_import_missing_location(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'NonExistent Branch', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        line = batch.line_ids
        self.assertTrue(line.error_message)

    def test_import_missing_date(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        with self.assertRaises(UserError):
            batch.action_import_file()

    def test_import_invalid_date(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', 'not-a-date', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        with self.assertRaises(UserError):
            batch.action_import_file()

    def test_import_no_file_raises(self):
        batch = self.env['bulk.operation.batch'].create({})
        with self.assertRaises(UserError):
            batch.action_import_file()

    def test_import_empty_file_raises(self):
        csv_content = self._make_csv_content([])
        batch = self._make_batch_with_csv(csv_content)
        with self.assertRaises(UserError):
            batch.action_import_file()

    def test_import_negative_returns_abs(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '-5'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        self.assertEqual(batch.line_ids.returned, 5.0)

    def test_import_price_from_product(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '10', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        self.assertEqual(batch.line_ids.price_unit, 50.0)

    def test_import_replaces_old_lines(self):
        csv_content1 = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '10', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content1)
        batch.action_import_file()
        self.assertEqual(len(batch.line_ids), 1)

        csv_content2 = self._make_csv_content([
            ('D002', 'CUST-002', 'Ben', '', 'Garissa Route', 'MG-B', '2026-06-22', '20', '0'),
        ])
        batch.write({
            'import_file': self._encode_csv(csv_content2),
        })
        batch.action_import_file()
        self.assertEqual(len(batch.line_ids), 1)
        self.assertEqual(batch.line_ids.partner_id, self.partner_ben)

    # ── Full batch processing ───────────────────────────────────

    def test_process_single_customer_single_product(self):
        batch = self._fully_setup_batch()
        batch.action_batch_process()
        self.assertEqual(batch.state, 'processed')

        self.assertTrue(batch.sale_order_ids)
        self.assertTrue(batch.invoice_ids)
        self.assertTrue(batch.picking_ids)
        self.assertTrue(batch.purchase_order_ids)

        so = batch.sale_order_ids[:1]
        self.assertEqual(so.partner_id, self.partner_alice)
        self.assertEqual(len(so.order_line), 1)
        self.assertEqual(so.order_line[0].product_id, self.product_a)
        self.assertEqual(so.order_line[0].product_uom_qty, 30.0)

        for line in batch.line_ids:
            self.assertTrue(line.is_processed)
            self.assertFalse(line.error_message)

    def test_process_multiple_customers(self):
        rows = [
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '5'),
            ('D002', 'CUST-002', 'Ben', '', 'Garissa Route', 'MG-B', '2026-06-22', '20', '2'),
        ]
        csv_content = self._make_csv_content(rows)
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()

        self.assertEqual(len(batch.sale_order_ids), 2)
        partners = batch.sale_order_ids.mapped('partner_id')
        self.assertIn(self.partner_alice, partners)
        self.assertIn(self.partner_ben, partners)

    def test_process_with_returns(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '25'),
        ])
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()

        out_pickings = batch.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        self.assertTrue(out_pickings)

        return_pickings = self.env['stock.picking'].search([
            ('origin', '=ilike', 'Return:%'),
        ])
        self.assertTrue(return_pickings)

        net_demand = 30 - 25  # 5
        po = batch.purchase_order_ids[:1]
        self.assertEqual(po.order_line[0].product_qty, net_demand)

    def test_process_saturday_rolls_to_monday(self):
        rows = [
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-27', '15', '0'),
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-28', '10', '0'),
        ]
        csv_content = self._make_csv_content(rows)
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()

        self.assertEqual(len(batch.sale_order_ids), 1)
        so = batch.sale_order_ids[:1]
        total_qty = sum(so.order_line.mapped('product_uom_qty'))
        self.assertEqual(total_qty, 25.0)

    def test_process_generates_consolidated_po(self):
        rows = [
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '0'),
            ('D002', 'CUST-002', 'Ben', '', 'Garissa Route', 'NP-A', '2026-06-22', '20', '0'),
        ]
        csv_content = self._make_csv_content(rows)
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()

        self.assertEqual(len(batch.purchase_order_ids), 1)
        po = batch.purchase_order_ids[:1]
        po_line = po.order_line[0]
        self.assertEqual(po_line.product_id, self.product_a)
        self.assertEqual(po_line.product_qty, 50.0)
        self.assertEqual(po.partner_id, self.supplier_deen)

    def test_process_with_no_net_demand_no_po(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '10', '10'),
        ])
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()

        # Net demand = 0 -> no PO expected
        self.assertFalse(batch.purchase_order_ids)

    def test_process_line_marked_processed(self):
        batch = self._fully_setup_batch()
        batch.action_batch_process()
        for line in batch.line_ids:
            self.assertTrue(line.is_processed)
            self.assertFalse(line.error_message)

    def test_process_all_succeeded(self):
        rows = [
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '5'),
            ('D002', 'CUST-002', 'Ben', '', 'Garissa Route', 'MG-B', '2026-06-22', '20', '2'),
        ]
        csv_content = self._make_csv_content(rows)
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()
        for line in batch.line_ids:
            self.assertTrue(line.is_processed)
            self.assertFalse(line.error_message)

    def test_process_invoice_is_posted_and_paid(self):
        batch = self._fully_setup_batch()
        batch.action_batch_process()
        for inv in batch.invoice_ids:
            self.assertEqual(inv.state, 'posted')
            self.assertAlmostEqual(inv.amount_residual, 0.0, places=2)

    def test_process_delivery_from_correct_location(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._fully_setup_batch(csv_content)
        batch.action_batch_process()

        for picking in batch.picking_ids:
            self.assertEqual(picking.location_id, self.location_chogoria)
            for move in picking.move_ids:
                self.assertEqual(move.location_id, self.location_chogoria)

    # ── Error scenarios ─────────────────────────────────────────

    def test_process_no_imported_lines_raises(self):
        batch = self.env['bulk.operation.batch'].create({})
        with self.assertRaises(UserError):
            batch.action_batch_process()

    def test_process_missing_partner_flagged(self):
        csv_content = self._make_csv_content([
            ('D001', 'NONEXIST', 'Ghost', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        with self.assertRaises(UserError):
            batch.action_batch_process()

    def test_process_missing_product_flagged(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'BAD-CODE', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        with self.assertRaises(UserError):
            batch.action_batch_process()

    def test_process_missing_location_flagged(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'NonExistent Branch', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        with self.assertRaises(UserError):
            batch.action_batch_process()

    def test_process_return_exceeds_delivered_flagged(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '10', '20'),
        ])
        batch = self._fully_setup_batch(csv_content)
        with self.assertRaises(UserError):
            batch.action_batch_process()

    def test_savepoint_isolation_one_fails(self):
        rows = [
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '0'),
            ('D002', 'NONEXIST', 'Ghost', '', 'Chogoria Route', 'NP-A', '2026-06-22', '20', '0'),
        ]
        csv_content = self._make_csv_content(rows)
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()

        alice_line = batch.line_ids.filtered(lambda l: l.partner_id == self.partner_alice)
        self.assertTrue(alice_line)
        ghost_lines = batch.line_ids.filtered(lambda l: l.customer_name == 'Ghost')
        self.assertTrue(ghost_lines)

        batch.action_batch_process()

        self.assertEqual(batch.state, 'processed')
        self.assertTrue(alice_line.is_processed)
        self.assertFalse(alice_line.error_message)
        self.assertFalse(ghost_lines.is_processed)
        self.assertTrue(ghost_lines.error_message)

    # ── Purchase orders ─────────────────────────────────────────

    def test_get_fallback_supplier_creates(self):
        batch = self.env['bulk.operation.batch'].create({})
        supplier = batch._get_fallback_supplier()
        self.assertTrue(supplier)
        self.assertEqual(supplier.name, 'Deen Innovations')

    def test_get_fallback_supplier_custom(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'bulk_operations.default_supplier', 'Custom Supplier'
        )
        batch = self.env['bulk.operation.batch'].create({})
        supplier = batch._get_fallback_supplier()
        self.assertEqual(supplier.name, 'Custom Supplier')

    def test_create_consolidated_po_empty(self):
        batch = self.env['bulk.operation.batch'].create({})
        pos = batch._create_consolidated_po({})
        self.assertFalse(pos)

    def test_create_consolidated_po_groups_by_supplier(self):
        batch = self.env['bulk.operation.batch'].create({})
        net_demand = {self.product_a: 50.0, self.product_b: 30.0}
        pos = batch._create_consolidated_po(net_demand)
        self.assertEqual(len(pos), 1)
        po = pos[:1]
        self.assertEqual(po.partner_id, self.supplier_deen)
        product_qtys = {(l.product_id.id, l.product_qty) for l in po.order_line}
        self.assertIn((self.product_a.id, 50.0), product_qtys)
        self.assertIn((self.product_b.id, 30.0), product_qtys)

    # ── Computed fields on batch ────────────────────────────────

    def test_error_line_count(self):
        csv_content = self._make_csv_content([
            ('D001', 'NONEXIST', 'Ghost', '', '', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        self.assertEqual(batch.error_line_count, 1)

    def test_pending_line_count(self):
        csv_content = self._make_csv_content([
            ('D001', 'CUST-001', 'Alice', '', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '0'),
        ])
        batch = self._fully_setup_batch(csv_content)
        self.assertEqual(batch.pending_line_count, 1)
        batch.action_batch_process()
        self.assertEqual(batch.pending_line_count, 0)

    # ── Payment registration ────────────────────────────────────

    def test_register_payment(self):
        batch = self._fully_setup_batch()
        batch.action_batch_process()
        for inv in batch.invoice_ids:
            self.assertAlmostEqual(inv.amount_residual, 0.0, places=2,
                                   msg="Invoice %s should be fully paid" % inv.name)

    # ── XLSX support (requires openpyxl) ────────────────────────
    # ── Only tested if openpyxl is available ─────────────────────

    def _encode_csv(self, content):
        import base64
        return base64.b64encode(content.encode('utf-8'))
