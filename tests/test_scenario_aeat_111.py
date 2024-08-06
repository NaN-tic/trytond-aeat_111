import unittest
from decimal import Decimal

from proteus import Model, Wizard
from trytond.modules.account.tests.tools import create_fiscalyear
from trytond.modules.account_invoice.tests.tools import \
    set_fiscalyear_invoice_sequences
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.modules.currency.tests.tools import get_currency
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Activate modules
        activate_modules(['aeat_111', 'account_es', 'account_invoice'])

        # Create company
        eur = get_currency('EUR')
        _ = create_company(currency=eur)
        company = get_company()
        tax_identifier = company.party.identifiers.new()
        tax_identifier.type = 'eu_vat'
        tax_identifier.code = 'ESB01000009'
        company.party.save()

        # Create fiscal year
        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')
        period = fiscalyear.periods[0]

        # Create chart of accounts
        AccountTemplate = Model.get('account.account.template')
        Account = Model.get('account.account')
        account_template, = AccountTemplate.find([('parent', '=', None),
                                                  ('name', 'ilike',
                                                   'Plan General Contable%')])
        create_chart = Wizard('account.create_chart')
        create_chart.execute('account')
        create_chart.form.account_template = account_template
        create_chart.form.company = company
        create_chart.execute('create_account')
        receivable, = Account.find([
            ('type.receivable', '=', True),
            ('code', '=', '4300'),
            ('company', '=', company.id),
        ],
                                   limit=1)
        payable, = Account.find([
            ('type.payable', '=', True),
            ('code', '=', '4100'),
            ('company', '=', company.id),
        ],
                                limit=1)
        revenue, = Account.find([
            ('type.revenue', '=', True),
            ('code', '=', '7000'),
            ('company', '=', company.id),
        ],
                                limit=1)
        expense, = Account.find([
            ('type.expense', '=', True),
            ('code', '=', '600'),
            ('company', '=', company.id),
        ],
                                limit=1)
        create_chart.form.account_receivable = receivable
        create_chart.form.account_payable = payable
        create_chart.execute('create_properties')

        # Get Taxes rule
        TaxRule = Model.get('account.tax.rule')
        tax_rule01, = TaxRule.find([
            ('company', '=', company.id),
            ('kind', '=', 'purchase'),
            ('name', '=', 'Retención IRPF 7%'),
        ])
        TaxRule = Model.get('account.tax.rule')
        tax_rule02, = TaxRule.find([
            ('company', '=', company.id),
            ('kind', '=', 'purchase'),
            ('name', '=', 'Retención IRPF 35%'),
        ])

        # Create parties
        Party = Model.get('party.party')
        supplier01 = Party(name='Supplier01')
        supplier01.supplier_tax_rule = tax_rule01
        identifier = supplier01.identifiers.new()
        identifier.type = 'eu_vat'
        identifier.code = 'ES00000000T'
        supplier01.save()
        supplier02 = Party(name='Supplier02')
        supplier02.supplier_tax_rule = tax_rule02
        identifier = supplier02.identifiers.new()
        identifier.type = 'eu_vat'
        identifier.code = 'ES00000001R'
        supplier02.save()

        # Create account category
        Tax = Model.get('account.tax')
        tax, = Tax.find([
            ('company', '=', company.id),
            ('group.kind', '=', 'purchase'),
            ('name', '=', 'IVA Deducible 21% (operaciones corrientes)'),
            ('parent', '=', None),
        ],
                        limit=1)
        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name="Account Category")
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.supplier_taxes.append(tax)
        account_category.save()

        # Create product
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.default_uom = unit
        template.type = 'service'
        template.list_price = Decimal('40')
        template.account_category = account_category
        product, = template.products
        product.cost_price = Decimal('25')
        template.save()
        product, = template.products

        # Create invoices
        Invoice = Model.get('account.invoice')
        invoice = Invoice()
        invoice.type = 'in'
        invoice.party = supplier01
        invoice.invoice_date = period.start_date
        line = invoice.lines.new()
        line.product = product
        line.quantity = 1
        line.unit_price = Decimal('700')
        invoice.click('post')
        self.assertEqual(invoice.total_amount, Decimal('798.00'))
        invoice = Invoice()
        invoice.type = 'in'
        invoice.party = supplier02
        invoice.invoice_date = period.start_date
        line = invoice.lines.new()
        line.product = product
        line.quantity = 1
        line.unit_price = Decimal('500')
        invoice.click('post')
        self.assertEqual(invoice.total_amount, Decimal('430.00'))

        # Create payroll move
        Journal = Model.get('account.journal')
        Move = Model.get('account.move')
        account_salaries, = Account.find([
            ('code', '=', '640'),
            ('type', '!=', None),
            ('type.expense', '=', True),
            ('type.revenue', '=', False),
            ('type.debt', '=', False),
            ('company', '=', company.id),
        ],
                                         limit=1)
        account_taxation, = Account.find([
            ('code', '=', '4751'),
            ('type', '!=', None),
            ('type.expense', '=', False),
            ('type.revenue', '=', False),
            ('type.debt', '=', False),
            ('company', '=', company.id),
        ],
                                         limit=1)
        account_remuneration, = Account.find([
            ('code', '=', '476'),
            ('type', '!=', None),
            ('type.expense', '=', False),
            ('type.revenue', '=', False),
            ('type.debt', '=', False),
            ('company', '=', company.id),
        ],
                                             limit=1)
        journal, = Journal.find([
            ('code', '=', 'MISC'),
        ])
        move = Move()
        move.period = period
        move.journal = journal
        move.date = period.start_date
        line = move.lines.new()
        line.account = account_salaries
        line.debit = Decimal(2200)
        line = move.lines.new()
        line.account = account_taxation
        line.credit = Decimal(1200)
        line = move.lines.new()
        line.account = account_remuneration
        line.credit = Decimal(1000)
        move.save()
        move.click('post')

        # Generate AEAT 111 Report
        Report = Model.get('aeat.111.report')
        report = Report()
        report.year = period.start_date.year
        report.type = 'I'
        report.period = "%02d" % (period.start_date.month)
        report.company_vat = 'ESB01000009'
        report.work_productivity_monetary_parties = 4
        report.work_productivity_in_kind_parties = 0
        report.economic_activities_productivity_in_kind_parties = 0
        report.awards_monetary_parties = 0
        report.awards_in_kind_parties = 0
        report.gains_forestry_exploitation_monetary_parties = 0
        report.gains_forestry_exploitation_in_kind_parties = 0
        report.image_rights_parties = 0
        report.click('calculate')
        self.assertEqual(
            report.economic_activities_productivity_monetary_parties, 2)
        self.assertEqual(report.withholdings_payments_amount,
                         Decimal('1424.00'))

        # Test report is generated correctly
        report.file_
        report.click('process')
        self.assertEqual(bool(report.file_), True)
