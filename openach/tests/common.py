import datetime

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone

from openach.models import Board, BoardFollower, UserSettings

PASSWORD = 'commonpassword'
USERNAME_PRIMARY = 'john'
USERNAME_OTHER = 'paul'


def create_board(board_title, days):
    """Create a board with the given title and publishing date offset.

    :param board_title: the board title
    :param days: negative for boards published in the past, positive for boards that have yet to be published
    """
    time = timezone.now() + datetime.timedelta(days=days)
    return Board.objects.create(board_title=board_title, pub_date=time)


def remove(model):
    """Mark model as removed."""
    model.removed = True
    model.save()


def add_follower(board):
    """Create a user and have the user follow the given board."""
    follower = User.objects.create_user('bob', 'bob@thebeatles.com', 'bobpassword')
    BoardFollower.objects.create(
        user=follower,
        board=board,
    )
    return follower


class PrimaryUserTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(USERNAME_PRIMARY, f'{USERNAME_PRIMARY}@thebeatles.com', PASSWORD)
        self.other = User.objects.create_user(USERNAME_OTHER, f'{USERNAME_OTHER}@thebeatles.com', PASSWORD)
        UserSettings.objects.create(user=self.user)
        UserSettings.objects.create(user=self.other)

    def login(self):
        self.client.login(username=USERNAME_PRIMARY, password=PASSWORD)

    def logout(self):
        self.client.logout()
