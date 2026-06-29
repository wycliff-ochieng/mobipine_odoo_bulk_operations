from odoo import fields
from odoo.tests import tagged

from .common import BulkOperationBase


@tagged('post_install', '-at_install')
class TestBulkOperationLine(BulkOperationBase):

    def _create_line(self, overrides=None):
        vals = {
            'batch_id': self.env['bulk.operation.batch'].create({}).id,
            'partner_id': self.partner_alice.id,
            'product_id': self.product_a.id,
            'location_id': self.location_chogoria.id,
            'date': fields.Date.from_string('2026-06-22'),
            'delivered': 30,
            'returned': 5,
            'price_unit': 50,
        }
        if overrides:
            vals.update(overrides)
        return self.env['bulk.operation.line'].create(vals)

    def test_computed_net_qty(self):
        line = self._create_line({'delivered': 30, 'returned': 5})
        self.assertEqual(line.net_qty, 25.0)

    def test_computed_net_qty_no_returns(self):
        line = self._create_line({'delivered': 30, 'returned': 0})
        self.assertEqual(line.net_qty, 30.0)

    def test_computed_net_qty_full_return(self):
        line = self._create_line({'delivered': 30, 'returned': 30})
        self.assertEqual(line.net_qty, 0.0)

    def test_computed_subtotal(self):
        line = self._create_line({'delivered': 10, 'returned': 2, 'price_unit': 50})
        self.assertEqual(line.subtotal, 400.0)

    def test_computed_subtotal_zero(self):
        line = self._create_line({'delivered': 10, 'returned': 10, 'price_unit': 50})
        self.assertEqual(line.subtotal, 0.0)

    def test_customer_group_stored(self):
        line = self._create_line({'customer_group': 'GRP-A'})
        self.assertEqual(line.customer_group, 'GRP-A')

    def test_distributor_id_stored(self):
        line = self._create_line({'distributor_id': 'D001'})
        self.assertEqual(line.distributor_id, 'D001')

    def test_customer_code_stored(self):
        line = self._create_line({'customer_code': 'CUST-001'})
        self.assertEqual(line.customer_code, 'CUST-001')

    def test_branch_name_stored(self):
        line = self._create_line({'branch_name': 'Chogoria'})
        self.assertEqual(line.branch_name, 'Chogoria')

    def test_edition_stored(self):
        line = self._create_line({'edition': 'NP-A'})
        self.assertEqual(line.edition, 'NP-A')

    def test_default_is_not_processed(self):
        line = self._create_line()
        self.assertFalse(line.is_processed)

    def test_default_error_message_empty(self):
        line = self._create_line()
        self.assertFalse(line.error_message)

