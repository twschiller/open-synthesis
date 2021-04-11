import django_filters
from openach.models import Board
from django_filters import DateFilter, CharFilter



class BoardFilter(django_filters.FilterSet):
    # board_title = CharFilter(lookup_expr='iexact')
    board_title = CharFilter(lookup_expr='icontains', label="Board Title")
    # creator = CharFilter()
    


    class Meta:
        model = Board
        fields = '__all__'
        exclude = ['board_slug', 'board_desc', 'removed' ]


