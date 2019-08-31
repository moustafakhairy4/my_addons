from odoo.addons.stock.tests.common2 import TestStockCommon
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests import common


class TestExchangeProcess(TestStockCommon):
    def test_exchange_process(self):
        # intial so
        print('********************')
        self.partner = self.env.ref('base.res_partner_1')
        self.product = self.env.ref('product.product_delivery_01')
        so_vals = {
            'partner_id': self.partner.id,
            'partner_invoice_id': self.partner.id,
            'partner_shipping_id': self.partner.id,
            'order_line': [(0, 0, {
                'name': self.product.name,
                'product_id': self.product.id,
                'product_uom_qty': 5.0,
                'product_uom': self.product.uom_id.id,
                'price_unit': self.product.list_price})],
            'pricelist_id': self.env.ref('product.list0').id,
        }
        self.so = self.env['sale.order'].create(so_vals)

        # confirm our standard so, check the picking
        self.so.action_confirm()
        self.assertTrue(self.so.picking_ids,
                        'Sale Stock: no picking created for "invoice on delivery" storable products')
        print(self.so.picking_ids)
        # invoice in on delivery, nothing should be invoiced
        self.assertEqual(self.so.invoice_status, 'no',
                         'Sale Stock: so invoice_status should be "no" instead of "%s".' % self.so.invoice_status)

        # deliver completely
        pick = self.so.picking_ids
        pick.move_lines.write({'quantity_done': 5})
        pick.button_validate()

        # Check quantity delivered
        del_qty = sum(sol.qty_delivered for sol in self.so.order_line)
        self.assertEqual(del_qty, 5.0,
                         'Sale Stock: delivered quantity should be 5.0 instead of %s after complete delivery' % del_qty)
        # Todo Ticket create
        ticket_obj = self.env['exchange.ticket']
        picking_id = self.so.picking_ids[0] if self.so.picking_ids else False
        self.assertEqual(picking_id.state, 'done', 'Picking (%s) Must be in done state' % picking_id)
        ticket = ticket_obj.create({
            'picking_id': picking_id.id,
        })
        ticket.onchange_picking_id()
        # ticket.ticket_line_ids.unlink()

        ticket.action_approve()
        #####################################################
        # Check invoice