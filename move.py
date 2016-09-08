#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from decimal import Decimal
import datetime
from itertools import groupby

try:
    from sql import Null
except ImportError:
    Null = None

from trytond.model import ModelView, ModelSQL, fields
from trytond.wizard import Wizard, StateTransition, StateView, StateAction, \
    Button
from trytond.report import Report
from trytond.pyson import Eval, Bool, PYSONEncoder
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.rpc import RPC

__all__ = ['Move', 'Line']
__metaclass__ = PoolMeta

class Move(ModelSQL, ModelView):
    'Account Move'
    __name__ = 'account.move'

    @classmethod
    def __setup__(cls):
        super(Move, cls).__setup__()

    @classmethod
    @ModelView.button
    def post(cls, moves):
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Date = pool.get('ir.date')
        Line = pool.get('account.move.line')

        for move in moves:
            amount = Decimal('0.0')
            if not move.lines:
                cls.raise_user_error('post_empty_move', (move.rec_name,))
            company = None
            for line in move.lines:
                amount += line.debit - line.credit
                if not company:
                    company = line.account.company
            if not company.currency.is_zero(amount):
                cls.raise_user_error('post_unbalanced_move', (move.rec_name,))
        for move in moves:
            values = {
                'state': 'posted',
                }
            if not move.post_number:
                values['post_date'] = Date.today()
                values['post_number'] = Sequence.get_id(
                    move.period.post_move_sequence_used.id)
            cls.write([move], values)

            keyfunc = lambda l: (l.party, l.account)
            to_reconcile = [l for l in move.lines
                if ((l.debit == l.credit == Decimal('0'))
                    and l.account.reconcile)]
            to_reconcile = sorted(to_reconcile, key=keyfunc)
            for _, zero_lines in groupby(to_reconcile, keyfunc):
                Line.reconcile(list(zero_lines))

class Line(ModelSQL, ModelView):
    'Account Move Line'
    __name__ = 'account.move.line'

    @classmethod
    def __setup__(cls):
        super(Line, cls).__setup__()
        cls.debit.digits = (16,4)
        cls.credit.digits = (16,4)
