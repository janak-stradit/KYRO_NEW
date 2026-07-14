import os
import psycopg
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://kyro_user:kyro_pass@localhost:5434/kyro_aml")

def check():
    queries = [
        """
        INSERT INTO warehouse.countries (id, code)
        SELECT gen_random_uuid(), COALESCE(country, 'UNKNOWN') FROM raw_data.customers GROUP BY COALESCE(country, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.countries (id, code)
        SELECT gen_random_uuid(), COALESCE(residency_country, 'UNKNOWN') FROM raw_data.customers GROUP BY COALESCE(residency_country, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.countries (id, code)
        SELECT gen_random_uuid(), COALESCE(meta_country_code, 'UNKNOWN') FROM raw_data.transactions GROUP BY COALESCE(meta_country_code, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.countries (id, code)
        SELECT gen_random_uuid(), COALESCE(meta_destination_country, 'UNKNOWN') FROM raw_data.transactions GROUP BY COALESCE(meta_destination_country, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.countries (id, code)
        SELECT gen_random_uuid(), COALESCE(meta_origin_country, 'UNKNOWN') FROM raw_data.transactions GROUP BY COALESCE(meta_origin_country, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.currencies (id, code)
        SELECT gen_random_uuid(), COALESCE(currency, 'UNKNOWN') FROM raw_data.accounts GROUP BY COALESCE(currency, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.currencies (id, code)
        SELECT gen_random_uuid(), COALESCE(currency, 'UNKNOWN') FROM raw_data.transactions GROUP BY COALESCE(currency, 'UNKNOWN')
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.kyc_statuses (id, status_code)
        SELECT gen_random_uuid(), kyc_status FROM raw_data.customers WHERE kyc_status IS NOT NULL GROUP BY kyc_status
        ON CONFLICT (status_code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.risk_levels (id, level_code, ordinal_rank, min_score, max_score)
        VALUES 
            (gen_random_uuid(), 'LOW', 1, 0, 33),
            (gen_random_uuid(), 'MEDIUM', 2, 33, 66),
            (gen_random_uuid(), 'HIGH', 3, 66, 100)
        ON CONFLICT (level_code) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.customers (id, customer_id, full_name, email, phone, date_of_birth, country_id, residency_country_id, kyc_status_id, kyc_last_review, pep_flag, sanctions_flag, adverse_media_flag, risk_level_id, risk_score, customer_type)
        SELECT 
            gen_random_uuid(), c.customer_id, c.full_name, c.email, c.phone, c.date_of_birth::date,
            co.id, co_res.id, kyc.id, c.kyc_last_review::date, c.pep_flag::boolean, c.sanctions_flag::boolean, c.adverse_media_flag::boolean,
            rl.id, c.risk_score::numeric, c.customer_type
        FROM raw_data.customers c
        LEFT JOIN warehouse.countries co ON c.country = co.code
        LEFT JOIN warehouse.countries co_res ON c.residency_country = co_res.code
        LEFT JOIN warehouse.kyc_statuses kyc ON c.kyc_status = kyc.status_code
        LEFT JOIN warehouse.risk_levels rl ON c.risk_level = rl.level_code
        ON CONFLICT (customer_id, wh_valid_from) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.accounts (id, account_id, customer_id, account_type, account_status, currency_id, balance, opened_date)
        SELECT
            gen_random_uuid(), a.account_id, wc.id, a.account_type, a.account_status, curr.id, a.balance::numeric, a.opened_date::date
        FROM raw_data.accounts a
        JOIN warehouse.customers wc ON a.customer_id = wc.customer_id
        LEFT JOIN warehouse.currencies curr ON a.currency = curr.code
        ON CONFLICT (account_id) DO NOTHING;
        """,
        """
        INSERT INTO warehouse.transactions (
            id, transaction_id, customer_id, account_id, transaction_date, 
            transaction_type, amount, currency_id, risk_flags, source_system, 
            meta_counterparty, meta_counterparty_type, meta_country_id, 
            meta_destination_country_id, meta_origin_country_id, raw_transaction_id
        )
        SELECT
            gen_random_uuid(), t.transaction_id, wc.id, wa.id, t.transaction_date::timestamptz, 
            t.transaction_type, t.amount::numeric, curr.id, t.risk_flags::jsonb, t.source_system, 
            COALESCE(t.meta_counterparty, 'UNKNOWN'), COALESCE(t.meta_counterparty_type, 'UNKNOWN'), co_meta.id, 
            co_dest.id, co_orig.id, t.id
        FROM raw_data.transactions t
        JOIN warehouse.customers wc ON t.customer_id = wc.customer_id
        JOIN warehouse.accounts wa ON t.account_id = wa.account_id
        LEFT JOIN warehouse.currencies curr ON COALESCE(t.currency, 'UNKNOWN') = curr.code
        LEFT JOIN warehouse.countries co_meta ON COALESCE(t.meta_country_code, 'UNKNOWN') = co_meta.code
        LEFT JOIN warehouse.countries co_dest ON COALESCE(t.meta_destination_country, 'UNKNOWN') = co_dest.code
        LEFT JOIN warehouse.countries co_orig ON COALESCE(t.meta_origin_country, 'UNKNOWN') = co_orig.code
        ON CONFLICT (transaction_id, transaction_date) DO NOTHING;
        """
    ]
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for i, q in enumerate(queries):
                res = conn.execute(text(q))
                print(f"Query {i} complete: {res.rowcount} rows affected.")
            trans.commit()
            print("All successful.")
        except Exception as e:
            trans.rollback()
            print("ERROR on query", i)
            print(e)

if __name__ == "__main__":
    check()
