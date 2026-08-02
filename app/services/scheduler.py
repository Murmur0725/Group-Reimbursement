from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.notion_sync import sync_notion_reimbursements

_scheduler: BackgroundScheduler | None = None


def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    for hour in (9, 13, 18, 22):
        scheduler.add_job(
            sync_notion_reimbursements,
            CronTrigger(hour=hour, minute=0),
            kwargs={"mode": "scheduled"},
            id=f"notion_sync_{hour}",
            replace_existing=True,
            max_instances=1,
        )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None

