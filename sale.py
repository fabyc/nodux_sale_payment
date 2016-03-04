# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
from trytond.model import ModelView, fields, ModelSQL
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, Not
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond import backend

__all__ = ['SalePaymentForm',  'WizardSalePayment', 'Sale']
__metaclass__ = PoolMeta
_ZERO = Decimal('0.0')

class Sale():
    __name__ = 'sale.sale'
    
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
    fecha_deposito = fields.Date('Fecha de Deposito', states={
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
        print "Los sales ",sales
        for sale in sales:
            print "Los sales ",sale
            if sale.state == 'draft':
                cls.process([sale])
            if sale.state == 'quotation':
                cls.confirm([sale])
            if sale.state == 'confirmed':
                cls.process([sale])
            print "Los sales ",sale
            if not sale.invoices and sale.invoice_method == 'order':
                cls.raise_user_error('not_customer_invoice')

            grouping = getattr(sale.party, 'sale_invoice_grouping_method',
                False)
            if sale.invoices and not grouping:
                print "Donde debe hacer la factura", sale.invoices
                for invoice in sale.invoices:
                    print "por cada factura", invoice
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
                    print "Aqui esta haciendo el proceso de tpv", invoice
            if sale.is_done():
                cls.do([sale])


class SalePaymentForm(ModelView, ModelSQL):
    'Sale Payment Form'
    __name__ = 'sale.payment.form'

    recibido = fields.Numeric('Valor recibido del cliente', help = "Ingrese el valor de dinero que reciba del cliente",
        digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits'])
     
    cambio = fields.Function(fields.Numeric('SU CAMBIO'),'on_change_with_recibido')
    
    """
    cambio = fields.Function(fields.Numeric('SU CAMBIO'),'on_change_with_recibido')
    tipo_p = fields.Function(fields.Char('Tipo de Pago'),'on_change_with_journal')
    cambio = fields.Numeric('SU CAMBIO')
    """
    tipo_p = fields.Selection([
            ('',''),
            ('efectivo','Efectivo'),
            ('tarjeta','Tarjeta de Debito'),
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
    fecha_deposito = fields.Date('Fecha de Deposito', states={
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
     
    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor
        table = TableHandler(cursor, cls, module_name)
        super(SalePaymentForm, cls).__register__(module_name)
        # Migration from 2.4: drop required on sequence
        table.not_null_action('sequence', action='remove')
          
    @fields.depends('recibido', 'payment_amount')
    def on_change_with_recibido(self, name=None):
        if self.recibido and self.payment_amount:
            cambio = (self.recibido) - (self.payment_amount)
            return cambio

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
        #salep.save_values()
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
        form.on_change_with_recibido()
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
            sale.recibido = form.recibido
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
            sale.save()
         
        if form.tipo_p == 'tarjeta':
            sale.tipo_p = form.tipo_p
            sale.numero_tarjeta = form.numero_tarjeta
            sale.lote = form.lote
            sale.tipo_tarjeta = form.tipo_tarjeta
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
        
        sale.description = sale.reference
        sale.save()
        Sale.workflow_to_end([sale])
        
        if sale.total_amount != sale.paid_amount:
            return 'end'
        if sale.state != 'draft':
            return 'end'
        
        
        return 'end'

       
    
