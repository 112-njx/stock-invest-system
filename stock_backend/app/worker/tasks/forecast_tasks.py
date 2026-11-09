from app.services import forecast_runs
from app.worker.celery_app import celery_app


@celery_app.task(ignore_result=True)
def run_forecast(run_id: int):
    forecast_runs.execute(run_id)


@celery_app.task(ignore_result=True, time_limit=55)
def sweep_forecasts():
    forecast_runs.sweep()
