# -*- coding: utf-8 -*-
from decimal import Decimal
import datetime
import calendar
import unicodedata
import sys

from retrofix import aeat111
from retrofix.record import Record, write as retrofix_write
from trytond.model import Workflow, ModelSQL, ModelView, fields, Unique
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.transaction import Transaction


_DEPENDS = ['state']

_ZERO = Decimal("0.0")


def remove_accents(unicode_string):
    str_ = str if sys.version_info < (3, 0) else bytes
    unicode_ = str if sys.version_info < (3, 0) else str
    if isinstance(unicode_string, str_):
        unicode_string_bak = unicode_string
        try:
            unicode_string = unicode_string_bak.decode('iso-8859-1')
        except UnicodeDecodeError:
            try:
                unicode_string = unicode_string_bak.decode('utf-8')
            except UnicodeDecodeError:
                return unicode_string_bak

    if not isinstance(unicode_string, unicode_):
        return unicode_string

    unicode_string_nfd = ''.join(
        (c for c in unicodedata.normalize('NFD', unicode_string)
            if (unicodedata.category(c) != 'Mn'
                or c in ('\\u0327', '\\u0303'))  # Avoids normalize ç and ñ
            ))
    # It converts nfd to nfc to allow unicode.decode()
    return unicodedata.normalize('NFC', unicode_string_nfd)


class TemplateTaxCodeRelation(ModelSQL):
    '''
    AEAT 111 TaxCode Mapping Codes Relation
    '''
    __name__ = 'aeat.111.mapping-account.tax.code.template'

    mapping = fields.Many2One('aeat.111.template.mapping', 'Mapping',
        required=True)
    code = fields.Many2One('account.tax.code.template', 'Tax Code Template',
        required=True)


class TemplateTaxCodeMapping(ModelSQL):
    '''
    AEAT 111 TemplateTaxCode Mapping
    '''
    __name__ = 'aeat.111.template.mapping'

    aeat111_field = fields.Many2One('ir.model.field', 'Field',
        domain=[('module', '=', 'aeat_111')], required=True)
    code = fields.Many2Many('aeat.111.mapping-account.tax.code.template',
        'mapping', 'code', 'Tax Code Template')

    @classmethod
    def __setup__(cls):
        super(TemplateTaxCodeMapping, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('aeat111_field_uniq', Unique(t, t.aeat111_field),
                'Field must be unique.')
            ]

    def _get_mapping_value(self, mapping=None):
        pool = Pool()
        TaxCode = pool.get('account.tax.code')

        res = {}
        if not mapping or mapping.aeat111_field != self.aeat111_field:
            res['aeat111_field'] = self.aeat111_field.id
        res['code'] = []
        old_ids = set()
        new_ids = set()
        if mapping and len(mapping.code) > 0:
            old_ids = set([c.id for c in mapping.code])
        if len(self.code) > 0:
            new_ids = set([c.id for c in TaxCode.search([
                            ('template', 'in', [c.id for c in self.code])
                            ])])
        if not mapping or mapping.template != self:
            res['template'] = self.id
        if old_ids or new_ids:
            key = 'code'
            res[key] = []
            to_remove = old_ids - new_ids
            if to_remove:
                res[key].append(['remove', list(to_remove)])
            to_add = new_ids - old_ids
            if to_add:
                res[key].append(['add', list(to_add)])
            if not res[key]:
                del res[key]
        if not mapping and not res['code']:
            return  # There is nothing to create as there is no mapping
        return res


class UpdateChart(metaclass=PoolMeta):
    __name__ = 'account.update_chart'

    def transition_update(self):
        pool = Pool()
        MappingTemplate = pool.get('aeat.111.template.mapping')
        Mapping = pool.get('aeat.111.mapping')

        ret = super(UpdateChart, self).transition_update()

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

        ret = super(CreateChart, self).transition_create_account()
        to_create = []
        for template in MappingTemplate.search([]):
            vals = template._get_mapping_value()
            if vals:
                vals['company'] = company
                to_create.append(vals)

        Mapping.create(to_create)
        return ret


class TaxCodeRelation(ModelSQL):
    '''
    AEAT 111 TaxCode Mapping Codes Relation
    '''
    __name__ = 'aeat.111.mapping-account.tax.code'

    mapping = fields.Many2One('aeat.111.mapping', 'Mapping', required=True)
    code = fields.Many2One('account.tax.code', 'Tax Code', required=True)


class TaxCodeMapping(ModelSQL, ModelView):
    '''
    AEAT 111 TaxCode Mapping
    '''
    __name__ = 'aeat.111.mapping'

    company = fields.Many2One('company.company', 'Company',
        ondelete="RESTRICT")
    aeat111_field = fields.Many2One('ir.model.field', 'Field',
        domain=[('module', '=', 'aeat_111')], required=True)
    code = fields.Many2Many('aeat.111.mapping-account.tax.code', 'mapping',
        'code', 'Tax Code')
    code_by_companies = fields.Function(
        fields.Many2Many('aeat.111.mapping-account.tax.code', 'mapping',
        'code', 'Tax Code'), 'get_code_by_companies')
    template = fields.Many2One('aeat.111.template.mapping', 'Template')

    @classmethod
    def __setup__(cls):
        super(TaxCodeMapping, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('aeat111_field_uniq', Unique(t, t.company, t.aeat111_field),
                'Field must be unique.')
            ]

    @staticmethod
    def default_company():
        return Transaction().context.get('company') or None

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


class Report(Workflow, ModelSQL, ModelView):
    '''
    AEAT 111 Report
    '''
    __name__ = 'aeat.111.report'

    company = fields.Many2One('company.company', 'Company', required=True,
        states={
            'readonly': Eval('state').in_(['done', 'calculated']),
            }, depends=['state'])
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
            }, depends=_DEPENDS)
    company_vat = fields.Char('VAT')
    company_surname = fields.Char('Company Surname')
    company_name = fields.Char('Company Name')
    year = fields.Integer("Year", required=True, states={
            'readonly': Eval('state').in_(['done', 'calculated']),
            }, depends=_DEPENDS)
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
                }, depends=_DEPENDS)

    work_productivity_monetary_parties = fields.Integer(
        "Work Productivity Monetary Parties")
    work_productivity_monetary_payments = fields.Numeric(
        "Work Productivity Monetary Payments", digits=(15, 2))
    work_productivity_monetary_withholdings_amount = fields.Numeric(
        "Work Productivty Monetary Withholdings Amount", digits=(15, 2))

    work_productivity_in_kind_parties = fields.Integer(
        "Work Productivity In-Kind Parties")
    work_productivity_in_kind_value_benefits = fields.Numeric(
        "Work Productivity In-Kind Value Benefits", digits=(15, 2))
    work_productivity_in_kind_payments_amount = fields.Numeric(
        "Work Productivity In-Kind Payments Amount", digits=(15, 2))

    economic_activities_productivity_monetary_parties = fields.Integer(
        "Economic Activities Productivity Monetary Parties")
    economic_activities_productivity_monetary_payments = fields.Numeric(
        "Economic Activities Productivity Monetary",
        digits=(15, 2))
    economic_activities_productivity_monetary_withholdings_amount = (
        fields.Numeric(
            "Economic Activities Productivity Monetary Withholdings Amount",
            digits=(15, 2)))

    economic_activities_productivity_in_kind_parties = fields.Integer(
        "Economic Activities Productivity In-Kind Parties")
    economic_activities_productivity_in_kind_value_benefits = fields.Numeric(
        "Economic Activities Productivity In-Kind Value Benefits",
        digits=(15, 2))
    economic_activities_productivity_in_kind_payments_amount = fields.Numeric(
        "Economic Activities Productivity In-Kind Payments Amount",
        digits=(15, 2))

    awards_monetary_parties = fields.Integer("Awards Monetary Parties")
    awards_monetary_payments = fields.Numeric(
        "Awards Monetary Payments", digits=(15, 2))
    awards_monetary_withholdings_amount = fields.Numeric(
        "Awards Monetary Withholdings Amount", digits=(15, 2))

    awards_in_kind_parties = fields.Integer("Awards In-Kind Parties")
    awards_in_kind_value_benefits = fields.Numeric(
        "Awards In-Kind Value Benefits", digits=(15, 2))
    awards_in_kind_payments_amount = fields.Numeric(
        "Awards In-Kind Payments Amount", digits=(15, 2))

    gains_forestry_exploitation_monetary_parties = fields.Integer(
        "Gains Forestry Exploitation Monetary Parties")
    gains_forestry_exploitation_monetary_payments = fields.Numeric(
        "Gains Forestry Exploitation Monetary Payments", digits=(15, 2))
    gains_forestry_exploitation_monetary_withholdings_amount = fields.Numeric(
        "Gains Forestry Exploitation Monetary Withholdings Amount",
        digits=(15, 2))

    gains_forestry_exploitation_in_kind_parties = fields.Integer(
        "Gains Forestry Exploitation In-Kind Parties")
    gains_forestry_exploitation_in_kind_value_benefits = fields.Numeric(
        "Gains Forestry Exploitation In-Kind Value Benefits", digits=(15, 2))
    gains_forestry_exploitation_in_kind_payments_amount = fields.Numeric(
        "Gains Forestry Exploitation In-Kind Payments Amount", digits=(15, 2))

    image_rights_parties = fields.Integer("Image Rights Parties")
    image_rights_service_payments = fields.Numeric(
        "Image Rights Service Payments", digits=(15, 2))
    image_rights_payments_amount = fields.Numeric(
        "Image Rights Payments Amount", digits=(15, 2))

    withholdings_payments_amount = fields.Function(fields.Numeric(
            "Withholding and Payments", digits=(15, 2)),
        'get_withholdings_payments_amount')
    to_deduce = fields.Numeric("To Deduce", digits=(15, 2),
        help="Exclusively in case of complementary self-assessment."
        "Results to be entered from previous self-assessments for the same "
        "concept, year and period")
    result = fields.Function(fields.Numeric("Result", digits=(15, 2)),
        'get_result')

    complementary_declaration = fields.Boolean("Complementary Declaration")
    previous_declaration_receipt = fields.Char("Previous Declaration Receipt",
        size=13, states={
            'required': Bool(Eval('complementary_declaration')),
            }, depends=['complementary_declaration'])
    company_party = fields.Function(fields.Many2One('party.party',
            'Company Party', context={
                'company': Eval('company'),
            }, depends=['company']), 'on_change_with_company_party')
    bank_account = fields.Many2One('bank.account', "Bank Account",
        domain=[
            ('owners', '=', Eval('company_party')),
            ], states={
            'required': Eval('type').in_(['U', 'D', 'X']),
            }, depends=['company_party', 'type'])

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
        super(Report, cls).__setup__()
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

    #@classmethod
    #def default_company_surnname(cls):
    #    pool = Pool()
    #    Company = pool.get('company.company')
    #    company_id = cls.default_company()
    #    if company_id:
    #        return Company(company_id).party.name.upper()

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
    def default_work_productivity_monetary_payments():
        return _ZERO

    @staticmethod
    def default_work_productivity_monetary_withholdings_amount():
        return _ZERO

    @staticmethod
    def default_work_productivity_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_work_productivity_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_economic_activities_productivity_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_economic_activities_productivity_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_awards_monetary_payments():
        return _ZERO

    @staticmethod
    def default_awards_monetary_withholdings_amount():
        return _ZERO

    @staticmethod
    def default_awards_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_awards_in_kind_payments_amount():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_monetary_payments():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_monetary_withholdings_amount():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_in_kind_value_benefits():
        return _ZERO

    @staticmethod
    def default_gains_forestry_exploitation_in_kind_payments_amount():
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

    def pre_validate(self):
        super().pre_validate()
        self.check_year_digits()

    @fields.depends('year')
    def check_year_digits(self):
        if self.year and len(str(self.year)) != 4:
            raise UserError(
                gettext('aeat_111.msg_invalid_year',
                    year=self.year))

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
            self.work_productivity_monetary_withholdings_amount
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
    def validate(cls, reports):
        for report in reports:
            report.check_euro()
            report.check_party_length()

    def check_euro(self):
        if (self.currency and self.company
                and self.currency.code != self.company.currency.code):
            raise UserError(gettext('aeat_111.msg_invalid_currency',
                name=self.rec_name,
                ))

    def check_party_length(self):
        columns = [x for x in self.__class__._fields if x.endswith('_parties')]
        for column in columns:
            value = getattr(self, column, None)
            if not value:
                continue
            if value > 15:
                raise UserError(gettext('aeat_111.msg_number_of_parties_to_hight',
                    name=value,
                    ))

    @classmethod
    @ModelView.button
    @Workflow.transition('calculated')
    def calculate(cls, reports):
        pool = Pool()
        Mapping = pool.get('aeat.111.mapping')
        Period = pool.get('account.period')
        TaxCode = pool.get('account.tax.code')
        Tax = pool.get('account.tax')
        TaxLine = pool.get('account.tax.line')
        Invoice = pool.get('account.invoice')

        for report in reports:
            mapping = {}
            for mapp in Mapping.search([
                    ('company', '=', report.company),
                    ]):
                for code in mapp.code_by_companies:
                    mapping[code.id] = mapp.aeat111_field.name

            period = report.period
            if 'T' in period:
                period = period[0]
                start_month = (int(period) - 1) * 3 + 1
                end_month = start_month + 2
            else:
                start_month = int(period)
                end_month = start_month

            year = report.year
            lday = calendar.monthrange(year, end_month)[1]
            periods = [p.id for p in Period.search([
                    ('start_date', '>=', datetime.date(year, start_month, 1)),
                    ('end_date', '<=', datetime.date(year, end_month, lday)),
                    ('company', '=', report.company),
                    ])]

            for field in mapping.values():
                setattr(report, field, _ZERO)

            # As only map the Economic Activities, only need to control its
            # parties.
            parties = set()
            with Transaction().set_context(periods=periods):
                for code in TaxCode.browse(mapping.keys()):
                    value = getattr(report, mapping[code.id])
                    amount = value + code.amount
                    setattr(report, mapping[code.id], abs(amount))

                    # To count the numebr of parties we have to do it from the
                    # party in the realted moves of all codes used for the
                    # amount calculation
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
                        for tax_line in TaxLine.search(domain):
                            if (tax_line.move_line and tax_line.move_line.move
                                    and isinstance(tax_line.move_line.move.origin,
                                        Invoice)):
                                parties.add(tax_line.move_line.move.origin.party)
            report.economic_activities_productivity_monetary_parties = (
                len(parties) if parties else 0)
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
        pass

    def create_file(self):
        header = Record(aeat111.HEADER_RECORD)
        footer = Record(aeat111.FOOTER_RECORD)
        record = Record(aeat111.RECORD)
        print("=======", [x for x in self.__class__._fields])
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
