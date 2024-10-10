# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import PoolMeta
from trytond.model import fields
from trytond.i18n import gettext
from trytond.exceptions import UserError


class MoveLine(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    aeat111_register = fields.Many2One('aeat.111.report.register',
        'AEAT 111 Register', readonly=True)

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._check_modify_exclude.add('aeat111_register')

    @classmethod
    def check_aeat111(cls, lines):
        for line in lines:
            if line.aeat111_register:
                raise UserError(
                    gettext('aeat_111.msg_delete_move_line_in_111report',
                        line=line.rec_name,
                        report=line.aeat111_register.report,
                    ))

    @classmethod
    def delete(cls, lines):
        cls.check_aeat111(lines)
        super().delete(lines)
