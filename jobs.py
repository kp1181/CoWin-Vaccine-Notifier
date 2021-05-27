from apscheduler.schedulers.blocking import BlockingScheduler
from app import slotChecker
import sys

sched = BlockingScheduler()

@sched.scheduled_job('interval', minutes=1)
def print_data():
    print("Running scheduled job")
    sys.stdout.flush()
    slotChecker()

sched.start()