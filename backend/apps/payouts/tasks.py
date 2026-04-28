import random
import time
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .exceptions import InvalidTransitionError
from .models import Payout, PayoutStatus
from .services import (
    dispatch_pending_events,
    fail_payout_and_return_funds,
    mark_payout_for_retry,
    transition_payout_status,
)


@shared_task(bind=True, max_retries=3)
def process_payout_task(self, payout_id: int):
    try:
        transition_payout_status(payout_id, PayoutStatus.PROCESSING)
    except (Payout.DoesNotExist, InvalidTransitionError):
        return

    outcome = random.random()

    if outcome < 0.70:
        time.sleep(random.uniform(1, 3))
        try:
            transition_payout_status(payout_id, PayoutStatus.COMPLETED)
        except InvalidTransitionError:
            return
    elif outcome < 0.90:
        time.sleep(random.uniform(0.5, 2))
        try:
            fail_payout_and_return_funds(payout_id)
        except InvalidTransitionError:
            return
    else:
        time.sleep(40)


@shared_task
def retry_stuck_payouts():
    cutoff = timezone.now() - timedelta(seconds=30)
    stuck_payouts = Payout.objects.filter(
        status=PayoutStatus.PROCESSING,
        processing_started_at__lt=cutoff,
    )

    for payout in stuck_payouts:
        if payout.attempt_count >= 3:
            try:
                fail_payout_and_return_funds(payout.id)
            except InvalidTransitionError:
                continue
            continue

        updated = mark_payout_for_retry(payout.id)
        if not updated:
            continue

        delay = 30 * (2 ** payout.attempt_count)
        process_payout_task.apply_async(args=[payout.id], countdown=delay)


@shared_task
def dispatch_outbox_events():
    dispatch_pending_events()
