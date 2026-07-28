import pandas as pd
from sqlalchemy import Table, MetaData, Column, Integer, String
from sqlalchemy.dialects.postgresql import insert
meta = MetaData()
tbl = Table('customers', meta, Column('customer_id', Integer, primary_key=True), Column('name', String))
stmt = insert(tbl).values([{'customer_id': 1, 'name': 'test'}])
excluded = stmt.excluded
print("name" in excluded)
try:
    set_={c: excluded[c] for c in ['name'] if c in excluded}
    print(set_)
except Exception as e:
    import traceback
    traceback.print_exc()
