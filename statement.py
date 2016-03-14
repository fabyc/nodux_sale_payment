# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard
from decimal import Decimal

__all__ = ['Statement']
__metaclass__ = PoolMeta


class Statement:
    __name__ = 'account.statement'
    
    tipo_pago = fields.Selection([
            ('',''),
            ('efectivo','Efectivo'),
            ('tarjeta','Tarjeta de Credito'),
            ('deposito','Deposito'),
            ('cheque','Cheque'),
            ],'Forma de Pago')
