# src/api/uploads.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import pandas as pd
import numpy as np
import json
from datetime import datetime
from pathlib import Path

# --- Configuration for File-Based Persistence ---
DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploaded_leads"
UPLOAD_DIR.mkdir(exist_ok=True) # Ensure the upload directory exists

router = APIRouter(prefix="/upload", tags=["Upload"])

class UploadResponse(BaseModel):
    """Response model for lead upload."""
    status: str
    leads_imported: int
    filename: str

@router.post("/leads", response_model=UploadResponse)
async def upload_leads(file: UploadFile = File(...)):
    """
    Upload a CSV or Excel file with lead data.
    The leads are saved to a time-stamped JSON file under the 'data/uploaded_leads' directory.
    """
    try:
        # Load file
        if file.filename.endswith(".csv"):
            # FastAPI's UploadFile provides an IO object, pandas can read directly
            df = pd.read_csv(file.file)
        elif file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file.file)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a CSV, XLSX, or XLS file.")

        # --- Data Cleaning and Standardization ---
        
        # 1. Drop any unwanted unnamed columns (common in exported sheets)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

        # 2. Convert column names to snake_case for consistency
        df.columns = df.columns.str.lower().str.replace(' ', '_', regex=False)
        
        # 3. Replace NaN with None for clean JSON serialization
        # The use of numpy is kept here as it's efficient for NaN replacement
        df = df.replace({np.nan: None})

        # 4. Convert to dict records
        leads = df.to_dict(orient="records")
        count = len(leads)
        
        if count == 0:
            raise HTTPException(status_code=400, detail="The file contains no data rows.")

        # --- File-Based Persistence ---
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_stem = Path(file.filename).stem
        new_filename = f"uploaded_{original_stem}_{timestamp}.json"
        save_path = UPLOAD_DIR / new_filename
        
        # Save the list of dictionaries to the file system
        with open(save_path, 'w') as f:
            json.dump({"timestamp": timestamp, "leads": leads}, f, indent=4)

        # The system now expects the crew or a campaign-specific trigger to pick up these uploaded leads.
        
        return {
            "status": "success", 
            "leads_imported": count, 
            "filename": new_filename
        }

    except HTTPException as h:
        raise h # Re-raise known HTTP exceptions

    except Exception as e:
        # Catch and handle other exceptions like ReadError from pandas
        print(f"Upload processing error: {e}") # Log the specific error
        raise HTTPException(status_code=500, detail=f"Upload failed due to data processing error: {type(e).__name__}")