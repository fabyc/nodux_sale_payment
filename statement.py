# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard
from decimal import Decimal

__all__ = ['Statement', 'OpenStatement', 'CloseStatement']
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

class OpenStatement():
    'Open Statement'
    __name__ = 'open.statement'

    def transition_create_(self):
        pool = Pool()
        User = pool.get('res.user')
        Statement = pool.get('account.statement')
        Journal = pool.get('account.statement.journal')
        Device = pool.get('sale.device')
        user = Transaction().user
        user = User(user)
        devices = Device.search([('id', '>', 0)])
        result = ''
        for device in devices:
            journals = [j.id for j in device.journals]
            statements = Statement.search([
                    ('journal', 'in', journals),
                    ], order=[
                    ('date', 'ASC'),
                    ])
            journals_of_draft_statements = [s.journal for s in statements
                if s.state == 'draft']
            vlist = []
            for journal in device.journals:
                if journal not in journals_of_draft_statements:
                    name = journal.rec_name.lower()
                    if 'efe' in name:
                        tipo_pago = 'efectivo'
                    if 'tar' in name:
                        tipo_pago = 'tarjeta'
                    if 'dep' in name:
                        tipo_pago = 'deposito'
                    if 'che' in name:
                        tipo_pago = 'cheque'

                    values = {
                        'name': '%s - %s' % (device.rec_name, journal.rec_name),
                        'journal': journal.id,
                        'company': user.company.id,
                        'start_balance': Decimal('0.0'),
                        'end_balance': Decimal('0.0'),
                        'tipo_pago' : tipo_pago,
                        }
                    vlist.append(values)
                    result += self.raise_user_error('open_statement',
                        error_args=(journal.rec_name,),
                        raise_exception=False)
                else:
                    result += self.raise_user_error('statement_already_opened',
                        error_args=(journal.rec_name,),
                        raise_exception=False)

            statements.extend(Statement.create(vlist))
        self.result = result

        return 'done'

class CloseStatement():
    'Close Statement'
    __name__ = 'close.statement'

    def transition_validate(self):
        pool = Pool()
        User = pool.get('res.user')
        Statement = pool.get('account.statement')
        Journal = pool.get('account.statement.journal')
        Device = pool.get('sale.device')
        user = Transaction().user
        user = User(user)
        devices = Device.search([('id', '>', 0)])
        result = ''
        for device in devices:
            journals = [j.id for j in device.journals]
            draft_statements = {
                s.journal: s for s in Statement.search([
                        ('journal', 'in', journals),
                        ], order=[
                        ('create_date', 'ASC'),
                        ])}

            statements = []
            for journal in device.journals:
                statement = draft_statements.get(journal)
                if statement and statement.state == 'draft':
                    end_balance = statement.start_balance
                    for line in statement.lines:
                        end_balance += line.amount
                    statement.end_balance = end_balance
                    statement.save()
                    statements.append(statement)
                    result += self.raise_user_error('close_statement',
                        error_args=(statement.rec_name,),
                        raise_exception=False)
                elif statement:
                    result += self.raise_user_error('statement_already_closed',
                        error_args=(statement.rec_name,),
                        raise_exception=False)
                else:
                    result += self.raise_user_error('not_statement_found',
                        error_args=(journal.rec_name,),
                        raise_exception=False)
            Statement.validate_statement(statements)
            Statement.post(statements)
        self.result = result

        return 'done'
