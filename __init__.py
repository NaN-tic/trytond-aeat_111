# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.pool import Pool
from . import aeat


def register():
    Pool.register(
        aeat.Report,
        aeat.TemplateMapping,
        aeat.TemplateAccountRelation,
        aeat.TemplateTaxCodeRelation,
        aeat.Mapping,
        aeat.AccountRelation,
        aeat.TaxCodeRelation,
        module='aeat_111', type_='model')
    Pool.register(
        aeat.CreateChart,
        aeat.UpdateChart,
        module='aeat_111', type_='wizard')
