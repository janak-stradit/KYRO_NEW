"""
scripts/seed_periodic_reviews.py — Schedules risk-based periodic KYC reviews.

Every customer without an open periodic review gets one, due one review cycle
after their last KYC review (or onboarding date if never reviewed):

    HIGH risk   every 3 months
    MEDIUM risk every 6 months
    LOW risk    every 12 months

Reviews whose due date has already passed are created as OVERDUE. Running the
script again only fills in customers that still have no open periodic review.

--backfill-last-review is for demo databases only: customers that have never
been reviewed get a synthetic kyc_last_review spread across their cycle, so the
schedule shows a realistic mix of overdue, due-soon and future reviews instead
of every review falling a full cycle after today.

Usage:
    python scripts/seed_periodic_reviews.py
    python scripts/seed_periodic_reviews.py --backfill-last-review
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models.customer import Customer, KYCReview

CYCLE_MONTHS = {"HIGH": 3, "MEDIUM": 6, "LOW": 12}
OPEN_STATUSES = ("SCHEDULED", "IN_PROGRESS", "OVERDUE")


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp to the last day of the target month (e.g. 31 Jan + 1 month)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(f"cannot add {months} months to {d}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill-last-review", action="store_true",
                        help="demo data: give never-reviewed customers a synthetic last review date")
    parser.add_argument("--seed", type=int, default=42, help="random seed for --backfill-last-review")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    today = date.today()
    db = SessionLocal()
    created = overdue = backfilled = 0
    try:
        already_open = {
            row[0]
            for row in db.query(KYCReview.customer_id)
            .filter(KYCReview.review_type == "PERIODIC", KYCReview.review_status.in_(OPEN_STATUSES))
            .all()
        }

        for customer in db.query(Customer).order_by(Customer.created_at).all():
            if customer.id in already_open:
                continue

            risk = customer.risk_level if customer.risk_level in CYCLE_MONTHS else "LOW"
            cycle = CYCLE_MONTHS[risk]

            if customer.kyc_last_review is None and args.backfill_last_review:
                # Last reviewed somewhere between ~1.2 cycles ago and today, so a
                # share of customers come out overdue or due soon.
                days_ago = rng.randint(0, int(cycle * 30.4 * 1.2))
                customer.kyc_last_review = datetime.now(timezone.utc) - timedelta(days=days_ago)
                backfilled += 1

            base = (customer.kyc_last_review or customer.created_at).date()
            due = add_months(base, cycle)
            status = "OVERDUE" if due < today else "SCHEDULED"
            overdue += status == "OVERDUE"

            db.add(KYCReview(
                customer_id=customer.id,
                review_type="PERIODIC",
                review_status=status,
                scheduled_date=due,
                risk_level_after=risk,
            ))
            created += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Scheduled {created} periodic reviews ({overdue} overdue)"
          + (f"; backfilled last review date for {backfilled} customers" if backfilled else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
