from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Board


def index(request):
    latest_board_list = Board.objects.order_by('-pub_date')[:5]
    context = {
        'latest_board_list': latest_board_list,
    }
    return render(request, 'boards/index.html', context)


def about(request):
    return render(request, 'boards/about.html')


def detail(request, board_id):
    board = get_object_or_404(Board, pk=board_id)
    return render(request, 'boards/detail.html', {'board': board})

@login_required
def profile(request):
    return render(request, 'boards/profile.html')
