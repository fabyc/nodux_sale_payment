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
from trytond.transaction import Transaction

__all__ = ['SalePaymentForm',  'WizardSalePayment', 'Sale']
__metaclass__ = PoolMeta
_ZERO = Decimal('0.0')
PRODUCT_TYPES = ['goods']


tipoPago = {
    '': '',
    'efectivo': 'Efectivo',
    'tarjeta': 'Tarjeta de Credito',
    'deposito': 'Deposito',
    'cheque': 'Cheque',
}

class Sale():
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
    fecha_deposito = fields.Date('Fecha deposito', states={
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
    tipo_tarjeta = fields.Selection([
            ('',''),
            ('visa','VISA'),
            ('mastercard','MASTERCARD'),
            ],'Tipo de Tarjeta.', states={
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
                    
                'wizard_sale_payment': {
                    'invisible':Eval('paid_amount', 'total_amount')
                    },
                    
                'wizard_add_product': {
                    'invisible':Eval('paid_amount', 'total_amount')
                    },
                })
        cls.payment_term.states['readonly'] |= Eval('paid_amount')
        cls.payment_term.depends.append('paid_amount')
        cls.lines.states['readonly'] |= Eval('paid_amount')
        cls.lines.depends.append('paid_amount')
        cls.self_pick_up.states['readonly'] |= Eval('paid_amount')
        cls.self_pick_up.depends.append('paid_amount')
        cls.acumulativo.states['readonly'] |= Eval('paid_amount')
                
    @staticmethod
    def default_sale_date():
        Date = Pool().get('ir.date')
        date = Date.today()
        return date

    @classmethod
    def get_amount(cls, sales, names):
        untaxed_amount = {}
        tax_amount = {}
        total_amount = {}
        pool = Pool()
        subtotal_12 = {}
        subtotal_0 = {}
        sub12= Decimal(0.0)
        sub0= Decimal(0.0)
        
        if {'tax_amount', 'total_amount'} & set(names):
            compute_taxes = True
        else:
            compute_taxes = False
        # Sort cached first and re-instanciate to optimize cache management
        sales = sorted(sales, key=lambda s: s.state in cls._states_cached,
            reverse=True)
        sales = cls.browse(sales)
        
        Taxes1 = pool.get('product.category-customer-account.tax')
        Taxes2 = pool.get('product.template-customer-account.tax')
        
        for sale in sales:
            if (sale.state in cls._states_cached
                    and sale.untaxed_amount_cache is not None
                    and sale.tax_amount_cache is not None
                    and sale.total_amount_cache is not None):
                untaxed_amount[sale.id] = sale.untaxed_amount_cache
                if compute_taxes:
                    tax_amount[sale.id] = sale.tax_amount_cache
                    total_amount[sale.id] = sale.total_amount_cache
                for line in sale.lines:
                    taxes1 = Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                        
                    if taxes1:
                        for t in taxes1:
                            if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                                sub12= sub12 + (line.amount)
                            elif str('{:.0f}'.format(t.tax.rate*100)) == '0':
                                sub0 = sub0 + (line.amount)
                    elif taxes2:
                        for t in taxes2:
                            if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                                sub12= sub12 + (line.amount)
                            if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                                sub0 = sub0 + (line.amount)
                        
                    elif taxes3:
                        for t in taxes3:
                            if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                                sub12= sub12 + (line.amount)
                            if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                                sub0 = sub0 + (line.amount)
                
                    subtotal_12[sale.id] = sub12
                    subtotal_0[sale.id] = sub0
            else:
                untaxed_amount[sale.id] = sum(
                    (line.amount for line in sale.lines
                        if line.type == 'line'), _ZERO)
                if compute_taxes:
                    tax_amount[sale.id] = sale.get_tax_amount()
                    total_amount[sale.id] = (
                        untaxed_amount[sale.id] + tax_amount[sale.id])
                for line in sale.lines:
                    taxes1 = Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                        
                    if taxes1:
                        for t in taxes1:
                            if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                                sub12= sub12 + (line.amount)
                            elif str('{:.0f}'.format(t.tax.rate*100)) == '0':
                                sub0 = sub0 + (line.amount)
                    elif taxes2:
                        for t in taxes2:
                            if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                                sub12= sub12 + (line.amount)
                            if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                                sub0= sub0 + (line.amount)
                        
                    elif taxes3:
                        for t in taxes3:
                            if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                                sub12= sub12 + (line.amount)
                            if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                                sub0= sub0 + (line.amount)
                                
                    subtotal_12[sale.id] = sub12
                    subtotal_0[sale.id] = sub0
                    
        result = {
            'untaxed_amount': untaxed_amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'subtotal_0':subtotal_0,
            'subtotal_12':subtotal_12,
            }
            
        for key in result.keys():
            if key not in names:
                del result[key]
        return result
        
    @fields.depends('lines', 'currency', 'party')
    def on_change_lines(self):
        pool = Pool()
        Tax = pool.get('account.tax')
        Invoice = pool.get('account.invoice')
        Configuration = pool.get('account.configuration')
        sub12 = Decimal(0.0)
        sub0= Decimal(0.0)
        config = Configuration(1)

        changes = {
            'untaxed_amount': Decimal('0.0'),
            'tax_amount': Decimal('0.0'),
            'total_amount': Decimal('0.0'),
            'subtotal_12': Decimal('0.0'),
            'subtotal_0': Decimal('0.0'),
            }

        if self.lines:
            context = self.get_tax_context()
            taxes = {}
            
            for line in self.lines:
                if  line.taxes:
                    for t in line.taxes:
                        if str('{:.0f}'.format(t.rate*100)) == '12':
                            sub12= sub12 + (line.amount)
                        elif str('{:.0f}'.format(t.rate*100)) == '0':
                            sub0 = sub0 + (line.amount)
                
                changes['subtotal_12'] = sub12
                changes['subtotal_0'] = sub0
            def round_taxes():
                if self.currency:
                    for key, value in taxes.iteritems():
                        taxes[key] = self.currency.round(value)

            for line in self.lines:
                if getattr(line, 'type', 'line') != 'line':
                    continue
                changes['untaxed_amount'] += (getattr(line, 'amount', None)
                    or Decimal(0))

                with Transaction().set_context(context):
                    tax_list = Tax.compute(getattr(line, 'taxes', []),
                        getattr(line, 'unit_price', None) or Decimal('0.0'),
                        getattr(line, 'quantity', None) or 0.0)
                for tax in tax_list:
                    key, val = Invoice._compute_tax(tax, 'out_invoice')
                    if key not in taxes:
                        taxes[key] = val['amount']
                    else:
                        taxes[key] += val['amount']
                if config.tax_rounding == 'line':
                    round_taxes()
            if config.tax_rounding == 'document':
                round_taxes()
            changes['tax_amount'] = sum(taxes.itervalues(), Decimal('0.0'))
        if self.currency:
            changes['untaxed_amount'] = self.currency.round(
                changes['untaxed_amount'])
            changes['tax_amount'] = self.currency.round(changes['tax_amount'])
        changes['total_amount'] = (changes['untaxed_amount']
            + changes['tax_amount'])
        if self.currency:
            changes['total_amount'] = self.currency.round(
                changes['total_amount'])
        return changes
                   
    @classmethod
    @ModelView.button
    def process(cls, sales):
        done = []
        process = []
        for sale in sales:
            sale.create_invoice('out_invoice')
            sale.create_invoice('out_credit_note')
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
                cls.process([sale])
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
    'Sale Payment Form'
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
    """
    tipo_p = fields.Function(fields.Char('Tipo de Pago'),'on_change_with_journal')
    """
    tipo_p =fields.Selection([
            ('',''), 
            ('efectivo','Efectivo'),
            ('tarjeta','Tarjeta de Credito'),
            ('deposito','Deposito'),
            ('cheque','Cheque'),
            ],'Forma de Pago', readonly=True)
    #forma de pago-> cheque
    banco =  fields.Many2One('bank', 'Banco', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    numero_cuenta = fields.Char('Numero de cuenta', states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'cheque',
                })
    fecha_deposito_cheque = fields.Date('Fecha de Deposito', states={
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
    tipo_tarjeta = fields.Selection([
            ('',''),
            ('visa','VISA'),
            ('mastercard','MASTERCARD'),
            ],'Tipo de Tarjeta.', states={
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
        
     
    @fields.depends('payment_amount', 'recibido')
    def on_change_recibido(self):
        if self.recibido and self.payment_amount:
            cambio = Decimal(0.0)
            cambio = (self.recibido) - (self.payment_amount)
            result = {}
            result['cambio_cliente'] = cambio
        return result
            
    @fields.depends('journal')
    def on_change_journal(self):
        if self.journal:
            pool = Pool()
            Statement=pool.get('account.statement')
            statement = Statement.search([('journal', '=', self.journal.id)])
            for s in statement:
                result = {}
                result['tipo_p'] = s.tipo_pago
        return result
            
    @staticmethod
    def default_cambio_cliente():
        return Decimal(0.0)    
    
class WizardSalePayment(Wizard):
    'Wizard Sale Payment'
    __name__ = 'sale.payment'  
    
    @classmethod
    def __setup__(cls):
        super(WizardSalePayment, cls).__setup__()
        cls._error_messages.update({
                'not_tipo_p': ('No ha configurado el tipo de pago. Dirijase a: \n->Todos los estados de cuenta (Seleeccione el estado de cuenta) \n->Forma de pago.'),
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
        print "La sale device ", sale_device
        Statement=pool.get('account.statement')
        if sale_device.journal:
            statement = Statement.search([('journal', '=', sale_device.journal.id)])
        else:
            self.raise_user_error('No se ha creado un estado de cuenta para %s', (sale_device.name))
        
        if not sale.check_enough_stock():
            return

        Product = Pool().get('product.product')
        if sale.lines:
            # get all products
            products = []
            locations = [sale.warehouse.id]
            for line in sale.lines:
                if not line.product or line.product.type not in PRODUCT_TYPES:
                    continue
                if line.product not in products:
                    products.append(line.product)
            print "Las locaciones ", locations
            # get quantity
            with Transaction().set_context(locations=locations):
                quantities = Product.get_quantity(
                    products,
                    sale.get_enough_stock_qty(),
                    )
            
            # check enough stock
            for line in sale.lines:
                if line.product and line.product.id in quantities:
                    qty = quantities[line.product.id]
                print "la qty ", qty
                if qty < line.quantity:
                    line.raise_user_warning('not_enough_stock_%s' % line.id,
                           'No hay suficiente stock del producto: "%s"'
                        'en la bodega "%s", para realizar esta venta.', (line.product.name, sale.warehouse.name))
                    # update quantities
                    quantities[line.product.id] = qty - line.quantity
    
        for s in statement:
            tipo_p = s.tipo_pago
        if tipo_p :
            pass
        else:
            self.raise_user_error('not_tipo_p')
            
        if user.id != 0 and not sale_device:
            self.raise_user_error('not_sale_device')
        term_lines = sale.payment_term.compute(sale.total_amount, sale.company.currency,
            sale.sale_date)
        if not term_lines:
            term_lines = [(Date.today(), total)]
        
        for date, amount in term_lines:
            if date == Date.today():
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
       
        print "tipo de pago" , tipo_p
        return {
            'journal': sale_device.journal.id
                if sale_device.journal else None,
            'journals': [j.id for j in sale_device.journals],
            'payment_amount': to_pay,
            'currency_digits': sale.currency_digits,
            'party': sale.party.id,
            'tipo_p':tipo_p,
            }     
        """
        if sale_device:
            default = {}
            default['journal'] = sale_device.journal.id if sale_device.journal else None,
            default['payment_amount'] = sale.total_amount - sale.paid_amount if sale.paid_amount else sale.total_amount
            default['currency_digits']= sale.currency_digits
            default['party']= sale.party.id
            return default
        """    
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
        if form.tipo_p == 'cheque':
            sale.tipo_p = form.tipo_p
            sale.banco = form.banco
            sale.numero_cuenta = form.numero_cuenta
            sale.fecha_deposito= form.fecha_deposito
            sale.titular = form.titular
            sale.numero_cheque = form.numero_cheque
            sale.save()
            
        if form.tipo_p == 'deposito':
            sale.tipo_p = form.tipo_p
            sale.banco_deposito = form.banco_deposito
            sale.numero_cuenta_deposito = form.numero_cuenta_deposito
            sale.fecha_deposito = form.fecha_deposito
            sale.numero_deposito= form.numero_deposito
         
        if form.tipo_p == 'tarjeta':
            sale.tipo_p = form.tipo_p
            sale.numero_tarjeta = form.numero_tarjeta
            sale.lote = form.lote
            sale.tipo_tarjeta = form.tipo_tarjeta
        
        if form.tipo_p == 'efectivo':
            sale.recibido = form.recibido
            sale.cambio = form.cambio_cliente
            
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
            InvoiceReport = Pool().get('account.invoice', type='report')
            print_ = StateAction('account_invoice.report_invoice') 
            for i in invoices:
                invoice = i
            resultado = InvoiceReport.execute([invoice.id], {})
            
            if sale.total_amount != sale.paid_amount:
                return 'print_'
                return 'end'
            if sale.state != 'draft':
                return 'print_'
                return 'end'
        else:
            if sale.total_amount != sale.paid_amount:
                return 'start'
            if sale.state != 'draft':
                return 'end'
            return 'print'
            sale.description = sale.reference
            sale.save()

            Sale.workflow_to_end([sale])
        
        return 'end'
        

