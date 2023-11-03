# This file is part aeat_111 module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool

def register():
    Pool.register(
        module='aeat_111', type_='model')
    Pool.register(
        module='aeat_111', type_='wizard')
    Pool.register(
        module='aeat_111', type_='report')
