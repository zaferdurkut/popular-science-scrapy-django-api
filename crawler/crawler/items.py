from scrapy_djangoitem import DjangoItem

from api.models import ListOverview

__all__ = [
    'ListOverview'
]

class ListOverview(DjangoItem):
    django_model = ListOverview
    