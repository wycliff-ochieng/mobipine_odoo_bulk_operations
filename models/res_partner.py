# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_route_location_id = fields.Many2one(
        'stock.location',
        string='Default Route Location',
        domain=[('usage', '=', 'internal')],
        help="Fallback stock location used when an imported row doesn't specify a branch "
             "(the 'bulkname' column). If the row does specify a branch, that takes priority."
    )
