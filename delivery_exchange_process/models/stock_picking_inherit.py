from odoo import fields, models, api


class StockPickingInherit(models.Model):
    _inherit = 'stock.picking'

    @api.multi
    def _count_ticket(self):
        for record in self:
            len_ticket = self.env['exchange.ticket'].search_count([('picking_id', '=', record.id)])
            record.count_ticket = len_ticket

    count_ticket = fields.Integer(compute=_count_ticket, string='Tickets')
