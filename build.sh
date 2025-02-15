#!/usr/bin/env bash
set -o errexit

# Make build.sh executable
chmod a+x build.sh

# Install Python dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --no-input

# Run migrations
python manage.py migrate