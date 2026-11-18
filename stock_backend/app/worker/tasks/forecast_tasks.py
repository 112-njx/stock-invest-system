from app.services import forecast_replay, forecast_runs
from app.worker.celery_app import celery_app


@celery_app.task(ignore_result=True, acks_late=True, reject_on_worker_lost=True)
def run_forecast(run_id: int):
    forecast_runs.execute(run_id)


@celery_app.task(ignore_result=True, acks_late=True, reject_on_worker_lost=True, time_limit=55)
def sweep_forecasts():
    if forecast_runs.sweep():
        sweep_forecasts.delay()


@celery_app.task(ignore_result=True, acks_late=True, reject_on_worker_lost=True, time_limit=3000)
def replay_forecasts():
    if forecast_replay.work_once():
        replay_forecasts.delay()
