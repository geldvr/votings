from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from django.apps import apps
from django.utils.timezone import get_current_timezone


class Scheduler(object):
    _instance = None
    _default_thread_worker_count = 5
    _default_process_worker_count = 1

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Scheduler, cls).__new__(cls, *args, **kwargs)
            executors = {
                'default': {
                    'type': 'threadpool',
                    'max_workers': cls._default_thread_worker_count
                }
            }
            config = apps.get_app_config('voting')
            twk = getattr(config, 'thread_worker_count', cls._default_thread_worker_count)
            if isinstance(twk, int) and 0 < twk < 20:
                executors['default']['max_workers'] = twk

            if getattr(config, 'process_pool', False):
                pwc = getattr(config, 'process_worker_count', cls._default_process_worker_count)
                process_worker_count = cls._default_process_worker_count
                if isinstance(pwc, int) and 0 < pwc < 10:
                    process_worker_count = pwc
                executors['processpool'] = ProcessPoolExecutor(max_workers=process_worker_count)

            job_defaults = {
                'coalesce': True,
                'max_instances': 3,
                'misfire_grace_time': getattr(config, 'misfire_grace_time', 20)
            }
            scheduler = BackgroundScheduler()
            scheduler.configure(executors=executors, job_defaults=job_defaults,
                                timezone=get_current_timezone())

            cls._instance._aps_scheduler = scheduler
            scheduler.start()
        return cls._instance

    def __init__(self):
        self.aps = self._instance._aps_scheduler

    def remove_job(self, job_id):
        previous_job = self.aps.get_job(str(job_id))
        if previous_job:
            print('Remove job: {}'.format(previous_job.name))
            previous_job.remove()
