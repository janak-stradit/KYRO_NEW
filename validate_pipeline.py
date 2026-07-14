import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://kyro_user:kyro_pass@localhost:5434/kyro_aml")

def check_counts():
    tables = [
        "raw_data.customers", "raw_data.accounts", "raw_data.transactions",
        "warehouse.customers", "warehouse.accounts", "warehouse.transactions",
        "warehouse.countries", "warehouse.currencies",
        "feature_store.customer_features", "feature_store.transaction_features"
    ]
    print("=== Row Counts ===")
    with engine.connect() as conn:
        for t in tables:
            try:
                c = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"{t.ljust(40)}: {c}")
            except Exception as e:
                print(f"{t.ljust(40)}: ERROR")

def check_impurities():
    print("\n=== Impurity Checks ===")
    with engine.connect() as conn:
        # Check nulls in warehouse transactions
        null_check_q = """
            SELECT 
                COUNT(*) as total_rows,
                SUM(CASE WHEN currency_id IS NULL THEN 1 ELSE 0 END) as null_currencies,
                SUM(CASE WHEN meta_country_id IS NULL THEN 1 ELSE 0 END) as null_countries,
                SUM(CASE WHEN meta_counterparty IS NULL THEN 1 ELSE 0 END) as null_cpty
            FROM warehouse.transactions;
        """
        res = conn.execute(text(null_check_q)).fetchone()
        print(f"Total Transactions: {res[0]}")
        print(f"Null Currencies: {res[1]}")
        print(f"Null Countries: {res[2]}")
        print(f"Null Counterparties: {res[3]}")

        # Check for orphan records (referential integrity)
        orphans_q = """
            SELECT COUNT(*) FROM warehouse.transactions t
            LEFT JOIN warehouse.customers c ON t.customer_id = c.id
            WHERE c.id IS NULL;
        """
        orphans = conn.execute(text(orphans_q)).scalar()
        print(f"Orphan Transactions (No Valid Customer): {orphans}")
        
        orphans_acc_q = """
            SELECT COUNT(*) FROM warehouse.transactions t
            LEFT JOIN warehouse.accounts a ON t.account_id = a.id
            WHERE a.id IS NULL;
        """
        orphans_acc = conn.execute(text(orphans_acc_q)).scalar()
        print(f"Orphan Transactions (No Valid Account): {orphans_acc}")

        # Check duplicates
        dup_q = """
            SELECT transaction_id, COUNT(*) 
            FROM warehouse.transactions 
            GROUP BY transaction_id 
            HAVING COUNT(*) > 1;
        """
        dups = conn.execute(text(dup_q)).fetchall()
        print(f"Duplicate Transaction IDs: {len(dups)}")

if __name__ == "__main__":
    check_counts()
    check_impurities()
