from odoo import fields, models, api, _
from odoo.exceptions import Warning


class TicketLineActionWizard(models.TransientModel):
    _name = 'ticket.process.wizard'
    _description = 'Action to process Ticket'

    ticket_line_id = fields.Many2one('exchange.ticket.lines', "Line")
    picking_id = fields.Many2one('stock.picking')
    product_id = fields.Many2one('product.product', "Product to be Replace")
    quantity = fields.Float("Quantity")
    so_status = fields.Selection([('update', 'Update Exist Sales Order'), ('create_so', 'Create New Sales Order'),
                                  ('delivery', 'Create Delivery Order ')], stinrg='So Status', default='update')

    send_goods_back = fields.Boolean("Send Goods Back to Customer")
    hide = fields.Selection([('true', 'true'), ('false', 'false')], default='true')
    state = fields.Char()

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id.id == self._context.get('product_id'):
            self.hide = 'true'
        else:
            self.hide = 'false'

    @api.model
    def default_get(self, default_fields):
        res = super(TicketLineActionWizard, self).default_get(default_fields)
        line = self.env['exchange.ticket.lines'].search([('id', '=', self._context.get('active_id'))])
        res['ticket_line_id'] = line.id
        res['state'] = line.ticket_id.state
        res['product_id'] = line.to_be_exchange_product_id.id or line.product_id.id
        res['quantity'] = line.to_be_exchange_quantity or line.quantity
        res['so_status'] = line.so_status or 'update'
        return res

    @api.multi
    def process_refund(self):
        if not self.ticket_line_id:
            return False
        self.ticket_line_id.write(
            {
                'to_be_exchange_product_id': self.product_id.id,
                'to_be_exchange_quantity': self.quantity,
                'so_status': self.so_status,
            })
