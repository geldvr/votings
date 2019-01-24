import django_tables2 as tables
from django.template import Template, Context
from django.utils.safestring import mark_safe
from django_tables2.utils import A

from .models import Voting, VotingStatus


class Truncate(tables.Column):
    max_cell_chars = 150

    def render(self, value):
        return (value[:self.max_cell_chars] + ' ...') if len(value) > self.max_cell_chars else value


class Status(tables.Column):
    def render(self, value):
        return VotingStatus.STATUS_TO_STR_DICT.get(value, 'UNKNOWN').title()


class VotingTable(tables.Table):
    title = tables.LinkColumn('voting_detail', args=[A('pk')])
    description = Truncate()
    start_date = tables.DateTimeColumn(format='d M Y, H:i')
    end_date = tables.DateTimeColumn(format='d M Y, H:i')
    status = Status()

    class Meta:
        model = Voting
        fields = ('title', 'description', 'start_date', 'end_date', 'status')
        template_name = 'django_tables2/bootstrap.html'


class ImageColumn(tables.Column):
    def render(self, value):
        template_str = """
            {% load static %}
            {% if not photo %}
                <img src="{% static "without_photo.jpg"%}"/>
            {% else %}
                <img src="{{ photo.url }}" />
            {% endif %}
        """
        # template = Template('<img src="{{ photo.url }}" />')
        template = Template(template_str)
        return mark_safe(template.render(Context({'photo': value})))


class VotingCandidatesTable(tables.Table):
    photo = ImageColumn()
    first_name = tables.Column()
    last_name = tables.Column()
    middle_name = tables.Column()
    age = tables.Column()
    biography = tables.Column()
    votes_count = tables.Column()
    vote = tables.LinkColumn('send_vote', args=[A('voting_id'), A('candidate_id')], empty_values=(), text='vote')
