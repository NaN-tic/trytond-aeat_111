===========================
AEAT 111 Reporting Scenario
===========================

Imports::

    >>> import datetime
    >>> from decimal import Decimal
    >>> from proteus import Model, Wizard, Report
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.tools import file_open
    >>> from trytond.modules.currency.tests.tools import get_currency
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import (
    ...     create_chart, get_accounts, create_fiscalyear)
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences
    >>> today = datetime.date.today()

Activate modules::

    >>> config = activate_modules(['aeat_111', 'account_es', 'account_invoice'])

Create company::

    >>> eur = get_currency('EUR')
    >>> _ = create_company(currency=eur)
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'eu_vat'
    >>> tax_identifier.code = 'ESB01000009'
    >>> company.party.save()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]

Create chart of accounts::

    >>> AccountTemplate = Model.get('account.account.template')
    >>> Account = Model.get('account.account')
    >>> account_template, = AccountTemplate.find([('parent', '=', None),
    ...     ('name', 'ilike', 'Plan General Contable%')])
    >>> create_chart = Wizard('account.create_chart')
    >>> create_chart.execute('account')
    >>> create_chart.form.account_template = account_template
    >>> create_chart.form.company = company
    >>> create_chart.execute('create_account')
    >>> receivable, = Account.find([
    ...         ('type.receivable', '=', True),
    ...         ('code', '=', '4300'),
    ...         ('company', '=', company.id),
    ...         ], limit=1)
    >>> payable, = Account.find([
    ...         ('type.payable', '=', True),
    ...         ('code', '=', '4100'),
    ...         ('company', '=', company.id),
    ...         ], limit=1)
    >>> revenue, = Account.find([
    ...         ('type.revenue', '=', True),
    ...         ('code', '=', '7000'),
    ...         ('company', '=', company.id),
    ...         ], limit=1)
    >>> expense, = Account.find([
    ...         ('type.expense', '=', True),
    ...         ('code', '=', '600'),
    ...         ('company', '=', company.id),
    ...         ], limit=1)
    >>> create_chart.form.account_receivable = receivable
    >>> create_chart.form.account_payable = payable
    >>> create_chart.execute('create_properties')

Get Taxes rule::

    >>> TaxRule = Model.get('account.tax.rule')
    >>> tax_rule01, = TaxRule.find([
    ...     ('company', '=', company.id),
    ...     ('kind', '=', 'purchase'),
    ...     ('name', '=', 'Retención IRPF 7%'),
    ...     ])
    >>> TaxRule = Model.get('account.tax.rule')
    >>> tax_rule02, = TaxRule.find([
    ...     ('company', '=', company.id),
    ...     ('kind', '=', 'purchase'),
    ...     ('name', '=', 'Retención IRPF 35%'),
    ...     ])

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier01 = Party(name='Supplier01')
    >>> supplier01.supplier_tax_rule = tax_rule01
    >>> identifier = supplier01.identifiers.new()
    >>> identifier.type='eu_vat'
    >>> identifier.code='ES00000000T'
    >>> supplier01.save()
    >>> supplier02 = Party(name='Supplier02')
    >>> supplier02.supplier_tax_rule = tax_rule02
    >>> identifier = supplier02.identifiers.new()
    >>> identifier.type = 'eu_vat'
    >>> identifier.code = 'ES00000001R'
    >>> supplier02.save()


Create account category::

    >>> Tax = Model.get('account.tax')
    >>> tax, = Tax.find([
    ...     ('company', '=', company.id),
    ...     ('group.kind', '=', 'purchase'),
    ...     ('name', '=', 'IVA Deducible 21% (operaciones corrientes)'),
    ...     ('parent', '=', None),
    ...     ], limit = 1)
    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.supplier_taxes.append(tax)
    >>> account_category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.list_price = Decimal('40')
    >>> template.account_category = account_category
    >>> product, = template.products
    >>> product.cost_price = Decimal('25')
    >>> template.save()
    >>> product, = template.products

Create invoices::

    >>> Invoice = Model.get('account.invoice')
    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = supplier01
    >>> invoice.invoice_date = today
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 1
    >>> line.unit_price = Decimal('700')
    >>> invoice.click('post')
    >>> invoice.total_amount
    Decimal('847.00')
    >>> Invoice = Model.get('account.invoice')
    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = supplier02
    >>> invoice.invoice_date = today
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 1
    >>> line.unit_price = Decimal('500')
    >>> invoice.click('post')
    >>> invoice.total_amount
    Decimal('430.00')

Generate AEAT 111 Report::

    >>> Report = Model.get('aeat.111.report')
    >>> report = Report()
    >>> report.year = today.year
    >>> report.type = 'I'
    >>> report.period = "%02d" % (today.month)
    >>> report.company_vat = 'ESB01000009'
    >>> report.click('calculate')
    >>> report.economic_activities_productivity_monetary_parties
    2
    >>> report.withholdings_payments_amount
    Decimal('224.00')

Test report is generated correctly::

    >>> report.file_
    >>> report.click('process')
    >>> bool(report.file_)
    True
