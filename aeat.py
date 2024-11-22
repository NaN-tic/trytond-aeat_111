# -*- coding: utf-8 -*-
from decimal import Decimal
import datetime
import calendar
import unicodedata
from itertools import groupby

from retrofix import aeat111
from retrofix.record import Record, write as retrofix_write
from trytond.model import Workflow, ModelSQL, ModelView, fields, Unique
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool, If
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from trytond.modules.currency.fields import Monetary

_ZERO = Decimal("0.0")


def remove_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text)
        if (unicodedata.category(c) != 'Mn'
                or c in ('\\u0327', '\\u0303'))  # Avoids normalize ç and ñ
        )


class TemplateAccountRelation(ModelSQL):
    '''
    AEAT 111 Account Mapping Codes Relation
    '''
    __name__ = 'aeat.111.mapping-account.account.template'

    mapping = fields.Many2One('aeat.111.template.mapping', 'Mapping',
        required=True)
    account = fields.Many2One('account.account.template', 'Account Template',
        required=True)


class TemplateTaxCodeRelation(ModelSQL):
    '''
    AEAT 111 TaxCode Mapping Codes Relation
    '''
    __name__ = 'aeat.111.mapping-account.tax.code.template'

    mapping = fields.Many2One('aeat.111.template.mapping', 'Mapping',
        required=True)
    code = fields.Many2One('account.tax.code.template', 'Tax Code Template',
        required=True)


class TemplateMapping(ModelSQL):
    '''
    AEAT 111 Template Mapping
    '''
    __name__ = 'aeat.111.template.mapping'

    aeat111_field = fields.Many2One('ir.model.field', 'Field',
        domain=[('module', '=', 'aeat_111')], required=True)
    type_ = fields.Selection([
            ('code', 'Code'),
            ('account', 'Account'),
            ], 'Type', required=True)
    account = fields.Many2Many('aeat.111.mapping-account.account.template',
        'mapping', 'account', 'Account Template',
        states={
            'invisible': Eval('type_') != 'account',
            })
    debit_credit_type = fields.Selection([
            (None, 'Not apply'),
            ('debit', 'Debit'),
            ('credit', 'Credit'),
            ('both', 'Both'),
            ], 'Debit Credit Type', states={
                'invisible': Eval('type_') != 'account',
                })
    code = fields.Many2Many('aeat.111.mapping-account.tax.code.template',
        'mapping', 'code', 'Tax Code Template',
        states={
            'invisible': Eval('type_') != 'code',
            })

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('aeat111_field_uniq', Unique(t, t.aeat111_field),
                'Field must be unique.')
            ]

    def _get_mapping_value(self, mapping=None):
        pool = Pool()
        Account = pool.get('account.account')
        TaxCode = pool.get('account.tax.code')

        res = {}
        if mapping is None or mapping.type_ != self.type_:
            res['type_'] = self.type_
        if mapping is None or mapping.debit_credit_type != self.debit_credit_type:
            res['debit_credit_type'] = self.debit_credit_type
        if mapping is None or mapping.aeat111_field != self.aeat111_field:
            res['aeat111_field'] = self.aeat111_field.id
        res['account'] = []
        res['code'] = []
        old_ids = {
            'account': set(),
            'code': set(),
                }
        new_ids = {
            'account': set(),
            'code': set(),
                }
        if mapping and len(mapping.account) > 0:
            old_ids['account'] = set([a.id for a in mapping.account])
        if mapping and len(mapping.code) > 0:
            old_ids['code'] = set([c.id for c in mapping.code])
        if len(self.account) > 0:
            new_ids['account']= set([a.id for a in Account.search([
                            ('template', 'in', [a.id for a in self.account])
                            ])])
        if len(self.code) > 0:
            new_ids['code'] = set([c.id for c in TaxCode.search([
                            ('template', 'in', [c.id for c in self.code])
                            ])])
        if not mapping or mapping.template != self:
            res['template'] = self.id
        for key in {'account', 'code'}:
            if old_ids[key] or new_ids[key]:
                res[key] = []
                to_remove = old_ids[key] - new_ids[key]
                if to_remove:
                    res[key].append(['remove', list(to_remove)])
                to_add = new_ids[key] - old_ids[key]
                if to_add:
                    res[key].append(['add', list(to_add)])
                if not res[key]:
                    del res[key]
        if not mapping and not res['account'] and not res['code']:
            return  # There is nothing to create as there is no mapping
        return res


class UpdateChart(metaclass=PoolMeta):
    __name__ = 'account.update_chart'

    def transition_update(self):
        pool = Pool()
        MappingTemplate = pool.get('aeat.111.template.mapping')
        Mapping = pool.get('aeat.111.mapping')

        ret = super().transition_update()

        # Update current values
        ids = []
        company = self.start.account.company.id
        for mapping in Mapping.search([
                    ('company', 'in', [company, None]),
                    ]):
            if not mapping.template:
                continue
            vals = mapping.template._get_mapping_value(mapping=mapping)
            if vals:
                Mapping.write([mapping], vals)
            ids.append(mapping.template.id)

        # Create new one's
        to_create = []
        for template in MappingTemplate.search([('id', 'not in', ids)]):
            vals = template._get_mapping_value()
            if vals:
                vals['company'] = company
                to_create.append(vals)
        if to_create:
            Mapping.create(to_create)

        return ret


class CreateChart(metaclass=PoolMeta):
    __name__ = 'account.create_chart'

    def transition_create_account(self):
        pool = Pool()
        MappingTemplate = pool.get('aeat.111.template.mapping')
        Mapping = pool.get('aeat.111.mapping')

        company = self.account.company.id

        ret = super().transition_create_account()
        to_create = []
        for template in MappingTemplate.search([]):
            vals = template._get_mapping_value()
            if vals:
                vals['company'] = company
                to_create.append(vals)

        Mapping.create(to_create)
        return ret


class AccountRelation(ModelSQL):
    '''
    AEAT 111 Account Mapping Codes Relation
    '''
    __name__ = 'aeat.111.mapping-account.account'

    mapping = fields.Many2One('aeat.111.mapping', 'Mapping', required=True)
    account = fields.Many2One('account.account', 'Account', required=True)


class TaxCodeRelation(ModelSQL):
    '''
    AEAT 111 TaxCode Mapping Codes Relation
    '''
    __name__ = 'aeat.111.mapping-account.tax.code'

    mapping = fields.Many2One('aeat.111.mapping', 'Mapping', required=True)
    code = fields.Many2One('account.tax.code', 'Tax Code', required=True)


class Mapping(ModelSQL, ModelView):
    '''
    AEAT 111 Mapping
    '''
    __name__ = 'aeat.111.mapping'

    company = fields.Many2One('company.company', 'Company',
        ondelete="RESTRICT")
    aeat111_field = fields.Many2One('ir.model.field', 'Field',
        domain=[('module', '=', 'aeat_111')], required=True)
    type_ = fields.Selection([
            ('code', 'Code'),
            ('account', 'Account')
            ], 'Type', required=True)
    account = fields.Many2Many('aeat.111.mapping-account.account', 'mapping',
        'account', 'Account',
        states={
            'required': Eval('type_') == 'account',
            'invisible': Eval('type_') != 'account',
            })
    account_by_companies = fields.Function(
        fields.Many2Many('aeat.111.mapping-account.account', 'mapping',
        'account', 'Account',
        states={
            'required': Eval('type_') == 'account',
            'invisible': Eval('type_') != 'account',
            }), 'get_account_by_companies')
    debit_credit_type = fields.Selection([
            (None, 'Not apply'),
            ('debit', 'Debit'),
            ('credit', 'Credit'),
            ('both', 'Both'),
            ], 'Debit Credit Type', states={
                'required': Eval('type_') == 'account',
                'invisible': Eval('type_') != 'account',
                })
    code = fields.Many2Many('aeat.111.mapping-account.tax.code', 'mapping',
        'code', 'Tax Code',
        states={
            'required': Eval('type_') == 'code',
            'invisible': Eval('type_') != 'code',
            })
    code_by_companies = fields.Function(
        fields.Many2Many('aeat.111.mapping-account.tax.code', 'mapping',
        'code', 'Tax Code',
        states={
            'required': Eval('type_') == 'code',
            'invisible': Eval('type_') != 'code',
            }), 'get_code_by_companies')
    template = fields.Many2One('aeat.111.template.mapping', 'Template')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('aeat111_field_uniq', Unique(t, t.company, t.aeat111_field),
                'Field must be unique.')
            ]

    @staticmethod
    def default_company():
        return Transaction().context.get('company') or None

    @staticmethod
    def default_debit_credit_type():
        return 'both'

    @classmethod
    def get_code_by_companies(cls, records, name):
        user_company = Transaction().context.get('company')
        res = dict((x.id, None) for x in records)
        for record in records:
            code_ids = []
            for code in record.code:
                if not code.company or code.company.id == user_company:
                    code_ids.append(code.id)
            res[record.id] = code_ids
        return res

    @classmethod
    def get_account_by_companies(cls, records, name):
        user_company = Transaction().context.get('company')
        res = dict((x.id, None) for x in records)
        for record in records:
            account_ids = []
            for account in record.account:
                if not account.company or account.company.id == user_company:
                    account_ids.append(account.id)
            res[record.id] = account_ids
        return res


class Report(Workflow, ModelSQL, ModelView):
    '''
    AEAT 111 Report
    '''
    __name__ = 'aeat.111.report'

    company = fields.Many2One('company.company', 'Company', required=True,
        states={
            'readonly': Eval('state').in_(['done', 'calculated']),
            })
    currency = fields.Function(fields.Many2One('currency.currency',
        'Currency'), 'get_currency')

    # DRM11101
    type = fields.Selection([
            ('I', 'Income'),
            ('U', 'Direct incomes in account'),
            ('G', 'Income on CCT'),
            ('N', 'Negative'),
            ], 'Declaration Type', required=True, sort=False, states={
                'readonly': Eval('state') == 'done',
            })
    company_vat = fields.Char('VAT')
    company_surname = fields.Char('Company Surname')
    company_name = fields.Char('Company Name')
    year = fields.Integer("Year", required=True,
        domain=[
            ('year', '>=', 1000),
            ('year', '<=', 9999)
            ],
        states={
            'readonly': Eval('state').in_(['done', 'calculated']),
            })
    period = fields.Selection([
            ('1T', 'First quarter'),
            ('2T', 'Second quarter'),
            ('3T', 'Third quarter'),
            ('4T', 'Fourth quarter'),
            ('01', 'January'),
            ('02', 'February'),
            ('03', 'March'),
            ('04', 'April'),
            ('05', 'May'),
            ('06', 'June'),
            ('07', 'July'),
            ('08', 'August'),
            ('09', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'December'),
            ], 'Period', required=True, sort=False, states={
                'readonly': Eval('state').in_(['done', 'calculated']),
                })

    work_productivity_monetary_parties = fields.Integer(
        "Work Productivity Monetary Parties")
    work_productivity_monetary_payments = fields.Numeric(
        "Work Productivity Monetary Payments", digits=(15, 2))
    work_productivity_monetary_withholdings_amount = fields.Numeric(
        "Work Productivty Monetary Withholdings Amount", digits=(15, 2))

    work_productivity_in_kind_parties = fields.Integer(
        "Work Productivity In-Kind Parties", required=True,
        domain=[
            If(Eval('work_productivity_in_kind_value_benefits', 0) != 0,
                [
                    ('work_productivity_in_kind_parties', '>', 0),
                    ('work_productivity_in_kind_parties', '<=', 99999999),
                    ],
                ('work_productivity_in_kind_parties', '=', 0)),
            ])
    work_productivity_in_kind_value_benefits = fields.Numeric(
        "Work Productivity In-Kind Value Benefits", digits=(15, 2))
    work_productivity_in_kind_payments_amount = fields.Numeric(
        "Work Productivity In-Kind Payments Amount", digits=(15, 2))

    economic_activities_productivity_monetary_parties = fields.Integer(
        "Economic Activities Productivity Monetary Parties", readonly=True)
    economic_activities_productivity_monetary_payments = fields.Numeric(
        "Economic Activities Productivity Monetary Payments",
        digits=(15, 2))
    economic_activities_productivity_monetary_withholdings_amount = (
        fields.Numeric(
            "Economic Activities Productivity Monetary Withholdings Amount",
            digits=(15, 2)))

    economic_activities_productivity_in_kind_parties = fields.Integer(
        "Economic Activities Productivity In-Kind Parties", required=True,
        domain=[
            If(Eval('economic_activities_productivity_in_kind_value_benefits', 0) != 0,
                [
                    ('economic_activities_productivity_in_kind_parties', '>', 0),
                    ('economic_activities_productivity_in_kind_parties', '<=', 99999999),
                    ],
                ('economic_activities_productivity_in_kind_parties', '=', 0)),
            ])
    economic_activities_productivity_in_kind_value_benefits = fields.Numeric(
        "Economic Activities Productivity In-Kind Value Benefits",
        digits=(15, 2))
    economic_activities_productivity_in_kind_payments_amount = fields.Numeric(
        "Economic Activities Productivity In-Kind Payments Amount",
        digits=(15, 2))

    awards_monetary_parties = fields.Integer("Awards Monetary Parties",
        required=True,
        domain=[
            If(Eval('awards_monetary_withholdings_amount', 0) != 0,
                [
                    ('awards_monetary_parties', '>', 0),
                    ('awards_monetary_parties', '<=', 99999999),
                    ],
                ('awards_monetary_parties', '=', 0)),
            ])
    awards_monetary_payments = fields.Numeric(
        "Awards Monetary Payments", digits=(15, 2))
    awards_monetary_withholdings_amount = fields.Numeric(
        "Awards Monetary Withholdings Amount", digits=(15, 2))

    awards_in_kind_parties = fields.Integer("Awards In-Kind Parties",
        required=True,
        domain=[
            If(Eval('awards_in_kind_payments_amount', 0) != 0,
                [
                    ('awards_in_kind_parties', '>', 0),
                    ('awards_in_kind_parties', '<=', 99999999),
                    ],
                ('awards_in_kind_parties', '=', 0)),
            ])
    awards_in_kind_value_benefits = fields.Numeric(
        "Awards In-Kind Value Benefits", digits=(15, 2))
    awards_in_kind_payments_amount = fields.Numeric(
        "Awards In-Kind Payments Amount", digits=(15, 2))

    gains_forestry_exploitation_monetary_parties = fields.Integer(
        "Gains Forestry Exploitation Monetary Parties", required=True,
        domain=[
            If(Eval('gains_forestry_exploitation_monetary_withholdings_amount', 0) != 0,
                [
                    ('gains_forestry_exploitation_monetary_parties', '>', 0),
                    ('gains_forestry_exploitation_monetary_parties', '<=', 99999999),
                    ],
                ('gains_forestry_exploitation_monetary_parties', '=', 0)),
            ])
    gains_forestry_exploitation_monetary_payments = fields.Numeric(
        "Gains Forestry Exploitation Monetary Payments", digits=(15, 2))
    gains_forestry_exploitation_monetary_withholdings_amount = fields.Numeric(
        "Gains Forestry Exploitation Monetary Withholdings Amount",
        digits=(15, 2))

    gains_forestry_exploitation_in_kind_parties = fields.Integer(
        "Gains Forestry Exploitation In-Kind Parties", required=True,
        domain=[
            If(Eval('gains_forestry_exploitation_in_kind_payments_amount', 0) != 0,
                [
                    ('gains_forestry_exploitation_in_kind_parties', '>', 0),
                    ('gains_forestry_exploitation_in_kind_parties', '<=', 99999999),
                    ],
                ('gains_forestry_exploitation_in_kind_parties', '=', 0)),
            ])
    gains_forestry_exploitation_in_kind_value_benefits = fields.Numeric(
        "Gains Forestry Exploitation In-Kind Value Benefits", digits=(15, 2))
    gains_forestry_exploitation_in_kind_payments_amount = fields.Numeric(
        "Gains Forestry Exploitation In-Kind Payments Amount", digits=(15, 2))

    image_rights_parties = fields.Integer("Image Rights Parties",
        required=True,
        domain=[
            If(Eval('image_rights_payments_amount', 0) != 0,
                [
                    ('image_rights_parties', '>', 0),
                    ('image_rights_parties', '<=', 99999999),
                    ],
            ('image_rights_parties', '=', 0)),
            ])
    image_rights_service_payments = fields.Numeric(
        "Image Rights Service Payments", digits=(15, 2))
    image_rights_payments_amount = fields.Numeric(
        "Image Rights Payments Amount", digits=(15, 2))

    registers = fields.One2Many('aeat.111.report.register', 'report',
        'Registers', readonly=True)

    withholdings_payments_amount = fields.Function(fields.Numeric(
            "Withholding and Payments", digits=(15, 2)),
        'get_withholdings_payments_amount')
    to_deduce = fields.Numeric("To Deduce", digits=(15, 2),
        help="Exclusively in case of complementary self-assessment. "
        "Results to be entered from previous self-assessments for the same "
        "concept, year and period")
    result = fields.Function(fields.Numeric("Result", digits=(15, 2)),
        'get_result')

    complementary_declaration = fields.Boolean("Complementary Declaration")
    previous_declaration_receipt = fields.Char("Previous Declaration Receipt",
        size=13, states={
            'required': Bool(Eval('complementary_declaration')),
            })
    company_party = fields.Function(fields.Many2One('party.party',
            'Company Party', context={
                'company': Eval('company', -1),
            }), 'on_change_with_company_party')
    bank_account = fields.Many2One('bank.account', "Bank Account",
        domain=[
            ('owners', '=', Eval('company_party')),
            ], states={
            'required': Eval('type').in_(['U', 'D', 'X']),
            })

    # Footer
    state = fields.Selection([
            ('draft', 'Draft'),
            ('calculated', 'Calculated'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled')
            ], "State", readonly=True)
    calculation_date = fields.DateTime("Calculation Date", readonly=True)
    file_ = fields.Binary("File", filename='filename', states={
            'invisible': Eval('state') != 'done',
            }, readonly=True)
    filename = fields.Function(fields.Char("File Name"), 'get_filename')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order = [
            ('year', 'DESC'),
            ('period', 'DESC'),
            ('id', 'DESC'),
            ]
        cls._buttons.update({
                'draft': {
                    'invisible': ~Eval('state').in_(['calculated',
                            'cancelled']),
                    },
                'calculate': {
                    'invisible': ~Eval('state').in_(['draft']),
                    },
                'process': {
                    'invisible': ~Eval('state').in_(['calculated']),
                    },
                'cancel': {
                    'invisible': Eval('state').in_(['cancelled']),
                    },
                })
        cls._transitions |= set((
                ('draft', 'calculated'),
                ('draft', 'cancelled'),
                ('calculated', 'draft'),
                ('calculated', 'done'),
                ('calculated', 'cancelled'),
                ('done', 'cancelled'),
                ('cancelled', 'draft'),
                ))

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @classmethod
    def default_company_vat(cls):
        pool = Pool()
        Company = pool.get('company.company')
        company_id = cls.default_company()
        if company_id:
            company = Company(company_id)
            vat_code = company.party.tax_identifier and \
                company.party.tax_identifier.code or None
            if vat_code and vat_code.startswith('ES'):
                return vat_code[2:]
            return vat_code

    @staticmethod
    def default_work_productivity_in_kind_parties():
        return _ZERO

    @staticmethod
    def default_work_productivity_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_work_productivity_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_economic_activities_productivity_in_kind_parties():
        return _ZERO

    @staticmethod
    def default_economic_activities_productivity_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_economic_activities_productivity_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_awards_monetary_parties():
        return _ZERO

    @staticmethod
    def default_awards_monetary_payments():
        return _ZERO

    @staticmethod
    def default_awards_monetary_withholdings_amount():
        return _ZERO

    @staticmethod
    def default_awards_in_kind_parties():
        return _ZERO

    @staticmethod
    def default_awards_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_awards_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_monetary_parties():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_monetary_payments():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_monetary_withholdings_amount():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_in_kind_parties():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_image_rights_parties():
        return _ZERO

    @staticmethod
    def default_image_rights_service_payments():
        return _ZERO

    @staticmethod
    def default_image_rights_payments_amount():
        return _ZERO

    @staticmethod
    def default_to_deduce():
        return _ZERO

    @classmethod
    def default_company_party(cls):
        pool = Pool()
        Company = pool.get('company.company')
        company_id = cls.default_company()
        if company_id:
            return Company(company_id).party.id

    @fields.depends('company')
    def on_change_with_company_party(self, name=None):
        if self.company:
            return self.company.party.id

    @fields.depends('company')
    def on_change_with_company_surname(self, name=None):
        if self.company:
            return self.company.party.name.upper()

    @fields.depends('company')
    def on_change_with_company_vat(self, name=None):
        if self.company:
            tax_identifier = self.company.party.tax_identifier
            if tax_identifier and tax_identifier.code.startswith('ES'):
                return tax_identifier.code[2:]

    def get_currency(self, name):
        return self.company.currency.id

    def get_withholdings_payments_amount(self, name=None):
        return (
            (self.work_productivity_monetary_withholdings_amount or _ZERO)
            + self.work_productivity_in_kind_payments_amount
            + (self.
                economic_activities_productivity_monetary_withholdings_amount
                or _ZERO)
            + self.economic_activities_productivity_in_kind_payments_amount
            + self.awards_monetary_withholdings_amount
            + self.awards_in_kind_payments_amount
            + self.gains_forestry_exploitation_monetary_withholdings_amount
            + self.gains_forestry_exploitation_in_kind_payments_amount
            + self.image_rights_payments_amount
            )

    def get_result(self, name):
        return (self.withholdings_payments_amount or _ZERO) - self.to_deduce

    def get_filename(self, name):
        return 'aeat111-%s-%s.txt' % (
            self.year, self.period)

    @classmethod
    @ModelView.button
    @Workflow.transition('calculated')
    def calculate(cls, reports):
        pool = Pool()
        Mapping = pool.get('aeat.111.mapping')
        Period = pool.get('account.period')
        Account = pool.get('account.account')
        MoveLine = pool.get('account.move.line')
        TaxCode = pool.get('account.tax.code')
        Tax = pool.get('account.tax')
        TaxLine = pool.get('account.tax.line')
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        Register = pool.get('aeat.111.report.register')

        for report in reports:
            # Work Productivity
            mapping_accounts = {}
            for mapp in Mapping.search([
                    ('type_', '=', 'account'),
                    ('company', '=', report.company),
                    ]):
                for account in mapp.account_by_companies:
                    mapping_accounts[account.id] = (mapp.aeat111_field.name,
                        mapp.debit_credit_type)
            # Economic Activities
            mapping_codes = {}
            for mapp in Mapping.search([
                    ('type_', '=', 'code'),
                    ('company', '=', report.company),
                    ]):
                for code in mapp.code_by_companies:
                    mapping_codes[code.id] = mapp.aeat111_field.name

            year = report.year
            period = report.period
            if 'T' in period:
                period = period[0]
                start_month = (int(period) - 1) * 3 + 1
                end_month = start_month + 2
            else:
                start_month = int(period)
                end_month = start_month
            lday = calendar.monthrange(year, end_month)[1]
            periods = [p.id for p in Period.search([
                    ('start_date', '>=', datetime.date(year, start_month, 1)),
                    ('end_date', '<=', datetime.date(year, end_month, lday)),
                    ('company', '=', report.company),
                    ])]

            for field, _ in mapping_accounts.values():
                setattr(report, field, _ZERO)
            for field in mapping_codes.values():
                setattr(report, field, _ZERO)

            work_payment_registers = {}
            work_amount_registers = {}
            economic_activities_registers = {}
            with Transaction().set_context(periods=periods):
                for code in TaxCode.browse(mapping_codes.keys()):
                    value = getattr(report, mapping_codes[code.id])
                    amount = value + code.amount
                    setattr(report, mapping_codes[code.id], abs(amount))

                    # To count the number of parties of economic activities
                    # we have to do it from the party in the related moves
                    # of all codes used for the amount calculation
                    # It is expected TaxCode was created from invoices, not
                    # manually.
                    children = []
                    childs = TaxCode.search([
                            ('parent', 'child_of', [code]),
                            ])
                    if len(childs) == 1:
                        children = childs
                    else:
                        for child in childs:
                            if not child.childs and child.amount:
                                children.append(child)
                    for child in children:
                        if not child.lines:
                            continue
                        domain = [['OR'] + [x._line_domain for x in child.lines
                            if x.amount == 'tax']]
                        if domain == [['OR']]:
                            continue
                        domain.extend(Tax._amount_domain())
                        a = TaxLine.search(domain)
                        for tax_line in TaxLine.search(domain):
                            if (tax_line.move_line and tax_line.move_line.move
                                    and isinstance(
                                        tax_line.move_line.move.origin,
                                        Invoice)):
                                invoice = tax_line.move_line.move.origin
                                party = invoice.party
                                if party in economic_activities_registers:
                                    economic_activities_registers[
                                        party].amount += abs(tax_line.amount)
                                    economic_activities_registers[
                                        party].invoices += (invoice,)
                                else:
                                    register = Register()
                                    register.report = report
                                    register.type_ = 'economic_activity'
                                    register.party = party
                                    register.amount = abs(tax_line.amount)
                                    register.invoices = (invoice,)
                                    economic_activities_registers[party] = (
                                        register)

                # To count the number of parties of work
                # we have to do it from the party in the related moves
                # of all accounts used for the amount calculation deffined in
                # the mapping.
                for account in Account.browse(mapping_accounts.keys()):
                    field = mapping_accounts[account.id][0]
                    debit_credit_type = mapping_accounts[account.id][1]
                    value = getattr(report, field)
                    amount = value
                    if debit_credit_type in ('debit', 'both'):
                        amount += account.debit
                    if debit_credit_type in ('credit', 'both'):
                        amount -= account.credit
                    setattr(report, field, abs(amount))
                    domain = [
                        ('move.period', 'in', periods),
                        ('account', '=', account),
                        ]
                    if debit_credit_type == 'debit':
                        domain.append(
                            ('debit', '!=', 0),
                            )
                    elif debit_credit_type == 'credit':
                        domain.append(
                            ('credit', '!=', 0),
                            )
                    move_lines = MoveLine.search(domain)
                    payment = 'payment' in field
                    for party, group_lines in groupby(move_lines,
                            key=lambda l: l.party):
                        lines = list(group_lines)
                        amount = sum(x.debit - x.credit for x in lines)
                        if payment and party in work_payment_registers:
                            work_payment_registers[party].amount += abs(amount)
                            work_payment_registers[party].move_lines += tuple(lines)
                        elif not payment and party in work_amount_registers:
                            work_amount_registers[party].amount += abs(amount)
                            work_amount_registers[party].move_lines += tuple(lines)
                        else:
                            register = Register()
                            register.report = report
                            register.amount = abs(amount)
                            register.move_lines = lines
                            if payment:
                                register.type_ = 'work_payment'
                                work_payment_registers[party] = register
                            else:
                                register.type_ = 'work_amount'
                                work_amount_registers[party] = register
            registers = []
            if work_payment_registers:
                registers.extend(work_payment_registers.values())
            if work_amount_registers:
                registers.extend(work_amount_registers.values())
            if economic_activities_registers:
                registers.extend(economic_activities_registers.values())
            if registers:
                Register.save(registers)
            report.work_productivity_monetary_parties = (
                len(work_amount_registers) if work_amount_registers else 0)
            report.economic_activities_productivity_monetary_parties = (
                len(economic_activities_registers)
                if economic_activities_registers else 0)
            report.save()

        cls.write(reports, {
                'calculation_date': datetime.datetime.now(),
                })

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def process(cls, reports):
        for report in reports:
            report.create_file()

    @classmethod
    @ModelView.button
    @Workflow.transition('cancelled')
    def cancel(cls, reports):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, reports):
        registers = [register for report in reports
            for register in report.registers]
        if registers:
            Register.delete(registers)

    def create_file(self):
        if (self.work_productivity_monetary_withholdings_amount != 0 and self.work_productivity_monetary_parties == 0):
            raise UserError(gettext('aeat_111.msg_invalid_work_productivity_monetary_parties'))

        header = Record(aeat111.HEADER_RECORD)
        footer = Record(aeat111.FOOTER_RECORD)
        record = Record(aeat111.RECORD)
        columns = [x for x in self.__class__._fields if x != 'report']
        for column in columns:
            value = getattr(self, column, None)
            if not value:
                continue
            if column == 'year' or column.endswith('_parties'):
                value = str(getattr(self, column, 0))
            elif column == 'bank_account':
                value = next((n.number_compact for n in value.numbers
                        if n.type == 'iban'), '')
            if column in header._fields:
                setattr(header, column, value)
            if column in record._fields:
                setattr(record, column, value)
            if column in footer._fields:
                setattr(footer, column, value)
        records = [header, record, footer]
        try:
            data = retrofix_write(records, separator='')
        except AssertionError as e:
            raise UserError(str(e))
        data = remove_accents(data).upper()
        if isinstance(data, str):
            data = data.encode('iso-8859-1')
        self.file_ = self.__class__.file_.cast(data)
        self.save()


class Register(ModelSQL, ModelView):
    """
    AEAT 111 Register
    """
    __name__ = 'aeat.111.report.register'

    company = fields.Function(fields.Many2One('company.company', 'Company'),
        'on_change_with_company', searcher='search_company')
    report = fields.Many2One('aeat.111.report', 'AEAT 111 Report')
    type_ = fields.Selection([
            ('work_payment', 'Work Payment'),
            ('work_amount', 'Work Amount'),
            ('economic_activity', 'Economic Activity'),
            ], 'Type', required=True)
    party = fields.Many2One(
        'party.party', 'Party',
        context={
            'company': Eval('company', -1),
            },
        depends={'company'})
    currency = fields.Function(fields.Many2One('currency.currency', 'Currency'),
        'on_change_with_currency')
    amount = Monetary("Amount", currency='currency', digits='currency')
    invoices = fields.One2Many('account.invoice', 'aeat111_register',
        'Invoices', readonly=True)
    move_lines = fields.One2Many('account.move.line', 'aeat111_register',
        'Move Lines', readonly=True)

    @fields.depends('report', '_parent_report.company')
    def on_change_with_company(self, name=None):
        return (self.report and self.report.company
            and self.report.company.id or None)

    @classmethod
    def search_company(cls, name, clause):
        return [('report.%s' % name,) + tuple(clause[1:])]

    @fields.depends('report', '_parent_report.currency')
    def on_change_with_currency(self, name=None):
        return (self.report and self.report.currency
            and self.report.currency.id or None)
