#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from decimal import Decimal
import base64
from trytond.model import Workflow, ModelView, ModelSQL, fields
from trytond.report import Report
from trytond.wizard import Wizard, StateView, StateTransition, StateAction, \
    Button
from trytond.pyson import If, Eval, Bool, Id
from trytond.tools import reduce_ids, grouped_slice
from trytond.transaction import Transaction
from trytond.pool import PoolMeta, Pool

__all__ = ['Invoice', 'InvoiceLine']
__metaclass__ = PoolMeta

class Invoice(Workflow, ModelSQL, ModelView):
    'Invoice'
    __name__ = 'account.invoice'

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()

    def create_move(self):
        pool = Pool()
        Move = pool.get('account.move')
        Period = pool.get('account.period')
        Date = pool.get('ir.date')

        if self.move:
            return self.move
        self.update_taxes([self], exception=True)
        move_lines = self._get_move_line_invoice_line()
        move_lines += self._get_move_line_invoice_tax()

        if self.type == 'in_invoice':
            Module = pool.get('ir.module.module')
            module = None
            module_w = Module.search([('name', '=', 'nodux_account_withholding_in_ec'), ('state', '=', 'installed')])
            for m in module_w:
                module = m
            if module:
                #if self.party.aplica_retencion == True:
                move_lines += self._get_move_line_invoice_withholding()

        total = Decimal('0.0')
        total_currency = Decimal('0.0')
        for line in move_lines:
            total += line['debit'] - line['credit']
            if line['amount_second_currency']:
                total_currency += line['amount_second_currency'].copy_sign(
                    line['debit'] - line['credit'])
        total = self.currency.round(total)

        term_lines = self.payment_term.compute(total, self.company.currency,
            self.invoice_date)
        remainder_total_currency = total_currency
        if not term_lines:
            term_lines = [(Date.today(), total)]
        for date, amount in term_lines:
            val = self._get_move_line(date, amount)
            if val['amount_second_currency']:
                remainder_total_currency += val['amount_second_currency']
            move_lines.append(val)
        if not self.currency.is_zero(remainder_total_currency):
            move_lines[-1]['amount_second_currency'] -= \
                remainder_total_currency

        accounting_date = self.accounting_date or self.invoice_date
        period_id = Period.find(self.company.id, date=accounting_date)

        move, = Move.create([{
                    'journal': self.journal.id,
                    'period': period_id,
                    'date': accounting_date,
                    'origin': str(self),
                    'lines': [('create', move_lines)],
                    }])
        self.write([self], {
                'move': move.id,
                })
        if self.type == 'in_invoice':
            if module:
                if self.no_generate_withholding == True:
                    pass
                else:
                    Withholding = Pool().get('account.withholding')
                    withholdings = Withholding.search([('number', '=', self.ref_withholding)])
                    for w in withholdings:
                        withholding = w
                    withholding.write([withholding], {
                        'move': move.id,
                        'ref_invoice':self.id,
                        })
        return move

class InvoiceLine(ModelSQL, ModelView):
    'Invoice Line'
    __name__ = 'account.invoice.line'

    @classmethod
    def __setup__(cls):
        super(InvoiceLine, cls).__setup__()
        cls.unit_price.digits = (16, 6)
        cls.amount.digits = (16, 6)

    @fields.depends('type', 'quantity', 'unit_price',
        '_parent_invoice.currency', 'currency')
    def on_change_with_amount(self):
        if self.type == 'line':
            currency = (self.invoice.currency if self.invoice
                else self.currency)
            amount = (Decimal(str(self.quantity or '0.0'))
                * (self.unit_price or Decimal('0.0')))
            if currency:
                new_amount = Decimal(str(round(amount, 4)))
                return new_amount
            return amount
        return Decimal('0.0')
