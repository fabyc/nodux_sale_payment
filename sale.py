# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
#! -*- coding: utf8 -*-
from decimal import Decimal
from trytond.model import ModelView, fields, ModelSQL
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, Not
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond import backend
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta

__all__ = ['SalePaymentForm',  'WizardSalePayment', 'Sale', 'AddTermForm', 'WizardAddTerm', 'Payment_Term']
__metaclass__ = PoolMeta
_ZERO = Decimal('0.0')

class Sale():
    __name__ = 'sale.sale'
    acumulativo = fields.Boolean ('Plan acumulativo', help = "Seleccione si realizara un plan acumulativo")
    
    tipo_p = fields.Char('Tipo de Pago')
    
    recibido = fields.Numeric('Valor recibido del cliente',
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
                'wizard_add_term': {
                    'invisible': Eval('state') != 'draft'
                    }
                })
                
    @classmethod
    @ModelView.button_action('nodux_sale_payment.wizard_add_term')
    def wizard_add_term(cls, sales):
        pass
    
    @classmethod
    @ModelView.button
    def process(cls, sales):
        print "Ingresa"
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
    cambio_cliente = fields.Function(fields.Numeric('SU CAMBIO',digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'], states={
                'readonly': ~Eval('active', True),
                'invisible': Eval('tipo_p') != 'efectivo',
                }),'on_change_with_recibido')
    """
    tipo_p = fields.Function(fields.Char('Tipo de Pago'),'on_change_with_journal')
    """
    tipo_p = fields.Selection([
            ('',''), 
            ('efectivo','Efectivo'),
            ('tarjeta','Tarjeta de Credito'),
            ('deposito','Deposito'),
            ('cheque','Cheque'),
            ],'Forma de Pago')
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
        
    @classmethod
    def __setup__(cls):
        super(SalePaymentForm, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))
     
    @fields.depends('payment_amount', 'recibido')
    def on_change_with_recibido(self, name=None):
        if self.recibido and self.payment_amount:
            cambio = Decimal(0.0)
            print "Lo que recibo ***", (self.recibido - self.payment_amount)
            cambio = (self.recibido) - (self.payment_amount)
            print "El cambio", cambio
            return cambio
            
    @staticmethod
    def default_cambio_cliente():
        return Decimal(0.0)    
    
class WizardSalePayment(Wizard):
    'Wizard Sale Payment'
    __name__ = 'sale.payment'  
    
    
    def default_start(self, fields):
        pool = Pool()
        Sale = pool.get('sale.sale')
        User = pool.get('res.user')
        SaleP = pool.get('sale.payment.form')
        sale = Sale(Transaction().context['active_id'])
        user = User(Transaction().user)
        sale_device = sale.sale_device or user.sale_device or False
        Date = pool.get('ir.date')

        if user.id != 0 and not sale_device:
            self.raise_user_error('not_sale_device')
        print "La venta tiene este termino de pago", sale.payment_term
        term_lines = sale.payment_term.compute(sale.total_amount, sale.company.currency,
            sale.sale_date)
        print "Las lineas de termino de pago ",term_lines
        if not term_lines:
            term_lines = [(Date.today(), total)]
        
        for date, amount in term_lines:
            print "Los terminos" ,date, amount
            if date == Date.today():
                payment_amount = amount
        
        if sale.paid_amount:
            print "El valor ", sale.paid_amount
            amount = sale.total_amount - sale.paid_amount  
        else: 
            print "El valor ", sale.paid_amount
            amount = sale.total_amount
        
        print "Valor a pagar ", payment_amount     
        print "el amount ", amount
        if payment_amount < amount:
            print "Es menor "
            to_pay = payment_amount
        elif payment_amount > amount:
            print "Es mayor "
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
            
            if sale.total_amount != sale.paid_amount:
                return 'end'
            if sale.state != 'draft':
                return 'end'
        else:
            if sale.total_amount != sale.paid_amount:
                return 'start'
            if sale.state != 'draft':
                return 'end'

            sale.description = sale.reference
            sale.save()

            Sale.workflow_to_end([sale])
        
        return 'end'

class AddTermForm(ModelView):
    'Add Term Form'
    __name__ = 'nodux_sale_payment.add_term_form'
    
    verifica_dias = fields.Boolean("Credito por dias", help=u"Seleccione si desea realizar su pago en los dias siguientes", states={
            'invisible': Eval('verifica_pagos', True),
            })
    verifica_pagos = fields.Boolean("Credito por pagos", help=u"Seleccione si desea realizar sus pagos mensuales", states={
            'invisible': Eval('verifica_dias', True),
            })
    dias = fields.Numeric("Numero de dias", help=u"Ingrese el numero de dias en los que se realizara el pago", states={
            'invisible': ~Eval('verifica_dias', False),
            })
    pagos = fields.Numeric("Numero de pagos", help=u"Ingrese el numero de pagos en lo que realizara el pago total", states={
            'invisible': ~Eval('verifica_pagos', False),
            })
    creditos = fields.One2Many('sale_payment.payment', 'sale',
        'Formas de Pago')
    efectivo = fields.Numeric('Efectivo')
    cheque = fields.Numeric('Cheque')
    nro= fields.Char('Numero de cheque', size=20)
    banco = fields.Many2One('bank', 'Banco')
    valor = fields.Numeric('Total a pagar')
    
    @fields.depends('dias', 'creditos', 'efectivo', 'cheque', 'verifica_dias', 'valor')
    def on_change_dias(self):
        if self.dias:
            print "El valor es ", self.valor
            pool = Pool()
            Date = pool.get('ir.date')
            Sale = pool.get('sale.sale')
            
            """
            active_id = Transaction().context.get('active_id', False)
            sale = Sale(active_id)
            print "El active_id", active_id
            """
            res = {}
            res['creditos'] = {}
            if self.creditos:
                res['creditos']['remove'] = [x['id'] for x in self.creditos]
                
            if self.efectivo:
                monto_efectivo = self.efectivo
            else:
                monto_efectivo = Decimal(0.0)
            if self.cheque:
                monto_cheque = self.cheque
            else:
                monto_cheque = Decimal(0.0)
            monto_parcial = self.valor -(monto_efectivo + monto_cheque)
            
            dias = timedelta(days=int(self.dias))
            monto = monto_parcial
            fecha = datetime.now() + dias
            result = {
                'fecha': fecha,
                'monto': monto,
            }
            
            res['creditos'].setdefault('add', []).append((0, result))
            print res
            return res          
    
    @fields.depends('pagos', 'creditos', 'efectivo', 'cheque', 'verifica_pagos', 'valor')
    def on_change_pagos(self):
        if self.pagos:
            pool = Pool()
            Date = pool.get('ir.date')
            Sale = pool.get('sale.sale')
            """
            active_id = Transaction().context.get('active_id', False)
            sale = Sale(active_id)
            print "El active_id", active_id
            """
            
            if self.efectivo:
                monto_efectivo = self.efectivo
            else:
                monto_efectivo = Decimal(0.0)
            if self.cheque:
                monto_cheque = self.cheque
            else:
                monto_cheque = Decimal(0.0)
            #monto_parcial = monto_efectivo + monto_cheque
            monto_parcial = self.valor -(monto_efectivo + monto_cheque)
            monto = monto_parcial / self.pagos
            pagos = int(self.pagos)
            
            res = {}
            res['creditos'] = {}
            if self.creditos:
                res['creditos']['remove'] = [x['id'] for x in self.creditos]
            
            for p in range(pagos):
                monto = monto
                fecha = datetime.now() + relativedelta(months=(p+1))
                result = {
                    'fecha': fecha,
                    'monto': monto,
                }
                res['creditos'].setdefault('add', []).append((0, result))
            print res
            return res                        
    #controlar dias y pagos con campo Boolean
                 
class WizardAddTerm(Wizard):
    'Wizard Add Term'
    __name__ = 'nodux_sale_payment.add_term'
    start = StateView('nodux_sale_payment.add_term_form',
        'nodux_sale_payment.add_term_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add_', 'tryton-ok'),
            Button('Imprimir Credito', 'print_', 'tryton-ok'),
        ])
    add_ = StateTransition()
    add_ = StateTransition()
    
    def default_start(self, fields):
        pool = Pool()
        Sale = pool.get('sale.sale')
        default = {}
        sale = Sale(Transaction().context['active_id'])
        default['valor'] = sale.residual_amount
        return default
        
    def transition_add_(self):
        print "Esto es lo que recibe **", self.start.creditos #aqui estan todas las lineas de credito que seran para los asientos contables
        pool = Pool()
        Sale = pool.get('sale.sale')
        active_id = Transaction().context.get('active_id', False)
        sale = Sale(active_id)
        Statement = pool.get('account.statement')
        StatementLine = pool.get('account.statement.line')
        Date = pool.get('ir.date')
        
        statements = Statement.search([
                ('state', '=', 'draft'),
                ], order=[('date', 'DESC')])
        account = (sale.party.account_receivable
            and sale.party.account_receivable.id
            or self.raise_user_error('party_without_account_receivable',
                error_args=(sale.party.name,)))
        
        if self.start.cheque:
            m_ch = self.start.cheque
        else:
            m_ch = Decimal(0.0)
            
        if self.start.efectivo:
            m_e = self.start.efectivo
        else:
            m_e = Decimal(0.0)
        print "Valores que se pagaran" ,m_ch, m_e    
        sale.payment_amount = m_ch + m_e
        sale.save()
        
        valor = m_ch + m_e
        if valor != 0:
            payment = StatementLine(
                    statement=statements[0].id,
                    date=Date.today(),
                    amount=(m_ch + m_e),
                    party=sale.party.id,
                    account=account,
                    description=sale.reference,
                    sale=active_id
                    )
            payment.save()
        Sale.workflow_to_end([sale])
        
        return 'end'
        
class Payment_Term(ModelView):
    'Payment Term Line'
    __name__ = 'sale_payment.payment'
    
    sale = fields.Many2One('sale.sale', 'Sale')
    fecha = fields.Date('Fecha de pago')
    monto = fields.Numeric("Valor a pagar")
    banco = fields.Many2One('bank', 'Banco')
    numero_cuenta = fields.Many2One('bank.account', 'Numero de Cuenta')
    
