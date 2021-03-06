# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
#! -*- coding: utf8 -*-
from decimal import Decimal
from trytond.model import ModelView, fields, ModelSQL, Workflow
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, Not, If, PYSONEncoder, Id
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button, StateAction
from trytond import backend
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
from itertools import groupby, chain
from functools import partial
from trytond.report import Report
from trytond.transaction import Transaction
import os

conversor = None
try:
    from numword import numword_es
    conversor = numword_es.NumWordES()
except:
    print("Warning: Does not possible import numword module!")
    print("Please install it...!")

__all__ = ['Card', 'SalePaymentForm',  'WizardSalePayment', 'Sale', 'InvoiceReportPos', 'ReturnSale']

_ZERO = Decimal('0.0')
PRODUCT_TYPES = ['goods']


tipoPago = {
    '': '',
    'efectivo': 'Efectivo',
    'tarjeta': 'Tarjeta de Credito',
    'deposito': 'Deposito',
    'cheque': 'Cheque',
}

class Card(ModelSQL, ModelView):
    'card'
    __name__ = 'sale.card'
    name = fields.Char('Tarjeta de credito', required=True)
    banco =  fields.Many2One('bank', 'Banco', states={
                'readonly': ~Eval('active', True),
                })

    @classmethod
    def __setup__(cls):
        super(Card, cls).__setup__()

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('banco',) + tuple(clause[1:]),
            (cls._rec_name,) + tuple(clause[1:]),
            ]

    def get_rec_name(self, name):
        if self.banco:
            return self.name + ' - ' + self.banco.party.name
        else:
            return self.name

class Sale():
    __metaclass__ = PoolMeta
    __name__ = 'sale.sale'
    acumulativo = fields.Boolean ('Plan acumulativo', help = "Seleccione si realizara un plan acumulativo",  states={
                'readonly': ~Eval('active', True),
                })

    tipo_p = fields.Char('Tipo de Pago')

    recibido = fields.Numeric('Valor recibido del cliente',
        digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'])

    cambio = fields.Numeric('CAMBIO',
        digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'])

    banco =  fields.Many2One('bank', 'Banco', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    numero_cuenta = fields.Char('Numero de cuenta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    fecha_deposito = fields.Date('Fecha de cheque', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    titular = fields.Char('Titular de la cuenta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    numero_cheque = fields.Char('Numero de Cheque', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    #forma de pago-> tarjeta
    numero_tarjeta = fields.Char('Numero de tarjeta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'tarjeta',
                })
    lote = fields.Char('Numero de lote', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'tarjeta',
                })
    tarjeta = fields.Many2One('sale.card', 'Tarjeta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'tarjeta',
                })
    #forma de pago -> banco_deposito numero_cuenta_deposito fecha_deposito numero_deposito
    banco_deposito =  fields.Many2One('bank', 'Banco', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    numero_cuenta_deposito = fields.Char('Numero de cuenta de Deposito', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    fecha_deposito = fields.Date('Fecha de Deposito', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    numero_deposito = fields.Char('Numero de Deposito', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls._buttons.update({
                'print_ticket': {
                    'invisible':~Eval('acumulativo', False)
                    },
                })

    @fields.depends('acumulativo', 'party')
    def on_change_acumulativo(self):
        if self.acumulativo:
            if self.acumulativo == True and self.party.code == '9999999999999':
                self.acumulativo = False

    def get_amount2words(self, value):
        if conversor:
            return (conversor.cardinal(int(value))).upper()
        else:
            return ''

    @classmethod
    def get_paid_amount(cls, sales, names):
        pool = Pool()

        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        InvoiceAccountMoveLine = pool.get('account.invoice-account.move.line')
        amount_unreconciled = Decimal(0.0)
        amount = Decimal(0.0)
        id_i = None
        result = {n: {s.id: Decimal(0) for s in sales} for n in names}

        for name in names:
            for sale in sales:
                amount_unreconciled = Decimal(0.0)
                amount = Decimal(0.0)
                invoices = Invoice.search([('description','=', sale.reference), ('description', '!=', None)])
                if invoices:
                    for i in invoices:
                        invoice = i.number
                    move_lines = MoveLine.search([
                            ('description', '=', invoice),
                        ])
                    for line in move_lines:
                        amount += line.credit
                if sale.payments:
                    for payment in sale.payments:
                        amount += payment.amount

                if amount:
                    result[name][sale.id] = amount
                else:
                    for payment in sale.payments:
                        result[name][sale.id] += payment.amount
        return result

    @classmethod
    def get_residual_amount(cls, sales, names):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        InvoiceAccountMoveLine = pool.get('account.invoice-account.move.line')
        amount_unreconciled = Decimal(0.0)
        amount = Decimal(0.0)
        original = Decimal(0.0)
        id_i = None
        result = {n: {s.id: Decimal(0) for s in sales} for n in names}
        for name in names:
            for sale in sales:
                amount_unreconciled = Decimal(0.0)
                amount = Decimal(0.0)
                invoices = Invoice.search([('description','=', sale.reference), ('description', '!=', None), ('description', '!=', '')])
                if invoices:
                    for i in invoices:
                        invoice = i.number
                    move_lines = MoveLine.search([
                            ('description', '=', invoice),
                        ])
                    for line in move_lines:
                        amount += line.credit

                if sale.total_amount:
                    original = sale.total_amount

                if sale.payments:
                    for payment in sale.payments:
                        amount += payment.amount
                if amount:
                    result[name][sale.id] = original - amount
                else:
                    result[name][sale.id] = sale.total_amount - sale.paid_amount
        return result

    @classmethod
    @ModelView.button
    def process(cls, sales):
        done = []
        process = []
        for sale in sales:
            sale.create_invoice()
            sale.set_invoice_state()
            sale.create_shipment('out')
            sale.create_shipment('return')
            sale.set_shipment_state()
            if sale.is_done():
                if sale.state != 'done':
                    done.append(sale)
            elif sale.state != 'processing':
                process.append(sale)
        if process:
            cls.proceed(process)
        if done:
            cls.do(done)

    @classmethod
    def workflow_to_end(cls, sales):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')
        for sale in sales:
            if sale.state == 'draft':
                cls.quote([sale])
            if sale.state == 'quotation':
                cls.confirm([sale])
            if sale.state == 'confirmed':
                cls.process([sale])
            if not sale.invoices and sale.invoice_method == 'order':
                cls.raise_user_error('not_customer_invoice')

            grouping = getattr(sale.party, 'sale_invoice_grouping_method',
                False)
            if sale.invoices and not grouping:
                for invoice in sale.invoices:
                    if invoice.state == 'draft':
                        if not getattr(invoice, 'invoice_date', False):
                            invoice.invoice_date = Date.today()
                        if not getattr(invoice, 'accounting_date', False):
                            invoice.accounting_date = Date.today()
                        invoice.description = sale.reference
                        invoice.save()
                Invoice.post(sale.invoices)
                for payment in sale.payments:
                    invoice = sale.invoices[0]
                    payment.invoice = invoice.id
                    # Because of account_invoice_party_without_vat module
                    # could be installed, invoice party may be different of
                    # payment party if payment party has not any vat
                    # and both parties must be the same
                    if payment.party != invoice.party:
                        payment.party = invoice.party
                    payment.save()
            if sale.is_done():
                cls.do([sale])

class SalePaymentForm():
    __metaclass__ = PoolMeta
    __name__ = 'sale.payment.form'

    recibido = fields.Numeric('Valor recibido del cliente', help = "Ingrese el monto de dinero que reciba del cliente",
        digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'], states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'efectivo',
                } )
    cambio_cliente =fields.Numeric('SU CAMBIO', readonly=True, digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'], states={
                'invisible': Eval('tipo_p') != 'efectivo',
                })
    tipo_p =fields.Selection([
            ('',''),
            ('efectivo','Efectivo'),
            ('tarjeta','Tarjeta de Credito'),
            ('deposito','Deposito'),
            ('cheque','Cheque'),
            ],'Forma de Pago', readonly=True)
    banco =  fields.Many2One('bank', 'Banco', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    numero_cuenta = fields.Char('Numero de cuenta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    fecha_deposito_cheque = fields.Date('Fecha de Cheque', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    titular = fields.Char('Titular de la cuenta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    numero_cheque = fields.Char('Numero de Cheque', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    #forma de pago-> tarjeta
    numero_tarjeta = fields.Char('Numero de tarjeta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'tarjeta',
                })
    lote = fields.Char('Numero de lote', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'tarjeta',
                })
    tarjeta = fields.Many2One('sale.card', 'Tarjeta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'tarjeta',
                })
    #forma de pago -> banco_deposito numero_cuenta_deposito fecha_deposito numero_deposito
    banco_deposito =  fields.Many2One('bank', 'Banco', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    numero_cuenta_deposito = fields.Char('Numero de cuenta de Deposito', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    fecha_deposito = fields.Date('Fecha de Deposito', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    numero_deposito = fields.Char('Numero de Deposito', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'deposito',
                })
    amount = fields.Numeric('Payment amount', required=True,
        digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'])

    @classmethod
    def __setup__(cls):
        super(SalePaymentForm, cls).__setup__()

    @fields.depends('payment_amount', 'recibido')
    def on_change_recibido(self):
        cambio = Decimal(0.0)
        if self.recibido and self.payment_amount:
            cambio = Decimal(0.0)
            cambio = (self.recibido) - (self.payment_amount)
        self.cambio_cliente = cambio

    @fields.depends('journal', 'party')
    def on_change_journal(self):
        if self.journal:
            pool = Pool()
            Statement=pool.get('account.statement')
            statement = Statement.search([('journal', '=', self.journal.id)])

            if statement:
                for s in statement:
                    self.tipo_p = s.tipo_pago
                    tipo_p = s.tipo_pago
                if tipo_p :
                    pass
                else:
                    self.raise_user_error('No ha configurado el tipo de pago. \n-Seleccione el estado de cuenta en "Todos los estados de cuenta" \n-Seleccione forma de pago.')
            else:
                 self.raise_user_error('No ha creado el estado de cuenta para el punto de venta')
            if tipo_p == 'cheque':
                titular = self.party.name
                self.titular = titular

    @staticmethod
    def default_cambio_cliente():
        return Decimal(0.0)

class WizardSalePayment(Wizard):
    __metaclass__ = PoolMeta
    __name__ = 'sale.payment'
    print_ = StateAction('nodux_sale_payment.report_invoice_pos')

    @classmethod
    def __setup__(cls):
        super(WizardSalePayment, cls).__setup__()
        cls._error_messages.update({
                'not_tipo_p': ('No ha configurado el tipo de pago. \n-Seleccione el estado de cuenta en "Todos los estados de cuenta" \n-Seleccione forma de pago.'),
                })

    def default_start(self, fields):
        pool = Pool()
        Sale = pool.get('sale.sale')
        User = pool.get('res.user')
        SaleP = pool.get('sale.payment.form')
        sale = Sale(Transaction().context['active_id'])
        user = User(Transaction().user)
        sale_device = sale.sale_device or user.sale_device or False
        Date = pool.get('ir.date')
        Statement=pool.get('account.statement')

        ModelData = pool.get('ir.model.data')
        User = pool.get('res.user')
        Group = pool.get('res.group')
        origin = str(sale)
        def in_group():

            group = Group(ModelData.get_id('nodux_sale_payment',
                    'group_stock_force'))
            transaction = Transaction()
            user_id = transaction.user
            if user_id == 0:
                user_id = transaction.context.get('user', user_id)
            if user_id == 0:
                return True
            user = User(user_id)
            return origin and group in user.groups

        if sale_device.journal:
            statement = Statement.search([('journal', '=', sale_device.journal.id), ('state', '=', 'draft')], order=[('date', 'DESC')])
        else:
            self.raise_user_error('No se ha definido un libro diario por defecto para %s', sale_device.name)

        if statement :
            for s in statement:
                tipo_p = s.tipo_pago
            if tipo_p :
                pass
            else:
                self.raise_user_error('not_tipo_p')
        else:
             self.raise_user_error('No ha creado un estado de cuenta para %s ', sale_device.name)


        if not sale.check_enough_stock():
            return

        Product = Pool().get('product.product')

        if sale.acumulativo == True:
            pass
        else:
            if sale.lines:
                # get all products
                products = []
                locations = [sale.warehouse.id]
                for line in sale.lines:
                    if not line.product or line.product.type not in PRODUCT_TYPES:
                        continue
                    if line.product not in products:
                        products.append(line.product)
                # get quantity
                with Transaction().set_context(locations=locations):
                    quantities = Product.get_quantity(
                        products,
                        sale.get_enough_stock_qty(),
                        )

                # check enough stock
                for line in sale.lines:
                    if line.product.type not in PRODUCT_TYPES:
                        continue
                    else:
                        if line.product and line.product.id in quantities:
                            qty = quantities[line.product.id]
                        if qty < line.quantity:
                            if not in_group():
                                self.raise_user_error('No hay suficiente stock del producto: \n %s \n en la bodega %s', (line.product.name, sale.warehouse.name))

                            line.raise_user_warning('not_enough_stock_%s' % line.id,
                                   'No hay suficiente stock del producto: "%s"'
                                'en la bodega "%s", para realizar esta venta.', (line.product.name, sale.warehouse.name))
                            # update quantities
                            quantities[line.product.id] = qty - line.quantity

        if user.id != 0 and not sale_device:
            self.raise_user_error('not_sale_device')

        term_lines = sale.payment_term.compute(sale.total_amount, sale.company.currency,
            sale.sale_date)
        total = sale.total_amount
        if not term_lines:
            term_lines = [(Date.today(), total)]

        if sale.paid_amount:
            payment_amount = sale.total_amount - sale.paid_amount
        else:
            payment_amount = sale.total_amount

        for date, amount in term_lines:
            if date == Date.today():
                if amount < 0 :
                    amount *=-1
                payment_amount = amount

        if sale.paid_amount:
            amount = sale.total_amount - sale.paid_amount
        else:
            amount = sale.total_amount

        if payment_amount < amount:
            to_pay = payment_amount
        elif payment_amount > amount:
            to_pay = amount

        else:
            to_pay= amount

        return {
            'journal': sale_device.journal.id
                if sale_device.journal else None,
            'journals': [j.id for j in sale_device.journals],
            'payment_amount': to_pay,
            'currency_digits': sale.currency_digits,
            'party': sale.party.id,
            'tipo_p':tipo_p,
            }

    def transition_pay_(self):
        pool = Pool()
        Date = pool.get('ir.date')
        Sale = pool.get('sale.sale')
        Statement = pool.get('account.statement')
        StatementLine = pool.get('account.statement.line')
        form = self.start
        statements = Statement.search([
                ('journal', '=', form.journal),
                ('state', '=', 'draft'),
                ], order=[('date', 'DESC')])
        if not statements:
            self.raise_user_error('not_draft_statement', (form.journal.name,))

        active_id = Transaction().context.get('active_id', False)
        sale = Sale(active_id)
        if sale.self_pick_up == False:
            sale.create_shipment('out')
            sale.set_shipment_state()
        date = Pool().get('ir.date')
        date = date.today()
        if form.payment_amount == 0 and form.party.vat_code == '9999999999999':
            self.raise_user_error('No se puede dar credito a consumidor final, monto a pagar no puede ser %s', form.payment_amount)

        if form.tipo_p == 'cheque':
            sale.tipo_p = form.tipo_p
            sale.banco = form.banco
            sale.numero_cuenta = form.numero_cuenta
            sale.fecha_deposito= form.fecha_deposito
            sale.titular = form.titular
            sale.numero_cheque = form.numero_cheque
            sale.sale_date = date
            sale.save()

        if form.tipo_p == 'deposito':
            sale.tipo_p = form.tipo_p
            sale.banco_deposito = form.banco_deposito
            sale.numero_cuenta_deposito = form.numero_cuenta_deposito
            sale.fecha_deposito = form.fecha_deposito
            sale.numero_deposito= form.numero_deposito
            sale.sale_date = date
            sale.save()

        if form.tipo_p == 'tarjeta':
            sale.tipo_p = form.tipo_p
            sale.numero_tarjeta = form.numero_tarjeta
            sale.lote = form.lote
            sale.tarjeta = form.tarjeta
            sale.sale_date = date
            sale.save()

        if form.tipo_p == 'efectivo':
            sale.tipo_p = form.tipo_p
            sale.recibido = form.recibido
            sale.cambio = form.cambio_cliente
            sale.sale_date = date
            sale.save()

        if not sale.reference:
            Sale.set_reference([sale])

        account = (sale.party.account_receivable
            and sale.party.account_receivable.id
            or self.raise_user_error('party_without_account_receivable',
                error_args=(sale.party.name,)))

        if form.payment_amount:
            payment = StatementLine(
                statement=statements[0].id,
                date=Date.today(),
                amount=form.payment_amount,
                party=sale.party.id,
                account=account,
                description=sale.reference,
                sale=active_id
                )
            payment.save()

        if sale.acumulativo != True:
            sale.description = sale.reference
            sale.save()
            Sale.workflow_to_end([sale])
            Invoice = Pool().get('account.invoice')
            invoices = Invoice.search([('description', '=', sale.description)])

            if sale.total_amount == sale.paid_amount:
                return 'print_'
                return 'end'

            if sale.total_amount != sale.paid_amount:
                return 'print_'
                return 'end'

            if sale.state != 'draft':
                return 'print_'
                return 'end'
        else:
            if sale.total_amount != sale.paid_amount:
                return 'end'
            if sale.state != 'draft':
                return 'end'
            sale.description = sale.reference
            sale.save()

            Sale.workflow_to_end([sale])

        return 'end'

class InvoiceReportPos(Report):
    __name__ = 'nodux_sale_payment.invoice_pos'

    @classmethod
    def get_context(cls, records, data):
        pool = Pool()
        User = pool.get('res.user')
        Invoice = pool.get('account.invoice')
        Sale = pool.get('sale.sale')
        sale = records[0]
        TermLines = pool.get('account.invoice.payment_term.line')
        TermLinesRela = pool.get('account.invoice.payment_term.line.relativedelta')
        invoices = Invoice.search([('description', '=', sale.reference), ('description', '!=', None)])
        cont = 0
        invoice_e = 'false'
        context = Transaction().context

        report_context = super(InvoiceReportPos, cls).get_context(
            records, data)

        if invoices:
            for i in invoices:
                invoice = i
                invoice_e = 'true'
        else:
            invoice_e = 'false'
            invoice = sale
        if sale.tipo_p:
            tipo = (sale.tipo_p).upper()
        else:
            tipo = None
        if sale.payment_term:
            term = sale.payment_term
            termlines = TermLines.search([('payment', '=', term.id)])

            for t in termlines:
                termlinesrela = TermLinesRela.search([('line', '=', t.id)])
                for t_l_r in termlinesrela:
                    t_f = t_l_r
                cont += 1

        if cont == 1 and t_f.days == 0:
            forma = 'CONTADO'
        else:
            forma = 'CREDITO'

        if sale.total_amount:
            d = str(sale.total_amount)
            decimales = d[-2:]
        else:
            decimales='0.0'

        user = User(Transaction().user)
        report_context['user'] = user
        report_context['company'] = user.company
        report_context['invoice'] = invoice
        report_context['invoice_e'] = invoice_e
        report_context['subtotal_0'] = cls._get_subtotal_0(Sale, sale)
        report_context['subtotal_12'] = cls._get_subtotal_12(Sale, sale)
        report_context['subtotal_14'] = cls._get_subtotal_14(Sale, sale)
        report_context['descuento'] = cls._get_descuento(Sale, sale)
        report_context['forma'] = forma
        report_context['tipo'] = tipo
        report_context['amount2words']=cls._get_amount_to_pay_words(Sale, sale)
        report_context['decimales'] = decimales
        report_context['lineas'] = cls._get_lineas(Sale, sale)
        #localcontext['fecha_de_emision']=cls._get_fecha_de_emision(Invoice, invoice)
        return report_context

    @classmethod
    def _get_amount_to_pay_words(cls, Sale, sale):
        amount_to_pay_words = Decimal(0.0)
        if sale.total_amount and conversor:
            amount_to_pay_words = sale.get_amount2words(sale.total_amount)
        return amount_to_pay_words

    @classmethod
    def _get_lineas(cls, Sale, sale):
        cont = 0

        for line in sale.lines:
            cont += 1
        return cont

    @classmethod
    def _get_descuento(cls, Sale, sale):
        descuento = Decimal(0.00)
        descuento_parcial = Decimal(0.00)

        for line in sale.lines:
            descuento_parcial = Decimal(line.product.template.list_price - line.unit_price)
            if descuento_parcial > 0:
                descuento = descuento + descuento_parcial
            else:
                descuento = Decimal(0.00)
        return descuento


    @classmethod
    def _get_subtotal_14(cls, Sale, sale):
        subtotal14 = Decimal(0.00)
        pool = Pool()

        for line in sale.lines:
            if  line.taxes:
                for t in line.taxes:
                    if str('{:.0f}'.format(t.rate*100)) == '14':
                        subtotal14= subtotal14 + (line.amount)
        return subtotal14

    @classmethod
    def _get_subtotal_12(cls, Sale, sale):
        subtotal12 = Decimal(0.00)
        pool = Pool()

        for line in sale.lines:
            if  line.taxes:
                for t in line.taxes:
                    if str('{:.0f}'.format(t.rate*100)) == '12':
                        subtotal12= subtotal12 + (line.amount)
        return subtotal12

    @classmethod
    def _get_subtotal_0(cls, Sale, sale):
        subtotal0 = Decimal(0.00)
        pool = Pool()

        for line in sale.lines:
            if  line.taxes:
                for t in line.taxes:
                    if str('{:.0f}'.format(t.rate*100)) == '0':
                        subtotal0= subtotal0 + (line.amount)
        return subtotal0

class ReturnSale(Wizard):
    __metaclass__ = PoolMeta
    __name__ = 'sale.return_sale'

    start = StateView('sale.return_sale.start',
        'sale.return_sale_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Return', 'return_', 'tryton-ok', default=True),
            #Button('Reversar factura', 'reverse_', 'tryton-ok'),
            ])
    return_ = StateAction('sale.act_sale_form')
    reverse_ = StateAction('sale.act_sale_form')
    def do_return_(self, action):
        Sale = Pool().get('sale.sale')

        sales = Sale.browse(Transaction().context['active_ids'])

        origin = str(sales)
        def in_group():
            pool = Pool()
            ModelData = pool.get('ir.model.data')
            User = pool.get('res.user')
            Group = pool.get('res.group')
            group = Group(ModelData.get_id('nodux_account_ec_pymes',
                        'group_sale_return'))
            transaction = Transaction()
            user_id = transaction.user
            if user_id == 0:
                user_id = transaction.context.get('user', user_id)
            if user_id == 0:
                return True
            user = User(user_id)
            return origin and group in user.groups
        if not in_group():
            self.raise_user_error("No esta autorizado a realizar una devolucion")

        return_sales = Sale.copy(sales)
        for sale in return_sales:
            for line in sale.lines:
                if line.type == 'line':
                    line.quantity *= -1
                    line.save()
        data = {'res_id': [s.id for s in return_sales]}
        if len(return_sales) == 1:
            action['views'].reverse()
        return action, data

    def do_reverse_(self, action):
        Sale = Pool().get('sale.sale')
        sales = Sale.browse(Transaction().context['active_ids'])
        for sale in sales:
            if sale.invoices:
                for s in sale.invoices:
                    if s.state == 'posted':
                        s.state = 'draft'
                        s.save()
            sale.cancel(sales)
