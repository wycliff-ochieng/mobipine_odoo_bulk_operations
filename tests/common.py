from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class BulkOperationBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── Products ──────────────────────────────────────────────
        cls.product_a = cls.env['product.product'].create({
            'name': 'Newspaper A',
            'default_code': 'NP-A',
            'type': 'consu',
            'is_storable': True,
            'list_price': 50.0,
            'standard_price': 30.0,
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Magazine B',
            'default_code': 'MG-B',
            'type': 'consu',
            'is_storable': True,
            'list_price': 75.0,
            'standard_price': 45.0,
        })
        cls.product_c = cls.env['product.product'].create({
            'name': 'Booklet C',
            'default_code': 'BK-C',
            'type': 'consu',
            'is_storable': True,
            'list_price': 100.0,
            'standard_price': 60.0,
        })

        # ── Stock locations (routes) ─────────────────────────────
        warehouse = cls.env.ref('stock.warehouse0')
        cls.location_chogoria = cls.env['stock.location'].create({
            'name': 'Chogoria Route',
            'usage': 'internal',
            'location_id': warehouse.view_location_id.id,
        })
        cls.location_garissa = cls.env['stock.location'].create({
            'name': 'Garissa Route',
            'usage': 'internal',
            'location_id': warehouse.view_location_id.id,
        })
        cls.location_nairobi = cls.env['stock.location'].create({
            'name': 'Nairobi Route',
            'usage': 'internal',
            'location_id': warehouse.view_location_id.id,
        })

        # ── Partners ─────────────────────────────────────────────
        cls.partner_alice = cls.env['res.partner'].create({
            'name': 'Alice',
            'ref': 'CUST-001',
            'x_route_location_id': cls.location_chogoria.id,
        })
        cls.partner_ben = cls.env['res.partner'].create({
            'name': 'Ben',
            'ref': 'CUST-002',
            'x_route_location_id': cls.location_garissa.id,
        })
        cls.partner_no_route = cls.env['res.partner'].create({
            'name': 'NoRoute',
            'ref': 'CUST-003',
        })

        # ── Supplier ─────────────────────────────────────────────
        cls.supplier_deen = cls.env['res.partner'].create({
            'name': 'Deen Innovations',
            'supplier_rank': 1,
        })

        # ── Vendor pricelist for products ────────────────────────
        cls.env['product.supplierinfo'].create({
            'partner_id': cls.supplier_deen.id,
            'product_id': cls.product_a.id,
            'price': 28.0,
        })
        cls.env['product.supplierinfo'].create({
            'partner_id': cls.supplier_deen.id,
            'product_id': cls.product_b.id,
            'price': 42.0,
        })

        # ── Stock quants ─────────────────────────────────────────
        cls._create_quant(cls.product_a, cls.location_chogoria, 200.0)
        cls._create_quant(cls.product_b, cls.location_chogoria, 150.0)
        cls._create_quant(cls.product_a, cls.location_garissa, 100.0)
        cls._create_quant(cls.product_b, cls.location_garissa, 100.0)
        cls._create_quant(cls.product_c, cls.location_nairobi, 500.0)
        cls._create_quant(cls.product_a, cls.location_nairobi, 300.0)

        # ── Accounting: find cash/bank journals ──────────────────
        cls.cash_journal = cls.env['account.journal'].search([
            ('type', '=', 'cash'), ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.cash_journal:
            cls.cash_journal = cls.env['account.journal'].search([
                ('type', '=', 'bank'), ('company_id', '=', cls.env.company.id),
            ], limit=1)

    # ── Helpers ──────────────────────────────────────────────────

    @classmethod
    def _create_quant(cls, product, location, quantity):
        cls.env['stock.quant'].create({
            'product_id': product.id,
            'location_id': location.id,
            'quantity': quantity,
        })

    def _make_csv_content(self, rows):
        header = 'distributorid,customerid,name1,customergroup,bulkname,edition,deliverydate,delivered,returns'
        lines = [header]
        for row in rows:
            lines.append(','.join(str(v) for v in row))
        return '\n'.join(lines)

    def _make_batch_with_csv(self, csv_content, filename='test.csv'):
        import base64
        batch = self.env['bulk.operation.batch'].create({})
        batch.write({
            'import_file': base64.b64encode(csv_content.encode('utf-8')),
            'filename': filename,
        })
        return batch

    def _fully_setup_batch(self, csv_content=None):
        if csv_content is None:
            rows = [
                ('D001', 'CUST-001', 'Alice', 'GRP-A', 'Chogoria Route', 'NP-A', '2026-06-22', '30', '5'),
            ]
            csv_content = self._make_csv_content(rows)
        batch = self._make_batch_with_csv(csv_content)
        batch.action_import_file()
        return batch
