<div align="center">
  <img src="https://upload.wikimedia.org/wikipedia/en/thumb/f/fa/Indian_Society_for_Technical_Education_logo.svg/1200px-Indian_Society_for_Technical_Education_logo.svg.png" alt="ISTE Logo" width="120" />

  <h1 align="center">ISTE Certificate Generation Hub</h1>

  <p align="center">
    An enterprise-grade, fully automated pipeline for generating, distributing, and verifying cryptographic certificates at scale. Built exclusively for the ISTE Student Chapter.
  </p>

  <p align="center">
    <a href="https://certificate-generator-app-iste.vercel.app"><strong>View Live Demo (Vercel)</strong></a>
    <br />
    <br />
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
    <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS" />
    <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=FastAPI&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
    <img src="https://img.shields.io/badge/Render-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Render" />
  </p>
</div>

<hr />

## 🌟 Overview

The **ISTE CertHub** is a high-performance web application designed to eliminate the manual labor of designing, rendering, and emailing event certificates. It features a stunning, state-of-the-art **Glassmorphism** user interface on the frontend and an asynchronous, highly resilient **Python/FastAPI** worker architecture on the backend. 

Whether generating a single certificate for a VIP speaker or dispatching 500+ certificates for a mega-event via Google Sheets, the pipeline ensures zero crashes, intelligent parsing, and beautiful PDF rendering.

<br />

## ✨ Core Features

### 🚀 Bulk & Single Processing Pipelines
- **Single Generation:** Instantly generate and email a customized certificate with a clean, distraction-free UI.
- **Bulk Pipeline (Data Source Agnostic):** Import data directly via a live **Google Sheets URL** or by uploading local **.CSV / .XLSX** files. 
- **Intelligent Ingestion Engine:** Automatically cleans messy data, converts names to Title Case, strips invalid emails, dynamically maps columns using fuzzy matching, and deduplicates entries to prevent email spam.

### 🎨 State-of-the-Art Rendering
- **SVG-to-PDF Conversion:** Ingests raw SVG templates and dynamically injects participant names, event titles, and roles using native XML manipulation.
- **Dynamic QR Codes:** Every certificate receives a uniquely generated, tamper-proof QR code physically stamped onto the PDF canvas (using `ReportLab`). 

### 🔐 Cryptographic Ledger & Verification
- **Immutable Database:** Every generated certificate logs a unique UUID in a persistent PostgreSQL ledger.
- **QR Code Verification Portal:** Scanning the physical QR code on the certificate instantly routes to a public, mobile-friendly Verification Portal confirming the document's authenticity and issuing details.

### ✉️ Asynchronous Email Dispatch
- Integrated with the **Resend API** for rapid, scalable, and high-deliverability email dispatch.
- Beautiful, fully responsive HTML email templates with the PDF attached perfectly intact.
- Features mid-way pipeline termination and background failure logging so a single bad email never breaks a batch.

<br />

## 🛠️ Architecture & Tech Stack

| Layer | Technologies Used | Description |
| :--- | :--- | :--- |
| **Frontend UI** | React, Vite, Tailwind CSS | A sleek, modern SPA featuring responsive claymorphism, micro-animations, and real-time polling. Hosted on **Vercel**. |
| **Backend API** | Python, FastAPI, Uvicorn | High-throughput asynchronous routing with raw CORS injection and 5MB payload guards. Hosted on **Render**. |
| **Database** | PostgreSQL, SQLAlchemy | Relational ledger tracking certificate issuance, batch IDs, and statuses. |
| **Generative Engine**| Pandas, svglib, ReportLab | Handles intelligent data cleaning, SVG manipulation, and multi-layer PDF compositing. |

<br />

## ⚙️ Local Development Setup

To run this project locally, you will need Node.js and Python 3.11+ installed.

### 1. Clone the Repository
```bash
git clone https://github.com/adhy2312/certificate-generator-app.git
cd certificate-generator-app
```

### 2. Backend Setup (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```
Create a `.env` file inside the `backend/` directory:
```env
RESEND_API_KEY=your_resend_api_key
DATABASE_URL=sqlite:///./certificates.db  # Or your PostgreSQL URL
GATEKEEPER_PASSWORD=your_secure_password
```
Run the server:
```bash
uvicorn main:app --reload
```

### 3. Frontend Setup (React/Vite)
```bash
cd ../frontend
npm install
```
Create a `.env` file inside the `frontend/` directory:
```env
VITE_API_URL=http://localhost:8000
```
Run the development server:
```bash
npm run dev
```

<br />

## 🌐 Production Deployment Flow

- **Frontend (Vercel):** The frontend relies on Vercel's Edge Network. Environment variables (`VITE_API_URL`) must be set in the Vercel dashboard prior to deployment to ensure proper routing to the backend.
- **Backend (Render):** The backend runs on a Render Web Service using `gunicorn` with `uvicorn` workers. It is bound to a managed PostgreSQL database. Background tasks (`BackgroundTasks`) are strictly utilized for non-blocking email dispatch and PDF rendering.

<br />

---
<div align="center">
  <p>Engineered with ❤️ for the ISTE Community.</p>
</div>
