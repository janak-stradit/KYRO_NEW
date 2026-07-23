#!/bin/bash
# Query PostgreSQL to show customer count

echo "📊 Querying database for customer count..."
echo ""

PGPASSWORD=kyro_pass psql -h localhost -p 5434 -U kyro_user -d kyro_aml -c "SELECT COUNT(*) as total_customers FROM app.customers;"

echo ""
echo "📝 Sample customers (first 5):"
PGPASSWORD=kyro_pass psql -h localhost -p 5434 -U kyro_user -d kyro_aml -c "SELECT id, full_name, email, risk_level FROM app.customers LIMIT 5;"
