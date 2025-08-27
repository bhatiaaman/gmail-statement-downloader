# 📥 Gmail Statement Downloader


[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Gmail API](https://img.shields.io/badge/Gmail%20API-enabled-green.svg)](https://developers.google.com/gmail/api)


Automate the retrieval and decryption of credit card statements from Gmail using the Gmail API and Python. Supports password-protected PDFs, retry logic, logging, and optional password reuse across files.

---

## 🚀 Features

- 🔐 Decrypts password-protected PDF statements
- 🔁 Retry logic for incorrect passwords
- 📝 Logs all downloads and failures
- 🏷️ Auto-tags failed files with `_FAILED.pdf`
- 🧠 Optional password reuse for batch processing
- 📦 Modular design for future dashboard integration

---

## 🧰 Requirements

- Python 3.8+
- Gmail account with statement emails
- Google Cloud Console project with Gmail API enabled
- OAuth credentials (`credentials.json`)

Install dependencies:

```bash
pip install --upgrade google-auth-oauthlib google-api-python-client pikepdf