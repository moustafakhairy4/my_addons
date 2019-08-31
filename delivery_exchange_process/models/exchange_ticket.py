from odoo.exceptions import Warning
from odoo.tools.translate import _

from odoo import fields, models, api


class ExchangeTicket(models.Model):
    _name = "exchange.ticket"
    _description = "Exchange So Ticket"
    _order = "date"
    _inherit = ['mail.thread']

    @api.depends('picking_id')
    @api.multi
    def get_product_ids(self):
        product_ids = []
        for record in self:
            if not record.picking_id:
                continue
            for move in record.picking_id.move_lines:
                product_ids.append(move.product_id.id)
            record.move_product_ids = [(6, 0, product_ids)]

    @api.depends('ticket_line_ids.product_id')
    @api.multi
    def get_line_product_ids(self):
        for record in self:
            lines = [p for p in self.ticket_line_ids]
            record.move_product_ids = [(6, 0, [p.product_id.id for p in lines])]

    @api.onchange('picking_id')
    def onchange_picking_id(self):
        if self.picking_id:
            self.partner_id = self.picking_id.partner_id.id
            self.sale_id = self.picking_id.sale_id.id
            lines = [
                (0, 0, {'product_id': move.product_id.id, 'quantity': move.product_uom_qty, 'move_id': move.id}) for
                move in self.picking_id.move_lines]
            self.ticket_line_ids = lines

    @api.depends('picking_id')
    @api.model
    def get_products(self):
        for record in self:
            move_products = []
            for move in record.picking_id.move_lines:
                move_products.append(move.product_id.id)
            record.move_product_ids = [(6, 0, move_products)]

    name = fields.Char(string='RMA Number', default="New", readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('approve', 'Approved'), ('process', 'Processing'), ('done', 'Closed'),
         ('reject', 'Rejected')], default='draft', copy=False, track_visibility="onchange")
    description = fields.Text('Description')
    closed_date = fields.Datetime('Closed Date', readonly=True, copy=False)
    date = fields.Datetime('Date', Index=True, default=fields.Datetime.now, copy=False)
    user_id = fields.Many2one('res.users', 'Responsible', track_visibility='always', default=lambda self: self._uid)
    company_id = fields.Many2one('res.company', 'Company', related='sale_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', 'Partner')
    ticket_line_ids = fields.One2many("exchange.ticket.lines", "ticket_id", string="Return Line")
    invoice_id = fields.Many2one("account.invoice", string="Invoice", copy=False)
    picking_id = fields.Many2one('stock.picking', string='Delivery Order')
    sale_id = fields.Many2one('sale.order', "Sale Order", related='picking_id.sale_id')
    move_product_ids = fields.Many2many('product.product', "Products", compute=get_products)
    return_picking_id = fields.Many2one('stock.picking', string='Return Delivery Order', default=False, copy=False)
    to_return_picking_ids = fields.Many2many('stock.picking', string='Return Delivery Orders', default=False,
                                             copy=False)
    refund_invoice_ids = fields.Many2many('account.invoice', string='Refund Invoices', copy=False)
    new_sale_id = fields.Many2one('sale.order', 'New Sale Order', copy=False)
    location_id = fields.Many2one('stock.location', 'Return Location', domain=[('usage', '=', 'internal')])

    @api.multi
    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise Warning(_("Only 'Draft' Ticket(s) can be deleted !"))
        return super(ExchangeTicket, self).unlink()

    @api.multi
    def create_return_picking(self, ticket=False):
        location_id = self.location_id.id
        vals = {'picking_id': self.return_picking_id.id if ticket else self.picking_id.id}
        if location_id and not ticket:
            vals.update({'location_id': location_id})
        return_picking_wizard = self.env['stock.return.picking'].with_context(
            active_id=self.return_picking_id.id if ticket else self.picking_id.id).create(vals)
        return_lines = []
        lines = ticket or self.ticket_line_ids
        for line in lines:
            move_id = self.env['stock.move'].search([('product_id', '=', line.product_id.id), (
                'picking_id', '=', self.return_picking_id.id if ticket else self.picking_id.id),
                                                     ('sale_line_id', '=', line.move_id.sale_line_id.id)])
            return_line = self.env['stock.return.picking.line'].create(
                {'product_id': line.product_id.id, 'quantity': line.quantity, 'to_refund': line.to_refund,
                 'wizard_id': return_picking_wizard.id,
                 'move_id': move_id.id})
            return_lines.append(return_line.id)
        return_picking_wizard.write({'product_return_moves': [(6, 0, return_lines)]})
        new_picking_id, pick_type_id = return_picking_wizard._create_returns()
        if ticket:
            self.write({'to_return_picking_ids': [(4, new_picking_id)]})
        else:
            self.return_picking_id = new_picking_id
        return True

    @api.multi
    def action_approve(self):
        processed_product_list = []
        if len(self.ticket_line_ids) <= 0:
            raise Warning(_("There is no ticket lines !!"))
        total_qty = 0
        for line in self.ticket_line_ids:
            moves = line.search([('move_id', '=', line.move_id.id)])
            for m in moves:
                if m.ticket_id.state in ['process', 'approve', 'done']:
                    total_qty += m.quantity
            if total_qty >= line.move_id.quantity_done:
                processed_product_list.append(line.product_id.name)
        if processed_product_list:
            raise Warning(_('%s Product\'s delivered quantities were already exist' % (
                ", ".join(processed_product_list))))
        # for line in self.ticket_line_ids:
        #     if line.quantity <= 0 or not line.rma_reason_id:
        #         raise Warning(_("Please set Return Quantity and Reason for all products."))
        self.name = self.env['ir.sequence'].next_by_code('exchange.ticket.sequence')
        self.write({'state': 'approve'})
        self.create_return_picking()
        return True

    @api.multi
    def show_return_picking(self):
        if len(self.return_picking_id) == 1:
            return {
                'name': "Receipt",
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'type': 'ir.actions.act_window',
                'res_id': self.return_picking_id.id
            }
        else:
            return {
                'name': "Receipt",
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'stock.picking',
                'type': 'ir.actions.act_window',
                'domain': [('id', '=', self.return_picking_id.id)]
            }

    @api.multi
    def show_delivery_picking(self):
        if len(self.to_return_picking_ids.ids) == 1:
            return {
                'name': "Delivery",
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'type': 'ir.actions.act_window',
                'res_id': self.to_return_picking_ids.id
            }
        else:
            return {
                'name': "Deliveries",
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'stock.picking',
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', self.to_return_picking_ids.ids)]
            }

    @api.multi
    def act_supplier_invoice_refund_ept(self):
        if len(self.refund_invoice_ids) == 1:
            view_id = self.env.ref('account.invoice_form').id
            return {
                'name': "Customer Invoices",
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.invoice',
                'type': 'ir.actions.act_window',
                'view_id': view_id,
                'res_id': self.refund_invoice_ids.id
            }
        else:
            return {
                'name': "Customer Invoices",
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'account.invoice',
                'type': 'ir.actions.act_window',
                'views': [(self.env.ref('account.invoice_tree').id, 'tree'),
                          (self.env.ref('account.invoice_form').id, 'form')],
                'domain': [('id', 'in', self.refund_invoice_ids.ids), ('type', '=', 'out_refund')]
            }

    @api.multi
    def act_new_so_ept(self):
        return {
            'name': "Sale Order",
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'type': 'ir.actions.act_window',
            'res_id': self.new_sale_id.id
        }

    @api.multi
    def action_close_ticket(self):
        for ticket in self:
            if ticket.return_picking_id.state != 'done':
                raise Warning("You must validate Return Picking Order firstly !!.")
            return_lines = []
            refund_lines = []
            do_lines = []
            so_lines = []
            updated_so_lines = []
            for line in ticket.ticket_line_ids:
                if not line.next_action:
                    raise Warning(_("Please set an 'Action' for all lines."))

                if line.next_action == 'refund':
                    refund_lines.append(line)

                elif line.next_action == 'exchange':
                    if not line.to_be_exchange_product_id or line.to_be_exchange_quantity <= 0:
                        raise Warning(
                            "Ticket line with product %s has exchange product or exchange quantity or both not set." % (
                                line.product_id.name))
                    if not line.so_status:
                        raise Warning("Please set a 'Sale order Status' to all lines !!")

                    if line.so_status == 'update':
                        updated_so_lines.append(line)
                    elif line.so_status == 'create_so':
                        so_lines.append(line)
                    elif line.so_status == 'delivery':
                        do_lines.append(line)

            return_lines and ticket.create_return_picking(return_lines)
            refund_lines and ticket.create_refund(refund_lines)
            do_lines and ticket.delivery_order_create(do_lines)
            so_lines and ticket.create_so(so_lines)
            updated_so_lines and ticket.updated_so_lines(updated_so_lines)
            ticket.state = 'done'
            return ticket

    @api.multi
    def updated_so_lines(self, lines):
        for ticket in self:
            for line in lines:
                sale_order_line_obj = self.env['sale.order.line']
                line_vals = {
                    'product_id': line.to_be_exchange_product_id.id,
                    'product_uom_qty': line.to_be_exchange_quantity,
                    'order_id': ticket.sale_id.id,
                }
                upd_record = sale_order_line_obj.new(line_vals)
                upd_record.product_id_change()
                line_vals = sale_order_line_obj._convert_to_write({name: upd_record[name] for name in upd_record._cache})
                sale_order_line_obj.create(line_vals)

    @api.multi
    def create_so(self, lines):
        sale_order = self.env['sale.order']
        order_vals = {
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'warehouse_id': self.sale_id.warehouse_id.id,
        }
        new_record = sale_order.new(order_vals)
        new_record.onchange_partner_id()
        order_vals = sale_order._convert_to_write({name: new_record[name] for name in new_record._cache})
        new_record = sale_order.new(order_vals)
        new_record.onchange_partner_shipping_id()
        order_vals = sale_order._convert_to_write({name: new_record[name] for name in new_record._cache})
        order_vals.update({
            'state': 'draft',
            'client_order_ref': self.name,
        })
        so = sale_order.create(order_vals)
        self.new_sale_id = so.id
        for line in lines:
            sale_order_line = self.env['sale.order.line']
            order_line = {
                'order_id': so.id,
                'product_id': line.to_be_exchange_product_id.id,
                'company_id': self.company_id.id,
                'name': line.to_be_exchange_product_id.name
            }
            new_order_line = sale_order_line.new(order_line)
            new_order_line.product_id_change()
            order_line = sale_order_line._convert_to_write(
                {name: new_order_line[name] for name in new_order_line._cache})
            order_line.update({
                'product_uom_qty': line.to_be_exchange_quantity,
                'state': 'draft',
            })
            sale_order_line.create(order_line)
        self.write({'new_sale_id': so.id})
        return True

    @api.multi
    def delivery_order_create(self, lines):
        stock_picking_obj = self.env['stock.picking']
        delivery = stock_picking_obj.create(
            {'partner_id': self.partner_id.id, 'location_id': self.picking_id.location_id.id,
             'location_dest_id': self.picking_id.location_dest_id.id,
             'picking_type_id': self.picking_id.picking_type_id.id, 'origin': self.name})
        for line in lines:
            self.env['stock.move'].create({
                'location_id': self.picking_id.location_id.id,
                'location_dest_id': self.picking_id.location_dest_id.id,
                'product_uom_qty': line.to_be_exchange_quantity or line.quantity,
                'name': line.to_be_exchange_product_id.name,
                'product_id': line.to_be_exchange_product_id.id,
                'state': 'draft',
                'picking_id': delivery.id,
                'product_uom': line.to_be_exchange_product_id.uom_id.id,
                'company_id': self.company_id.id
            })
        self.write({'to_return_picking_ids': [(4, delivery.id)]})
        delivery.action_assign()
        return True

    @api.multi
    def create_refund(self, lines):
        refund_invoice_ids = {}
        refund_invoice_ids_rec = []
        is_create_refund = False
        product_process_dict = {}
        for line in lines:
            if line.id not in product_process_dict:
                product_process_dict.update({line.id: {'total_qty': line.return_qty, 'invoice_line_ids': {}}})
            for invoice_line in line.move_id.sale_line_id.invoice_lines:
                if invoice_line.invoice_id.state not in ['open',
                                                         'paid'] or invoice_line.invoice_id.type != 'out_invoice':
                    continue
                is_create_refund = True
                if product_process_dict.get(line.id).get('process_qty', 0) < product_process_dict.get(line.id).get(
                        'total_qty', 0):
                    if product_process_dict.get(line.id).get('process_qty',
                                                             0) + invoice_line.quantity < product_process_dict.get(
                        line.id).get('total_qty', 0):
                        process_qty = invoice_line.quantity
                        product_process_dict.get(line.id).update({'process_qty': product_process_dict.get(line.id).get(
                            'process_qty', 0) + invoice_line.quantity})
                    else:
                        process_qty = product_process_dict.get(line.id).get('total_qty', 0) - product_process_dict.get(
                            line.id).get('process_qty', 0)
                        product_process_dict.get(line.id).update(
                            {'process_qty': product_process_dict.get(line.id).get('total_qty', 0)})
                    product_process_dict.get(line.id).get('invoice_line_ids').update(
                        {invoice_line.id: process_qty, 'invoice_id': invoice_line.invoice_id.id})
                    if refund_invoice_ids.get(invoice_line.invoice_id.id):
                        refund_invoice_ids.get(invoice_line.invoice_id.id).append(
                            {invoice_line.product_id.id: process_qty, 'price': line.move_id.sale_line_id.price_unit})
                    else:
                        refund_invoice_ids.update({invoice_line.invoice_id.id: [
                            {invoice_line.product_id.id: process_qty, 'price': line.move_id.sale_line_id.price_unit}]})
        if not is_create_refund:
            return False
        for invoice_id, lines in refund_invoice_ids.items():
            invoice = self.env['account.invoice'].browse(invoice_id)
            refund_invoice = invoice.refund(invoice.date_invoice, invoice.date, self.name, invoice.journal_id.id)
            if not refund_invoice:
                continue
            refund_invoice and refund_invoice.invoice_line_ids and refund_invoice.invoice_line_ids.unlink()
            for line in lines:
                if not list(line.keys()) or not list(line.values()):
                    continue
                price = line.get('price')
                del line['price']
                product_id = self.env['product.product'].browse(list(line.keys())[0])
                if not product_id:
                    continue
                line_vals = self.env['account.invoice.line'].new(
                    {'product_id': product_id.id, 'name': product_id.name, 'invoice_id': refund_invoice.id,
                     'account_id': invoice.account_id.id})
                line_vals._onchange_product_id()
                line_vals = line_vals._convert_to_write({name: line_vals[name] for name in line_vals._cache})
                line_vals.update({'quantity': list(line.values())[0], 'price_unit': price})
                self.env['account.invoice.line'].create(line_vals)
            refund_invoice_ids_rec.append(refund_invoice.id)
        raise ValueError()
        refund_invoice_ids_rec and self.write({'refund_invoice_ids': [(6, 0, refund_invoice_ids_rec)]})


class TicketLines(models.Model):
    _name = 'exchange.ticket.lines'
    _description = "Exchange Ticket Lines"
    _rec_name = 'product_id'

    @api.multi
    def get_return_quantity(self):
        for record in self:
            if record.ticket_id.return_picking_id:
                move_line = self.env['stock.move'].search([('picking_id', '=', record.ticket_id.return_picking_id.id),
                                                           ('sale_line_id', '=', record.move_id.sale_line_id.id)])
                record.return_qty = move_line.quantity_done

    @api.multi
    def get_done_quantity(self):
        for record in self:
            if record.ticket_id.picking_id:
                record.done_qty = record.move_id.quantity_done

    @api.constrains('quantity')
    def check_qty(self):
        for line in self:
            if line.quantity < 0:
                raise Warning(_('Quantity must be positive number'))
            elif line.quantity > line.move_id.quantity_done:
                raise Warning(_('Quantity must be less than or equal to the delivered quantity'))

    product_id = fields.Many2one('product.product', string='Product')
    done_qty = fields.Float('Delivered Quantity', compute=get_done_quantity)
    quantity = fields.Float('Return Quantity', copy=False)
    return_qty = fields.Float('Received Quantity', compute=get_return_quantity)
    ticket_id = fields.Many2one('exchange.ticket', string='Ticket', copy=False)
    next_action = fields.Selection([('refund', 'Refund'), ('exchange', 'Exchange')], "Action", copy=False)
    to_be_exchange_product_id = fields.Many2one('product.product', "Product to be exchange", copy=False)
    to_be_exchange_quantity = fields.Float("Exchange Quantity", copy=False)
    so_status = fields.Selection([('update', 'Update Exist Sales Order'), ('create_so', 'Create New Sales Order'),
                                  ('delivery', 'Create Delivery Order ')], stinrg='So Status', default='update')
    move_id = fields.Many2one('stock.move')
    rma_reason_id = fields.Many2one('rma.reason.ept', 'Reason')
    to_refund = fields.Boolean('To Refund (update SO/PO)', copy=False,
                               help='Trigger a decrease of the delivered/received quantity in the associated Sale Order/Purchase Order')

    @api.multi
    def unlink(self):
        for record in self:
            if record.ticket_id and record.ticket_id.state != 'draft':
                raise Warning(_("You can delete line(s) in draft state only ."))
        return super(TicketLines, self).unlink()

    @api.multi
    def action_ticket_refund_process_ept(self):
        return {
            'name': 'Return Products',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'ticket.process.wizard',
            'src_model': 'exchange.ticket.lines',
            'target': 'new',
            'context': {'product_id': self.product_id.id, 'hide': True, 'ticket_line_id': self.id}
        }
