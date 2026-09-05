# 🚀 ISTE CertHub — Complete Backend Deployment & Setup Guide

This guide contains everything needed to deploy an identical, clean new backend for **ISTE CertHub** on **Render (Free Tier)** using **SQLite** and **Google Apps Script Mailer**, and connect it seamlessly with your frontend.

---

## 📌 Summary of Architecture
* **Backend Framework:** FastAPI / Python (Uvicorn + Gunicorn)
* **Database:** SQLite (`certops.db` - zero config, fast)
* **Email Service:** Google Apps Script (GAS) Proxy or Gmail SMTP
* **Frontend:** React + Vite (Hosted on Vercel)
* **Backend Hosting:** Render Web Service (Free Tier)

---

## 🛠️ Phase 1: Deploy New Backend to Render

### Step 1: Push Code to GitHub
Ensure all your local changes are committed and pushed:
```bash
git add .
git commit -m "Update backend configuration and requirements"
git push origin main
```

---

### Step 2: Create a New Web Service on Render
1. Go to [Render Dashboard](https://dashboard.render.com/).
2. Click **"New +"** in the top right corner and select **"Web Service"**.
3. Connect your repository: `adhy2312/certificate-generator-app`.
4. Configure the service settings:
   * **Name:** `iste-cert-hub-backend-v2` *(or any name you prefer)*
   * **Region:** Choose closest (e.g., Singapore / Oregon / Frankfurt)
   * **Branch:** `main`
   * **Root Directory:** *(leave blank)*
   * **Runtime:** `Python 3`
   * **Build Command:** 
     ```bash
     cd backend && pip install -r requirements.txt
     ```
   * **Start Command:**
     ```bash
     cd backend && gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:$PORT --timeout 120
     ```
   * **Instance Type:** `Free`

---

### Step 3: Add Environment Variables in Render
In the **Environment Variables** section on Render, add the following keys:

| Key | Example Value | Description |
| :--- | :--- | :--- |
| `GATEKEEPER_PASSWORD` | `YourSecretPassword123` | Password to access the admin portal / cancel batches |
| `GAS_MAILER_URL` | `https://script.google.com/macros/s/.../exec` | Your Google Apps Script Web App URL |
| `DATABASE_URL` | `sqlite:///./certops.db` | Default SQLite database path |

*(Note: If you ever want to use Gmail SMTP instead of GAS, set `SENDER_EMAIL` and `SENDER_PASS` [16-character App Password] instead of `GAS_MAILER_URL`)*.

---

### Step 4: Deploy & Verify
1. Click **"Create Web Service"**.
2. Wait 2–3 minutes for the build and deployment to finish.
3. Once live, open `https://<YOUR_RENDER_URL>/health` in your browser.
4. You should see:
   ```json
   {
     "status": "ok",
     "service": "ISTE CertHub API"
   }
   ```

---

## 🌐 Phase 2: Connect Frontend (Vercel) to New Backend

1. Go to [Vercel Dashboard](https://vercel.com/dashboard).
2. Click your frontend project (`certificate-generator-app-iste`).
3. Go to **Settings** → **Environment Variables**.
4. Edit or add the variable:
   * **Key:** `VITE_API_URL`
   * **Value:** `https://<YOUR_NEW_RENDER_URL>` *(e.g., `https://iste-cert-hub-backend-v2.onrender.com` without trailing slash)*
5. Go to the **Deployments** tab, click the three dots `...` on the latest deployment, and select **"Redeploy"**.

---

## ✉️ Phase 3: (Optional) Google Apps Script Mailer Setup

If you need to deploy or recreate your Google Apps Script Proxy:

1. Open [Google Apps Script](https://script.google.com/) and click **"New Project"**.
2. Replace the code in `Code.gs` with:
   ```javascript
   function doPost(e) {
     try {
       var data = JSON.parse(e.postData.contents);
       var to = data.to;
       var subject = data.subject;
       var htmlBody = data.html;
       var pdfBase64 = data.attachment_base64;
       var filename = data.filename || "certificate.pdf";
       
       var decodedBlob = Utilities.newBlob(Utilities.base64Decode(pdfBase64), 'application/pdf', filename);
       
       GmailApp.sendEmail(to, subject, "Please view in an HTML-compatible client.", {
         htmlBody: htmlBody,
         attachments: [decodedBlob],
         name: "ISTE MBCET"
       });
       
       return ContentService.createTextOutput(JSON.stringify({
         "success": true,
         "message": "Email sent successfully"
       })).setMimeType(ContentService.MimeType.JSON);
       
     } catch (error) {
       return ContentService.createTextOutput(JSON.stringify({
         "success": false,
         "error": error.toString()
       })).setMimeType(ContentService.MimeType.JSON);
     }
   }
   ```
3. Click **Deploy** → **New deployment**.
4. Click the gear icon next to "Select type" and choose **Web app**.
5. Set:
   * **Execute as:** `Me (<your_email>)`
   * **Who has access:** `Anyone` *(Crucial: must be Anyone so Render can call it)*
6. Click **Deploy**, authorize permissions, and copy the **Web app URL** (ends in `/exec`).
7. Paste this URL as `GAS_MAILER_URL` on Render.

---

## 💻 Phase 4: Running Locally

If you want to run everything locally on your machine:

1. **Configure Backend:**
   * Copy `backend/.env.example` to `backend/.env`
   * Set your `GATEKEEPER_PASSWORD` and `GAS_MAILER_URL` (or Gmail App Password).
2. **Configure Frontend:**
   * Copy `frontend/.env.example` to `frontend/.env` (points to `http://localhost:8000`).
3. **One-Click Startup:**
   * Double-click `Start_Local.bat` in the repository root.
   * Both frontend (`http://localhost:3001`) and backend (`http://localhost:8000`) will boot up automatically!

---

## ✅ Verification Checklist

- [ ] Backend health check responds `200 OK` at `/health`.
- [ ] Login screen accepts the `GATEKEEPER_PASSWORD` set on Render.
- [ ] Single certificate generation with "Download PDF Only" downloads valid PDF.
- [ ] Single certificate generation with "Generate & Email" delivers PDF to inbox.
- [ ] Bulk pipeline spreadsheet parsing and batch processing works without errors.
