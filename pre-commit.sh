#!/bin/sh

set -e

# Format with Black
black errantbot/*.py

if [[ -n $(git diff) ]]; then
    echo "Formatted with Black"
fi

DBNAME=$(python - <<EOF
from errantbot import helper
print(helper.get_secrets()["database"]["name"])
EOF
      )

# Export schema
./export_schema.sh $DBNAME

if [[ -n $(git diff schema.sql) ]]; then
    echo "Changed database schema file"
fi

if [[ -n $(git diff) ]]; then
    echo "Changed files; add the changes and re-commit"
    exit 1
fi
