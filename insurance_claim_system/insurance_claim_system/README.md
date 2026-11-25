# Digital Insurance Claim Processing System

A simple base project built with **Python, Flask and SQLite**.

## Features
- Customer registration / login (a demo policy is created automatically)
- Customers file claims with an optional document upload (PDF/PNG/JPG)
- Automatic validation rules (`rules.py`):
  - policy period check, remaining-coverage check
  - duplicate-claim and high-amount fraud flags
  - auto-approval for clean claims up to 5,000; others go to manual review
- Adjuster dashboard: review, approve (with amount) or reject claims, create policies
- Full claim status history / audit trail

## Run
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

**Adjuster login:** `adjuster` / `admin123`
Customers: register from the Register page.

## Structure
```
app.py          routes & logic
db.py           SQLite schema & helpers
rules.py        automatic claim-validation rules
templates/      HTML pages (Jinja2)
static/         CSS
uploads/        uploaded claim documents
```

## Ideas for extension
Email notifications, REST API, payment module, role-based admin panel,
ML-based fraud detection, PostgreSQL, Docker deployment.
