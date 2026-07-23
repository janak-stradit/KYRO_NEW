import psycopg
from generator.data_generator import generate_dataset

DATABASE_URL = "postgresql://kyro_user:kyro_pass@localhost:5434/kyro_aml"

def fast_populate():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for start_id in range(1, 10001, 1000):
                print(f"Generating from {start_id} to {start_id + 999}...")
                dataset = generate_dataset(1000, start_id)
                
                # Insert Customers
                print("Inserting customers...")
                cur.executemany(
                    "INSERT INTO raw_data.customers (customer_id, full_name, email, phone, date_of_birth, country, residency_country, kyc_status, pep_flag, sanctions_flag, adverse_media_flag, risk_level, risk_score, customer_type) VALUES (%(customer_id)s, %(full_name)s, %(email)s, %(phone)s, %(date_of_birth)s, %(country)s, %(residency_country)s, %(kyc_status)s, %(pep_flag)s, %(sanctions_flag)s, %(adverse_media_flag)s, %(risk_level)s, %(risk_score)s, %(customer_type)s)",
                    dataset["customers"]
                )
                
                # Insert Accounts
                print("Inserting accounts...")
                cur.executemany(
                    "INSERT INTO raw_data.accounts (account_id, customer_id, account_type, account_status, currency, balance, opened_date, account_metadata) VALUES (%(account_id)s, %(customer_id)s, %(account_type)s, %(account_status)s, %(currency)s, %(balance)s, %(opened_date)s, '{}'::jsonb)",
                    dataset["accounts"]
                )
                
                # Insert Transactions
                print("Inserting transactions...")
                cur.executemany(
                    "INSERT INTO raw_data.transactions (transaction_id, customer_id, account_id, transaction_date, transaction_type, amount, currency, risk_flags, source_system, meta_counterparty, meta_counterparty_type, meta_location, meta_country, meta_country_code, meta_destination_country, meta_origin_country, meta_source) VALUES (%(transaction_id)s, %(customer_id)s, %(account_id)s, %(transaction_date)s, %(transaction_type)s, %(amount)s, %(currency)s, to_jsonb(%(risk_flags)s::text), %(source_system)s, %(meta_counterparty)s, %(meta_counterparty_type)s, %(meta_location)s, %(meta_country)s, %(meta_country_code)s, %(meta_destination_country)s, %(meta_origin_country)s, %(meta_source)s)",
                    dataset["transactions"]
                )
                conn.commit()
                print(f"Batch inserted! Total: {start_id + 999} / 10000")

if __name__ == "__main__":
    fast_populate()
