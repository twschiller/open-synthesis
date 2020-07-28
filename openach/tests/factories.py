#  Open Synthesis, an open platform for intelligence analysis
#  Copyright (C) 2016-2020 Open Synthesis Contributors. See CONTRIBUTING.md
#  file at the top-level directory of this distribution.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
import factory
from django.utils import timezone

from openach import models


class BoardFactory(factory.DjangoModelFactory):
    class Meta:
        model = models.Board

    board_title = factory.Sequence(lambda x: f"Board Title {x}")

    pub_date = factory.LazyFunction(timezone.now)

    board_desc = "Description"

    @factory.post_generation
    def teams(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.permissions.teams.set(extracted, clear=True)

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.permissions.update_all(extracted)


class TeamFactory(factory.DjangoModelFactory):
    class Meta:
        model = models.Team

    name = factory.Sequence(lambda x: f"Team {x}")

    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.members.set([self.owner, *extracted], clear=True)
