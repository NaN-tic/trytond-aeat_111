# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.pool import Pool
from . import aeat
from . import invoice
from . import move


def register():
    Pool.register(
        aeat.TemplateMapping,
        aeat.TemplateAccountRelation,
        aeat.TemplateTaxCodeRelation,
        aeat.Mapping,
        aeat.AccountRelation,
        aeat.TaxCodeRelation,
        aeat.Report,
        aeat.Register,
        invoice.Invoice,
        move.MoveLine,
        module='aeat_111', type_='model')
    Pool.register(
        aeat.CreateChart,
        aeat.UpdateChart,
        module='aeat_111', type_='wizard')
