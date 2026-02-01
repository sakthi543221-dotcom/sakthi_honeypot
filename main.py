import os
import json
import re
from typing import Dict
from fastapi import FastAPI, Header, HTTPException, Request
from dotenv import load_dotenv
import google.generativeai as genai

# ================= LOAD ENV =================
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
API_KEY = os.getenv("API_KEY")

# Do NOT crash app on startup (hackathon-safe)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ================= APP =================
app = FastAPI(
    title="Agentic Scam Honeypot API",
    version="FINAL",
    description="Hackathon-safe agentic honeypot (simulated environment)"
)

# ================= MEMORY =================
conversation_store: Dict = {}

# ================= PERSONAS =================
PERSONAS = {
    "Bank Fraud": [
        "Why is my account blocked? I use it daily.",
        "Which UPI ID should I send the money to?",
        "The app is asking for details again. Can you help?"
    ],
    "UPI Fraud": [
        "I am confused about UPI. Can you explain?",
        "Please send the correct UPI ID.",
        "It says transaction failed. What should I do?"
    ],
    "Job Scam": [
        "Is there really no interview?",
        "How much is the registration fee?",
        "Can I pay through UPI?"
    ],
    "Lottery Scam": [
        "I don't remember entering any lottery!",
        "What is the processing fee?",
        "How will I receive the prize?"
    ],
    "KYC Scam": [
        "My KYC is pending? I was not informed.",
        "Is this official bank message?",
        "Which details should I update?"
    ],
    "Phishing": [
        "The link is not opening properly.",
        "Is this the official website?",
        "Should I login using my app instead?"
    ]
}

# ================= SYSTEM PROMPT =================
SYSTEM_PROMPT = """
You are an AI Scam Detection and Honeypot Agent.

RULES:
- Respond ONLY with valid JSON
- NO markdown, NO explanation text
- NEVER agree to send money
- Assume simulated environment only

Return EXACT JSON:

{
  "is_scam": true or false,
  "scam_type": "UPI Fraud | Bank Fraud | Job Scam | Lottery Scam | KYC Scam | Phishing | Not Scam",
  "confidence": number between 0 and 1,
  "honeypot_response": string or null,
  "extracted_entities": {
    "upi_id": string or null,
    "bank_account": string or null,
    "ifsc": string or null,
    "phone_number": string or null,
    "phishing_link": string or null
  }
}
"""

# ================= HELPERS =================
def safe_json(text: str):
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return None

def regex_extract(message: str):
    return {
        "upi_id": re.findall(r'\b[\w\.-]+@[\w-]+\b', message),
        "phone_number": re.findall(r'(?:\+91)?[6-9]\d{9}', message),
        "phishing_link": re.findall(r'https?://\S+', message),
        "bank_account": re.findall(r'\b\d{10,18}\b', message),
        "ifsc": re.findall(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', message.upper())
    }

def get_honeypot(scam_type: str, stage: int):
    responses = PERSONAS.get(scam_type, [])
    if not responses:
        return "Can you explain this again?"
    return responses[stage % len(responses)]

# ================= ENDPOINT =================
@app.post("/analyze")
async def analyze(request: Request, x_api_key: str = Header(None)):
    try:
        # ---- API KEY (HEADER + QUERY FALLBACK) ----
        if not x_api_key:
            x_api_key = request.query_params.get("api_key")

        if x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        # ---- READ BODY (JSON OR TEXT) ----
        raw_body = await request.body()
        text = raw_body.decode("utf-8").strip()

        try:
            data = json.loads(text) if text else {}
            message = data.get("message", text)
            session_id = data.get("conversation_id", "default")
        except:
            message = text
            session_id = "default"

        if not message:
            raise HTTPException(status_code=400, detail="Message required")

        # ---- SESSION MEMORY ----
        if session_id not in conversation_store:
            conversation_store[session_id] = {"stage": 0}

        session = conversation_store[session_id]

        # ---- GEMINI CALL ----
        ai_json = None
        if GEMINI_API_KEY:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                SYSTEM_PROMPT + "\nMessage:\n" + message
            )
            ai_text = response.text if response else ""
            ai_json = safe_json(ai_text)

        # ---- FALLBACK (NO AI / BAD JSON) ----
        if not ai_json:
            extracted = regex_extract(message)
            is_scam = bool(extracted["upi_id"] or extracted["phishing_link"])
            scam_type = "Phishing" if extracted["phishing_link"] else "Bank Fraud"

            honeypot = get_honeypot(scam_type, session["stage"]) if is_scam else None
            if is_scam:
                session["stage"] += 1

            return {
                "is_scam": is_scam,
                "scam_type": scam_type if is_scam else "Not Scam",
                "confidence": 0.7 if is_scam else 0.2,
                "honeypot_response": honeypot,
                "extracted_entities": extracted,
                "ethical_note": "Simulated environment only"
            }

        # ---- HONEYPOT RESPONSE ----
        if ai_json.get("is_scam"):
            ai_json["honeypot_response"] = get_honeypot(
                ai_json.get("scam_type", "Bank Fraud"),
                session["stage"]
            )
            session["stage"] += 1

        ai_json["ethical_note"] = "Simulated environment only"
        return ai_json

    except Exception as e:
        return {
            "is_scam": True,
            "scam_type": "System Safe Mode",
            "confidence": 0.4,
            "honeypot_response": "Please repeat the message.",
            "extracted_entities": {},
            "ethical_note": f"Error handled safely: {str(e)}"
        }

# ================= HEALTH =================
@app.get("/")
def health():
    return {
        "status": "running",
        "message": "Agentic Honeypot API ready for hackathon evaluation"
    }
