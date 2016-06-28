# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard
from decimal import Decimal

__all__ = ['Statement']

class Statement:
    __metaclass__ = PoolMeta
    __name__ = 'account.statement'

    tipo_pago = fields.Selection([
            ('',''),
            ('efectivo','Efectivo'),
            ('tarjeta','Tarjeta de Credito'),
            ('deposito','Deposito'),
            ('cheque','Cheque'),
            ],'Forma de Pago')

    @classmethod
    def __setup__(cls):
        super(Statement, cls).__setup__()

    @fields.depends('name', 'tipo_pago')
    def on_change_name(self):
        result = {}
        tipo_pago = ""
        if self.name:
            name = self.name.lower()
            if 'efectivo' in name:
                tipo_pago = 'efectivo'
            if 'tarjeta' in name:
                tipo_pago = 'tarjeta'
            if 'deposito' in name:
                tipo_pago = 'deposito'
            if 'cheque' in name:
                tipo_pago = 'cheque'

        result['tipo_pago'] = tipo_pago
        return result
