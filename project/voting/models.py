import operator
import re
import time
from datetime import datetime, timedelta
from functools import reduce

from django.apps import apps
from django.db import models
from django.db.models import Q
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

from .errors import InvalidInputException


class Candidate(models.Model):
    class Meta:
        db_table = 'candidates'

    last_name = models.CharField(max_length=30)
    first_name = models.CharField(max_length=30)
    middle_name = models.CharField(max_length=30)
    age = models.PositiveIntegerField()
    biography = models.TextField(max_length=1024)
    photo = models.ImageField("Candidate's photo", upload_to="candidates_photo/", null=True, blank=True,
                              editable=True, default='candidates_photo/without_photo.png')

    created = models.DateTimeField(auto_now=True)
    modified = models.DateTimeField(auto_now=True)

    photo_thumbnail = ImageSpecField(source='photo', processors=[ResizeToFill(100, 100)], format='JPEG',
                                     options={'quality': 60})

    def full_name(self):
        return ' '.join([self.last_name, self.first_name, self.middle_name])


class VotingStatus(object):
    UNKNOWN = 0
    DRAFT = 1
    WAITING_BEGINNING = 2
    ACTIVE = 3
    FINISHED = 4
    FINISHED_WITHOUT_VOTERS = 5
    EXPIRED = 6

    STATUS_TO_STR_DICT = {
        UNKNOWN: 'UNKNOWN',
        DRAFT: 'DRAFT',
        WAITING_BEGINNING: 'WAITING',
        ACTIVE: 'ACTIVE',
        FINISHED: 'FINISHED',
        FINISHED_WITHOUT_VOTERS: 'FINISHED WITHOUT VOTERS',
        EXPIRED: 'EXPIRED'
    }


def _voting_default_start_datetime():
    start_date = datetime.now()
    start_date_hour = start_date.hour + 1 if start_date.minute < 50 else start_date.hour + 2

    if start_date_hour < 8 or start_date_hour >= 22:
        if start_date_hour >= 22:
            start_date += timedelta(days=1)
        start_date_hour = 8

    return start_date.replace(hour=start_date_hour, minute=0, second=0, microsecond=0)


def _voting_default_end_datetime():
    return _voting_default_start_datetime() + timedelta(days=1)


class Voting(models.Model):
    class Meta:
        db_table = 'votings'
        ordering = ['start_date']

    title = models.CharField(max_length=30)
    description = models.TextField(max_length=1024)
    start_date = models.DateTimeField(default=_voting_default_start_datetime)
    end_date = models.DateTimeField(default=_voting_default_end_datetime)
    candidates = models.ManyToManyField(Candidate, through='VotingCandidate')
    max_votes = models.PositiveIntegerField(
        "Maximum votes number for premature completion", default=0, blank=True)

    status = models.PositiveIntegerField(default=VotingStatus.UNKNOWN)
    created = models.DateTimeField(auto_now=True)
    modified = models.DateTimeField(auto_now=True)

    def status_str(self):
        return VotingStatus.STATUS_TO_STR_DICT[self.status]


class VotingCandidate(models.Model):
    class Meta:
        db_table = 'voting_candidates'
        unique_together = ('voting_id', 'candidate_id')

    voting_id = models.ForeignKey(Voting, on_delete=models.CASCADE)
    candidate_id = models.ForeignKey(Candidate, on_delete=models.CASCADE)


class CandidateVotes(models.Model):
    class Meta:
        db_table = 'candidate_votes'

    voting_candidate_ids = models.ForeignKey(VotingCandidate, on_delete=models.CASCADE)
    ip_address = models.CharField(max_length=30)


def get_voting_queryset(status=None, **kwargs):
    verified_statuses = []
    date_format = '%Y-%m-%d'

    if status is None:
        verified_statuses = [status for status in VotingStatus.STATUS_TO_STR_DICT.keys()]
    elif isinstance(status, int):
        if status in VotingStatus.STATUS_TO_STR_DICT.keys():
            verified_statuses.append(status)
    elif isinstance(status, (list, tuple)) or isinstance(status, str):
        temp_status_list = []
        inverted_status_dict = {v: k for k, v in VotingStatus.STATUS_TO_STR_DICT.items()}

        if isinstance(status, str):
            status = [status]

        for st in status:
            if st in VotingStatus.STATUS_TO_STR_DICT:
                temp_status_list.append(st)
                continue
            else:
                st = re.sub('[\s_]+', ' ', str(st)).strip().upper()
                if st in VotingStatus.STATUS_TO_STR_DICT.values():
                    temp_status_list.append(inverted_status_dict[st])
                    continue

            temp_status_list = []
            break

        verified_statuses = temp_status_list

    if not verified_statuses:
        if not status:
            raise InvalidInputException('status', 'required argument not supplied')
        raise InvalidInputException('status', 'invalid argument value')
    elif kwargs.get('restrict_status', None):
        for status in verified_statuses:
            if status not in [VotingStatus.ACTIVE, VotingStatus.FINISHED]:
                raise InvalidInputException('status', 'invalid argument value', {
                    'must be': 'ACTIVE[{}] or FINISHED[{}]'.format(VotingStatus.ACTIVE, VotingStatus.FINISHED)})

    # queryset which return votings with supplied statuses
    queryset = Voting.objects.filter(reduce(operator.or_, (Q(status=status) for status in verified_statuses)))

    # validation to - from arguments
    start_date = kwargs.get('from', None)
    end_date = kwargs.get('to', None)

    if start_date:
        try:
            start_date = datetime.strptime(str(start_date).split(' ')[0], date_format)
            queryset = queryset.filter(start_date__gte=start_date)
        except:
            raise InvalidInputException('from', 'invalid argument value', {'format': date_format})

    if end_date:
        try:
            end_date = datetime.strptime(str(end_date).split(' ')[0], date_format)
            queryset = queryset.filter(end_date__lte=end_date)
        except:
            raise InvalidInputException('to', 'invalid argument value', {'format': date_format})

    if start_date and end_date and start_date > end_date:
        raise InvalidInputException('to', 'must be less or equal from')

    # sort argument validation
    sort_by_cols = kwargs.get('sort', None)
    if sort_by_cols:
        valid_col_names = [col.name for col in Voting._meta.get_fields()]
        if isinstance(sort_by_cols, str):
            sort_by_cols = [col.strip().lower() for col in sort_by_cols.split(',')]

        if isinstance(sort_by_cols, (list, tuple)):
            for col in sort_by_cols:
                desc_asc = ''  # sort by ascending value by default
                col = str(col).strip()
                if col[0] in '-+':
                    if col[0] == '-':
                        desc_asc = '-'
                    col = col[1:]
                if col not in valid_col_names:
                    raise InvalidInputException('sort', 'invalid argument value[{}]'.format(col))
                queryset = queryset.order_by(desc_asc + col)
        else:
            raise InvalidInputException('sort', 'invalid argument')

    return queryset


def try_update_voting_status(voting, status):
    ok_template = "Status for voting '{title}' [id:{id}] successfully set to {status}"
    fail_template = "Unable to set {status} status for voting '{title}' [id:{id}]: {err}"
    status_str = VotingStatus.STATUS_TO_STR_DICT[status]

    try:
        Voting.objects.filter(pk=voting.id).update(status=status)
        return True
    except BaseException as db_err:
        # todo change to logging
        print(fail_template.format(id=voting.id, title=voting.title, status=status_str, err=db_err))
        config = apps.get_app_config('voting')
        for attempt in range(getattr(config, 'activate_close_retry_count', 0)):
            try:
                Voting.objects.filter(pk=voting.id).update(status=status)
                print(('[Attempt {attempt}]' + ok_template).
                      format(attempt=attempt + 1, id=voting.id, title=voting.title, status=status_str))
                return True
            except BaseException as db_err:
                # todo change to logging
                print(('[Attempt {attempt}]' + fail_template).
                      format(attempt=attempt + 1, id=voting.id, title=voting.title, status=status_str, err=db_err))
                time.sleep(5)
        return False
