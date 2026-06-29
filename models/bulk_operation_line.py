# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class BulkOperationLine(models.Model):
    _name = 'bulk.operation.line'
    _description = 'Bulk Operation Line'
    _order = 'date, id'

    batch_id = fields.Many2one('bulk.operation.batch', string='Batch', ondelete='cascade', required=True)

    # --- Raw columns, kept exactly as imported, for traceability ---
    distributor_id = fields.Char(string='Distributor ID')
    customer_code = fields.Char(string='Customer ID (file)')
    customer_name = fields.Char(string='Customer Name (file)')
    customer_group = fields.Char(string='Customer Group')
    branch_name = fields.Char(string='Branch (file)')
    edition = fields.Char(string='Edition / Product Code (file)')

    # --- Resolved links, editable so a mismatch can be fixed by hand ---
    partner_id = fields.Many2one('res.partner', string='Customer')
    product_id = fields.Many2one('product.product', string='Product')
    location_id = fields.Many2one('stock.location', string='Route Location',
                                   domain=[('usage', '=', 'internal')])

    date = fields.Date(string='Delivery Date', required=True)
    delivered = fields.Float(string='Delivered')
    returned = fields.Float(string='Returned')
    net_qty = fields.Float(string='Net Sold', compute='_compute_net_qty', store=True)

    price_unit = fields.Float(string='Unit Price')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)

    sale_line_id = fields.Many2one('sale.order.line', string='Generated Sale Line', readonly=True, copy=False)
    is_processed = fields.Boolean(string='Processed', default=False, copy=False)
    error_message = fields.Char(string='Error', readonly=True, copy=False)

    @api.depends('delivered', 'returned')
    def _compute_net_qty(self):
        for line in self:
            line.net_qty = line.delivered - line.returned

    @api.depends('net_qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.net_qty * line.price_unit

    @api.model
    def load(self, fields, data):
        raise UserError(_(
            "Direct import into \"Imported Lines\" is not supported. "
            "Use the Quick Import (upload a file on the Batch form and click \"Process File\") "
            "or the Standard Import wizard instead."
        ))
