#!/usr/bin/env bash
# ============================================================
# CodeNova — Vercel Build Script
# Runs during Vercel deployment to collect static files.
# ============================================================
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt --quiet

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Build complete."
