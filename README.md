# ♟️ CheckMate: A Personal Plagiarism Pre-Checker

**CheckMate** is a small, locally-hosted utility app built as a student project. It acts as a "pre-checker" for students and writers to run their drafts against a personal, curated database of sources before making a final submission to official tools like Turnitin.

### 💡 Why I Built This
When writing a paper, students often download dozens of PDFs (from ArXiv or textbooks). It's easy to accidentally patch-write or forget to paraphrase properly. 

However, you can't submit an unfinished draft to Turnitin just to check it. CheckMate solves this: it lets you build a **mini, private database** of your specific reference materials, and scans your draft against *only those files*. Best of all, because it runs locally on your computer, your unpublished draft stays completely private.

---

## ✨ Features

* 🔒 **100% Private & Local Database:** Your draft never leaves your computer. All document processing and vector storage (`ChromaDB`) happens on your own hardware, isolated securely per user.
* 🔐 **Secure Authentication & Rate Limiting:** JWT-based authentication with Bcrypt password hashing (72-byte limit handled) and API rate limiting to prevent brute force attacks.
* 📚 **Personal Knowledge Base:** You control the database. Upload local PDFs or search and import papers directly from the ArXiv API.
* 🧠 **Smart Matching:** Uses an AI vector model (`sentence-transformers`) to find similar paragraphs, then uses mathematical N-Gram overlap to highlight the exact copied words.
* ✂️ **Cleans Academic Text:** Automatically ignores citations (like `[1]`) and math formulas so you don't get penalized for standard academic formatting.
* 🎨 **Minimalist UI:** A gorgeous, responsive, minimalist frontend built with React, Tailwind CSS, and custom fluid animations. Dark mode persists locally and syncs flawlessly.

---

## 🛠️ Tech Stack

* **Frontend:** React.js (Vite) + Tailwind CSS + Lucide Icons
* **Backend:** FastAPI (Python) + SQLite
* **Security:** `slowapi` (Rate Limiting), `bcrypt` (Hashing), `PyJWT` (Auth)
* **AI & Search:** `ChromaDB` (Vector Database) + `sentence-transformers` (MiniLM)
* **File Processing:** `pdfplumber` (with custom logic to crop out PDF headers/footers)

---

## 🚀 How to Run It Locally

Since this app runs AI models directly on your machine, it requires about 1GB of RAM and Python installed on your computer.
### 1. Configure Environment Variables

1. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your details:
   ```env
   JWT_SECRET_KEY=your_secure_random_string
   APP_ENV=development
   # Production only: use HTTPS URLs and set COOKIE_SECURE=true
   # FRONTEND_URLS=https://your-production-domain.com
   # FRONTEND_URL=https://your-production-domain.com
   # BACKEND_URL=https://api.your-production-domain.com
   # COOKIE_SECURE=true
   ```
* **JWT_SECRET_KEY**: This signs login sessions. Generate it with `python -c "import secrets; print(secrets.token_hex(32))"`. It is mandatory when `APP_ENV=production`.
* **Production**: Set `APP_ENV=production`, use HTTPS for every URL, and set `COOKIE_SECURE=true`. The application refuses insecure production settings.
* **Privacy**: Never commit `.env`, `users.sqlite`, `my_plagiarism_db`, `dataset_pdfs`, or `temp_uploads`. These may contain account records, source text, or drafts.

### 2. Start the Backend
Clone the repository and install the Python libraries:
```bash
git clone https://github.com/yourusername/checkmate.git
cd checkmate
pip install -r requirements.txt
```

Run the FastAPI server:
```bash
python api.py
```

### 3. Start the Frontend
Open a new terminal window, go to the `ui` folder, and start the React app:
```bash
cd ui
npm install
npm run dev
```

### 4. Open CheckMate
Open `http://localhost:5173` in your browser. Register a new account, log in, and start analyzing your drafts!
