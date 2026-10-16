# MediBridge — Healthcare Continuity Platform

## Problem Statement
Patients often have medical information scattered across prescriptions, reports, and personal notes. This can make it difficult to organise information before a doctor visit.

## Our Solution
MediBridge is a healthcare continuity prototype that helps users organise their personal profile, medical history, reports, and doctor-visit summaries in one place.

## Key Features
- Mobile number and PIN-based account creation and login
- Personal profile management
- Medical history records for past conditions, symptoms, medicines, stopped medicines, and allergies
- Upload support for PDF and image reports
- Doctor-visit summary with print-to-PDF
- Help assistant for navigation and general preparation
- SQLite database for persistent local records
- Basic login request rate limiting

## Technology Stack
- Python
- Flask
- SQLite
- HTML and CSS
- Werkzeug password hashing
- Flask-Limiter
- Browser print-to-PDF

## How to Run
1. Install Python 3.12 or a compatible version.
2. Open the project folder in VS Code.
3. Install dependencies in a virtual environment:
   `python -m venv .venv`
4. On Windows, install packages using:
   `.\.venv\Scripts\python.exe -m pip install flask flask-limiter reportlab`
5. Start the application:
   `.\.venv\Scripts\python.exe app.py`
6. Open `http://127.0.0.1:5000` in a browser.

## Demo Flow
1. Create a fictional demo account.
2. Complete the profile.
3. Add a sample medical history record.
4. Upload a non-sensitive sample report.
5. Generate a doctor-visit summary and print it as PDF.
6. Demonstrate the help assistant.

## Important Limitations
This is a local hackathon prototype, not a production-ready healthcare system. The assistant currently provides rule-based demo responses and is not connected to a real AI model. It does not diagnose conditions or prescribe treatment. Real patient data must not be used in this prototype.

## Privacy and Safety
Use fictional demo data only. Do not enter Aadhaar numbers, real PINs, or real medical records. A production version would require a security review, stronger session and upload protections, CSRF protection, secure deployment, backups, and appropriate privacy safeguards.
