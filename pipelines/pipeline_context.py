from core.company_context import CompanyContext


_CONTEXT = None


def set_context(context):

    global _CONTEXT

    _CONTEXT = context


def get_context():

    return _CONTEXT