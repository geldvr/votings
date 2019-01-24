from django import forms
from django.apps import apps
from django.contrib import admin
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

import project.voting.models as models
from .report import crete_voting_report
from .scheduler import Scheduler


class MembershipInline(admin.TabularInline):
    model = models.VotingCandidate
    extra = 0


class VotingForm(forms.ModelForm):
    class Meta:
        model = models.Voting
        fields = ['title', 'description', 'start_date', 'end_date', 'max_votes']

    def __init__(self, *args, **kwargs):
        super(VotingForm, self).__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)

        if instance and instance.id:

            if instance.status == models.VotingStatus.DRAFT:
                self.fields['draft'].initial = True
            elif instance.status == models.VotingStatus.ACTIVE:
                self.fields['draft'].disabled = True
                self.fields['start_date'].disabled = True
            elif instance.status == models.VotingStatus.FINISHED:
                for field in self.fields:
                    self.fields[field].widget.attrs['readonly'] = True

    draft = forms.BooleanField(help_text='Save voting as draft', initial=False, required=False)

    def clean_title(self):
        if len(self.cleaned_data['title']) < 5:
            raise forms.ValidationError('Title length must be greater or equal 5')
        return self.cleaned_data['title']

    def clean(self):
        # form with draft flag
        if self['draft'].value():
            if self.instance.status in [models.VotingStatus.ACTIVE, models.VotingStatus.FINISHED]:
                raise forms.ValidationError(
                    'Cannot change {} voting to DRAFT'.format(
                        models.VotingStatus.STATUS_TO_STR_DICT[self.instance.status]))
            self.instance.status = models.VotingStatus.DRAFT

        if self.instance.status == models.VotingStatus.UNKNOWN:
            self.instance.status = models.VotingStatus.WAITING_BEGINNING

        # skip start_date & end_date fields verification for draft voting
        if not self['draft'].value():
            skip_start_date_checking = False
            start_date = self.cleaned_data["start_date"]
            end_date = self.cleaned_data['end_date']

            if self.instance.pk is not None:
                if self.instance.status == models.VotingStatus.DRAFT:
                    self.instance.status = models.VotingStatus.WAITING_BEGINNING
                elif start_date == models.Voting.objects.get(pk=self.instance.pk).start_date:
                    skip_start_date_checking = True
                elif self.instance.status in [models.VotingStatus.ACTIVE, models.VotingStatus.FINISHED]:
                    raise forms.ValidationError(
                        'Cannot change start date for {} voting'.format(
                            models.VotingStatus.STATUS_TO_STR_DICT[self.instance.status]))
                else:
                    self.instance.status = models.VotingStatus.WAITING_BEGINNING

            if not skip_start_date_checking:
                minimum_start_date = timezone.now() + timezone.timedelta(minutes=1)
                if start_date < minimum_start_date:
                    self.add_error('start_date',
                                   "Voting's start date must be greater than {} (now + 5 min)"
                                   .format(timezone.localtime(minimum_start_date).strftime('%Y-%m-%d %H:%M:%S')))

            min_voting_duration = getattr(apps.get_app_config('voting'), 'min_voting_duration',
                                          timezone.timedelta(hours=1))

            if end_date < start_date:
                self.add_error('end_date', "Voting's end date must be greater than start date")

            elif end_date < start_date + min_voting_duration:
                self.add_error('end_date', "Voting's duration cannot be less than {}".format(min_voting_duration))


def activate_voting(voting):
    scheduler = Scheduler()
    scheduler.remove_job(voting.id)
    job_task, run_date = close_voting, voting.end_date
    job_name = "CLOSE '{}' voting[{}]".format(voting.title, voting.id)

    if not models.try_update_voting_status(voting, models.VotingStatus.ACTIVE):
        if voting.end_date < timezone.now() + timezone.timedelta(minutes=5):
            return
        job_task, run_date = activate_voting, timezone.now() + timezone.timedelta(minutes=1)
        job_name = "RETRY ACTIVATE '{}' voting[{}]".format(voting.title, voting.id)

    # todo change to logging
    print("Add job: {}".format(job_name))
    scheduler.aps.add_job(job_task, 'date', id=str(voting.id), name=job_name, run_date=run_date, args=[voting])


def close_voting(voting):
    scheduler = Scheduler()
    scheduler.remove_job(voting.id)
    run_date = timezone.now() + timezone.timedelta(minutes=1)

    if not models.try_update_voting_status(voting, models.VotingStatus.FINISHED):
        job_name = "RETRY CLOSE '{}' voting[{}]".format(voting.title, voting.id)
        scheduler.aps.add_job(close_voting, 'date', id=str(voting.id), name=job_name, run_date=run_date, args=[voting])
        return

    if getattr(apps.get_app_config('voting'), 'generate_report_on_close', False):
        job_name = "CREATE REPORT for '{}' voting[{}]".format(voting.title, voting.id)
        # todo change to logging
        print("Add job: {}".format(job_name))
        scheduler.aps.add_job(crete_voting_report, 'date', id=str(voting.id), name=job_name, run_date=run_date,
                              args=[voting])


@receiver(post_save, sender=models.Voting)
def _register_voting_activation(sender, **kwargs):
    scheduler = Scheduler()
    voting = kwargs['instance']

    if voting.status == models.VotingStatus.DRAFT:
        scheduler.remove_job(voting.id)
        return

    if voting.status == models.VotingStatus.WAITING_BEGINNING:
        scheduler.remove_job(voting.id)
        job_name = "ACTIVATE '{}' voting[{}]".format(voting.title, voting.id)
        # todo change to logging
        print("Add job: {}".format(job_name))
        scheduler.aps.add_job(activate_voting, 'date', id=str(voting.id), name=job_name, run_date=voting.start_date,
                              args=[voting])


@admin.register(models.Voting)
class VotingAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'created', 'status_str', 'id')
    inlines = [MembershipInline]
    form = VotingForm

    def status_str(self, obj):
        return obj.status_str()


@admin.register(models.Candidate)
class CandidatesAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'age', 'created')
    inlines = [MembershipInline]

    def full_name(self, obj):
        return obj.full_name()


@admin.register(models.VotingCandidate)
class VotingCandidatesAdmin(admin.ModelAdmin):
    pass
