import psycopg
from app.utils.security import hash_password

DB_URL = "postgresql://kyro_user:kyro_pass@kyro_postgres:5432/kyro_aml"

def fix_pass():
    hp = hash_password("kyro123")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE app.users SET hashed_password = %s WHERE username = 'analyst'", (hp,))
            conn.commit()
            print("Password updated!")

if __name__ == "__main__":
    fix_pass()
