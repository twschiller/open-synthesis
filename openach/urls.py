from django.conf.urls import url

from . import views

app_name = 'openach'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^boards/(?P<board_id>[0-9]+)/$', views.detail, name='detail'),
]
