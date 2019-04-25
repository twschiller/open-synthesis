# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/django_coverage_plugin/blob/master/NOTICE.txt

"""Django Template Coverage Plugin"""

from .plugin import DjangoTemplatePlugin
from .plugin import DjangoTemplatePluginException       # noqa


def coverage_init(reg, options):
    reg.add_file_tracer(DjangoTemplatePlugin())
