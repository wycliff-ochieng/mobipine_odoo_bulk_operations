{
    'name': 'Bulk Operations Automation',
    'version': '18.0.1.0.0',
    'summary': 'Automates daily sales order creation, delivery, invoicing, returns and consolidated purchasing.',
    'description': """
Bulk Operations
===============
Upload a daily CSV of customer / product / quantity sold / quantity returned
data and, in one click, generate:

* One Sales Order per customer per date (Saturday/Sunday rolled into Monday)
* A confirmed Delivery, with stock deducted at the customer's assigned route location
* Same-day return pickings, crediting stock back to the route location
* A posted, paid customer Invoice
* One consolidated Purchase Order per supplier, based on net quantity sold across all customers
""",
    'category': 'Sales',
    'author': 'Development Team',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'purchase',
        'stock',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/bulk_operation_views.xml',
        'views/import_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}
