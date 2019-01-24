from threading import Lock

from django.apps import apps
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.views.generic import ListView
from django_tables2 import RequestConfig

from .admin import close_voting
from .models import Voting, VotingStatus, VotingCandidate, CandidateVotes
from .tables import VotingTable, VotingCandidatesTable

mutex = Lock()


class VotingsView(ListView):
    model = Voting
    template_name = 'votings.html'
    ordering = ['start_date']

    def get_context_data(self, **kwargs):
        context = super(VotingsView, self).get_context_data(**kwargs)
        table = VotingTable(self.get_queryset())

        RequestConfig(self.request).configure(table)
        table.paginate(page=self.request.GET.get('page', 1), per_page=10)
        context['table'] = table
        return context

    def get_queryset(self):
        qs = super(VotingsView, self).get_queryset()
        status = self.kwargs['status']
        if not status or status == 'active':
            return qs.filter(status=VotingStatus.ACTIVE)

        if status == 'all':
            return qs.filter(status__in=[VotingStatus.ACTIVE, VotingStatus.FINISHED])

        return qs.filter(status=VotingStatus.FINISHED)


class VotingDetailsView(ListView):
    model = Voting
    template_name = 'voting_details.html'

    def get_context_data(self, **kwargs):
        context = super(VotingDetailsView, self).get_context_data(**kwargs)
        table = VotingCandidatesTable(self.table_date)
        context['table'] = table
        context['voting'] = self.voting
        return context

    def get_queryset(self):
        voting_id = self.kwargs['voting_id']
        # fetch voting by id with prefetched candidates
        self.voting = get_object_or_404(Voting.objects.filter(id=voting_id).prefetch_related())

        # select unique candidate's id
        candidate_ids = [candidate.id for candidate in self.voting.candidates.all()]
        candidate_ids = list(set(candidate_ids))

        # fill candidate_with_votes with tuple where first element is candidate object, second - candidate's votes
        # candidate_with_votes sorted by descending votes number
        self.table_date = []
        qs = VotingCandidate.objects.filter(candidate_id__in=candidate_ids, voting_id=voting_id)
        for candidate in qs.annotate(votes_num=Count('candidatevotes__ip_address')).order_by('-votes_num'):
            self.table_date.append({
                'photo': candidate.candidate_id.photo_thumbnail,
                'last_name': candidate.candidate_id.last_name,
                'first_name': candidate.candidate_id.first_name,
                'middle_name': candidate.candidate_id.middle_name,
                'age': candidate.candidate_id.age,
                'biography': candidate.candidate_id.biography,
                'votes_count': candidate.votes_num,
                'voting_id': voting_id,
                'candidate_id': candidate.candidate_id.id
            })


class SendVoteView(ListView):
    model = Voting
    template_name = 'vote_result.html'

    def get_context_data(self, **kwargs):
        context = super(SendVoteView, self).get_context_data(**kwargs)
        context['message'] = self.message
        return context

    def get_queryset(self):
        voting_id = self.kwargs['voting_id']
        candidate_id = self.kwargs['candidate_id']
        # prefetch voting object for subsequent status checking
        candidate = get_object_or_404(VotingCandidate.objects.filter(
            voting_id=voting_id, candidate_id=candidate_id).select_related('voting_id'))

        self.message = "Sorry, voting '{}' is over:(".format(candidate.voting_id.title)
        successful_vote_message = 'Thank you for your vote!'
        if candidate.voting_id.status != VotingStatus.ACTIVE:
            return

        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')

        # check attempt to vote second time by client IP
        if getattr(apps.get_app_config('voting'), 'check_ip_address', True) and \
                VotingCandidate.objects.filter(voting_id=voting_id, candidatevotes__ip_address__contains=ip).all():
            self.message = 'You already participated in the vote:('
            return

        if candidate.voting_id.max_votes > 0:
            mutex.acquire()
            if candidate.voting_id.status == VotingStatus.FINISHED:
                mutex.release()
                return

            candidate_votes = VotingCandidate.objects.filter(candidate_id=candidate_id, voting_id=voting_id). \
                annotate(votes_num=Count('candidatevotes__ip_address'))

            candidate_votes_number = candidate_votes[0].votes_num
            if candidate_votes_number >= candidate.voting_id.max_votes:
                close_voting(candidate.voting_id)
                mutex.release()
                return

            self.message = successful_vote_message
            CandidateVotes(voting_candidate_ids=candidate, ip_address=ip).save()
            if candidate_votes_number + 1 >= candidate.voting_id.max_votes:
                close_voting(candidate.voting_id)
            mutex.release()
        else:
            self.message = successful_vote_message
            CandidateVotes(voting_candidate_ids=candidate, ip_address=ip).save()
