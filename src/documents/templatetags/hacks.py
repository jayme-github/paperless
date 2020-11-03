import re

from django.contrib.admin.templatetags.admin_list import (
    result_headers,
    result_hidden_fields,
    results
)
from django.template import Library


EXTRACT_URL = re.compile(r'href="(.*?)"')

register = Library()


def add_doc_edit_url(result):
    """
    Make the document edit URL accessible to the view as a separate item
    """
    title = result[1]
    match = re.search(EXTRACT_URL, title)
    edit_doc_url = match.group(1)
    result.append(edit_doc_url)
    return result
