from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from recommends.providers import RecommendationProvider
from recommends.providers import recommendation_registry

from .models import Board, Evaluation

class BoardRecommendationProvider(RecommendationProvider):
    def get_users(self):
        return User.objects.filter(is_active=True, evaluations__isnull=False).distinct()

    def get_items(self):
        return Board.objects.all()

    def get_ratings(self, obj):
        return Evaluation.objects.filter(board=obj)

    def get_rating_score(self, rating):
        return rating.value

    def get_rating_site(self, rating):
        return Site.objects.get_current()

    def get_rating_user(self, rating):
        return rating.user

    def get_rating_item(self, rating):
        return rating.board

recommendation_registry.register(Evaluation, [Board], BoardRecommendationProvider)