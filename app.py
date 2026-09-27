from datetime import datetime
import json
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image

st.set_page_config(page_title="Medical Bill Claim Extractor", layout="centered")
st.title("Personal Medical Bill Claim Extractor")

# Define strict JSON schema
class BillExtraction(BaseModel):
    provider_name: str = Field(description="Name of the hospital, clinic, pharmacy, or diagnostic lab")
    bill_date: str = Field(description="Date of the bill in YYYY-MM-DD format")
    invoice_number: str = Field(description="Invoice or receipt number")
    total_amount: float = Field(description="Total final amount paid")
    claimable_amount: float = Field(description="Total reimbursable amount excluding non-claimable fees like admin or registration")

# Document ingestion options
ingestion_mode = st.radio("Select Ingestion Method:", ["Mobile Camera", "File Upload (Desktop/PDF/Image)"])

uploaded_file = None
if ingestion_mode == "Mobile Camera":
    uploaded_file = st.camera_input("Capture Bill Photo")
else:
    uploaded_file = st.file_uploader("Upload Bill (PNG, JPG, JPEG, PDF)", type=["png", "jpg", "jpeg", "pdf"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="Selected Bill Preview", use_container_width=True) if uploaded_file.type != "application/pdf" else st.info("PDF document ready for processing.")
    
    if st.button("Process & Log Claim", type="primary"):
        with st.spinner("Extracting data and logging claim..."):
            try:
                # 1. Initialize Gemini Client
                gemini_api_key = st.secrets["GEMINI_API_KEY"]
                client = genai.Client(api_key=gemini_api_key)

                file_bytes = uploaded_file.getvalue()
                mime_type = uploaded_file.type

                # 2. Extract structured data
                prompt = (
                    "Extract the details from this medical bill into the structured JSON schema. "
                    "Normalize the bill date strictly to YYYY-MM-DD. "
                    "For claimable_amount, subtract non-reimbursable elements such as registration charges or admin fees."
                )
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BillExtraction,
                    ),
                )
                
                extracted = BillExtraction.model_validate_json(response.text)

                # 3. Connect to Google Sheets via Service Account
                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
                gc = gspread.authorize(creds)
                sheet = gc.open("Medical_Claims_DB").sheet1

                # 4. Append row to Google Sheets
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_row = [
                    now_str,
                    extracted.provider_name,
                    extracted.bill_date,
                    extracted.invoice_number,
                    extracted.total_amount,
                    extracted.claimable_amount,
                    "Uploaded via App"
                ]
                sheet.append_row(new_row)

                st.success("Claim successfully logged!")
                st.json(extracted.model_dump())

            except Exception as e:
                st.error(f"Error processing claim: {str(e)}")
