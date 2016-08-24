from django.db import models
import datetime
from django.utils import timezone


class Board(models.Model):
    board_title = models.CharField(max_length=200)
    board_desc = models.CharField(max_length=200)
    pub_date = models.DateTimeField('date published')

    def __str__(self):
        return self.board_title

    def was_published_recently(self):
        now = timezone.now()
        return now - datetime.timedelta(days=1) <= self.pub_date <= now


class Hypothesis(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    hypothesis_text = models.CharField(max_length=200)

    def __str__(self):
        return self.hypothesis_text


class Evidence(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    evidence_url = models.URLField()




