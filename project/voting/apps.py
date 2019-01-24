import sys

from django.apps import AppConfig
from django.utils import timezone

from .scheduler import Scheduler


class VotingConfig(AppConfig):
    name = 'project.voting'

    # db related configs
    maximum_rows_per_request = 1000

    # Voting configs
    check_ip_address = False
    generate_report_on_close = True
    activate_close_retry_count = 5
    min_voting_duration = timezone.timedelta(minutes=1)

    # Scheduler configs (uncomment and change)
    # process_pool = False
    # process_worker_count = 1
    # thread_worker_count = 5
    # misfire_grace_time = 20

    def ready(self):
        if 'runserver' not in sys.argv:
            return True

        from .models import Voting, VotingStatus, get_voting_queryset
        from .admin import activate_voting, close_voting

        scheduler = Scheduler()
        waiting_votings = get_voting_queryset(VotingStatus.WAITING_BEGINNING, sort='-end_date').all()

        for index in range(len(waiting_votings)):
            now = job_start_time = timezone.now()
            job_name = "ACTIVATE '{}' voting".format(waiting_votings[index].title)

            if waiting_votings[index].end_date <= now:
                # change for all other votings status to EXPIRED cuz
                # they are sorted by descending end_date column
                ids = [voting.id for voting in waiting_votings[index:]]
                Voting.objects.filter(pk__in=list(ids)).update(status=VotingStatus.EXPIRED)

                # todo change to logging
                print("Set to EXPIRED state {} votings".format(len(ids)))
                break
            elif now < waiting_votings[index].start_date:
                job_start_time = waiting_votings[index].start_date

            job_id = waiting_votings[index].id
            # todo change to logging
            print("Add job: {}[{}]".format(job_name, job_id))
            scheduler.aps.add_job(activate_voting, 'date', id=str(job_id), name=job_name, run_date=job_start_time,
                                  args=[waiting_votings[index]])

        # set to FINISHED state all active votings with expired end date and have at least one vote
        active_votings_queryset = get_voting_queryset(VotingStatus.ACTIVE, to=timezone.now())
        active_votings = active_votings_queryset.filter(votingcandidate__candidatevotes__isnull=False)
        ids = [voting.id for voting in active_votings]
        Voting.objects.filter(pk__in=list(ids)).update(status=VotingStatus.FINISHED)

        if len(active_votings):
            # todo change to logging
            print("Set to FINISHED state {} votings".format(len(active_votings)))

        active_votings = get_voting_queryset(VotingStatus.ACTIVE, sort='-end_date').all()
        for index in range(len(active_votings)):
            now = timezone.now()
            end_date = active_votings[index].end_date
            if end_date <= now:
                ids = [voting.id for voting in active_votings[index:]]
                Voting.objects.filter(pk__in=list(ids)).update(status=VotingStatus.FINISHED_WITHOUT_VOTERS)

                # todo change to logging
                print("Set to FINISHED_WITHOUT_VOTERS state {} votings".format(len(ids)))
                break

            job_id = active_votings[index].id
            job_name = "CLOSE '{}' voting".format(active_votings[index].title)
            # todo change to logging
            print("Add job: {}[{}]".format(job_name, job_id))
            scheduler.aps.add_job(close_voting, 'date', id=str(job_id), name=job_name, run_date=end_date,
                                  args=[active_votings[index]])
