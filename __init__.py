# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .sale import *
from .statement import *
from .move import *
from .invoice import *

def register():
    Pool.register(
        SaleBank,
        Card,
        SalePaymentForm,
        Statement,
        Sale,
        Invoice,
        InvoiceLine,
        Move,
        Line,
        module='nodux_sale_payment', type_='model')
    Pool.register(
        WizardSalePayment,
        ReturnSale,
        module='nodux_sale_payment', type_='wizard')
    Pool.register(
        InvoiceReportPos,
        module='nodux_sale_payment', type_='report')
