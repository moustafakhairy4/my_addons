# -*- coding: utf-8 -*-
{
    'name': "Delivery Exchange Process",
    'summary': "Delivery Exchange Process",
    'description': """ 
        This module provide a delivery exchange process.\n
        The idea behind is to allow the user to exchange an already delivered and paid product. It should
        follow the same approach like the existing delivery return process. It also means to update
        the related order line in the sale and / or purchase order.
     """,
    'author': "BLOOPARK SYSTEMS",
    'category': 'Sales',
    'version': '0.1',
    'depends': ['account', 'stock', 'sale_management', 'purchase', 'sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/exchange_ticket_sequence.xml',
        'wizard/ticket_line_action_wizard_view.xml',

        'views/exchange_ticket_views.xml',
        'views/stock_picking_inherit.xml',
        'views/menu_items.xml',
    ],
    'installable': True,
    'auto_install': False,
    'sequence': 1
}
