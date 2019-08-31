from odoo import fields, models, api


class StockMoveInherit(models.Model):
    _inherit = 'stock.move'

    @api.multi
    def write(self, vals):
        if 'state' in vals and self:
            if vals.get('state') == 'done':
                ticket_obj = self.env['exchange.ticket'].search([('return_picking_id', '=', self[0].picking_id.id)])
                if ticket_obj:
                    ticket_obj.write({'state': 'process'})
        return super(StockMoveInherit, self).write(vals)
