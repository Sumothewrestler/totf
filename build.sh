#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --no-input

# Run migrations only if database is available
if [ "$DATABASE_URL" != "" ]; then
    python manage.py migrate
fi