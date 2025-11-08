"""
FastAPI Backend for Outreach System (File-Based Persistence)
REST API endpoints for campaign management and monitoring
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from fastapi import UploadFile, File
from pathlib import Path
import json
import os
import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from src.core.logger import log
from src.crew.outreach_lang_crew import LangGraphOutreachCrew
from . import uploads 
from src.crew.outreach_lang_crew import DATA_DIR, CAMPAIGN_BASE_DIR, MEMORY_DIR, UPLOAD_DIR
from src.core.utils import _read_json_file, _get_latest_uploaded_leads_file, _get_campaign_summary, _get_all_campaign_summaries

CAMPAIGN_SUMMARY_FILE = "campaign_summary.json"
GLOBAL_INSIGHTS_FILE = "global_insights_history.json"
LEADS_FILE = "discovered_leads.json"
CONTENT_FILE = "generated_content.json"

# ----------------------------------------------------

app = FastAPI(
    title="Outreach Campaign API",
    description="AI-Powered Outreach Campaign Management System",
    version="1.0.0"
)

# CORS middleware for web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)  

# Store active campaign tasks
active_campaigns: Dict[str, Any] = {}


# =========================
# Pydantic Models
# =========================

class CampaignCreate(BaseModel):
    campaign_id: Optional[str] = None
    product: str
    target_industry: Optional[str] = None
    company_size: Optional[str] = "10-50 employees"
    lead_count: Optional[int] = 10
    target: Optional[str] = None
    # --- FIX APPLIED HERE ---
    # This field is required to pass the uploaded leads file name to the LangGraph crew.
    uploaded_leads_file: Optional[str] = None 
    # ------------------------

class CampaignResponse(BaseModel):
    campaign_id: str
    status: str
    product: str
    created_at: datetime
    leads_discovered: int
    emails_generated: int
    emails_sent: int
    current_step: str

class DashboardStats(BaseModel):
    total_campaigns: int
    active_campaigns: int
    total_leads: int
    total_emails_sent: int
    success_rate: float


# =========================
# Background Task Runner
# =========================

def run_campaign_background(campaign_params: Dict[str, Any]):
    """Run campaign in background, updating file status"""
    campaign_id = campaign_params["campaign_id"]
    try:
        log.info(f"Starting background campaign: {campaign_id}")
        
        # NOTE: We can't update a "db" object inside the background task, 
        # so we rely on the LangGraph crew to manage its state/files and 
        # update the final summary file.
        
        crew = LangGraphOutreachCrew()
        # The campaign_params dictionary now correctly contains 'uploaded_leads_file' if provided in the API call.
        result = crew.run_campaign(campaign_params) 
        
        # After execution, the summary file should exist
        active_campaigns[campaign_id] = {"status": "completed", "result": result}
        
    except Exception as e:
        log.error(f"Background campaign failed: {e}")
        active_campaigns[campaign_id] = {"status": "failed", "error": str(e)}
        
        # Attempt to save the error status to a file (optional, but good practice)
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        error_summary = {
            "campaign_id": campaign_id,
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "errors": [str(e)]
        }
        with open(campaign_dir / CAMPAIGN_SUMMARY_FILE, 'w') as f:
             json.dump(error_summary, f, indent=2)

# =========================
# API Endpoints
# =========================

# Mount static files (if you later add CSS/JS/images)
app.mount("/static", StaticFiles(directory="src/web"), name="static")

# Serve dashboard at root
@app.get("/")
def serve_dashboard():
    index_path = os.path.join("src", "web", "index.html")
    if not os.path.exists(index_path):
        return {"error": "Dashboard file not found."}
    return FileResponse(index_path)

@app.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(campaign: CampaignCreate, background_tasks: BackgroundTasks):
    """Create and start a new campaign"""
    try:
        # Generate campaign ID if not provided
        if not campaign.campaign_id:
            campaign.campaign_id = f"campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        campaign_params = campaign.dict()

        # --- INSERTED: AUTO-POPULATE uploaded_leads_file if not provided ---
        if not campaign_params.get("uploaded_leads_file"):
            latest_file_name = _get_latest_uploaded_leads_file()
            if latest_file_name:
                log.info(f"Automatically using latest uploaded leads file: {latest_file_name}")
                campaign_params["uploaded_leads_file"] = latest_file_name
            else:
                log.warning(
                    "No leads file provided, and no leads found in uploads directory. "
                    "Campaign will attempt discovery or fail."
                )
        # ----------------------------------------------------------------

        # Create campaign directory and initial files/status
        campaign_id = campaign.campaign_id
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)

        # Initial status for immediate response
        initial_status = "running"

        # Create a temporary summary file to indicate running status
        initial_summary = {
            "campaign_id": campaign_id,
            "status": initial_status,
            "product": campaign_params["product"],
            "created_at": datetime.now().isoformat(),
            "leads_discovered": 0,
            "emails_generated": 0,
            "emails_sent": 0,
            "current_step": "initializing",
            "errors": []
        }

        with open(campaign_dir / CAMPAIGN_SUMMARY_FILE, "w") as f:
            json.dump(initial_summary, f, indent=2)

        campaign_params["campaign_id"] = campaign_id  # Ensure ID is in params for background task

        # Start campaign in background
        active_campaigns[campaign_id] = {"status": "running"}
        background_tasks.add_task(run_campaign_background, campaign_params)

        return CampaignResponse(
            campaign_id=campaign_id,
            status=initial_status,
            product=campaign_params["product"],
            created_at=datetime.now(),
            leads_discovered=0,
            emails_generated=0,
            emails_sent=0,
            current_step="initializing"
        )

    except Exception as e:
        log.error(f"Failed to create campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/campaigns", response_model=List[CampaignResponse])
async def list_campaigns():
    """Get all campaigns (from file summaries)"""
    try:
        campaigns = _get_all_campaign_summaries()
        
        # Map file-based dictionary to Pydantic model
        return [
            CampaignResponse(
                campaign_id=c.get("campaign_id", "unknown"),
                status=c.get("status", "unknown"),
                product=c.get("product", "N/A"),
                created_at=datetime.fromisoformat(c["created_at"]) if c.get("created_at") else datetime.min,
                leads_discovered=c.get("leads_discovered", 0),
                emails_generated=c.get("emails_generated", 0),
                emails_sent=c.get("emails_sent", 0),
                # Note: current_step is not in the final summary, but we can infer it or use 'completed'
                current_step=c.get("current_step", "completed" if c.get("status") in ["completed", "completed_with_errors"] else "N/A")
            )
            for c in campaigns
        ]
    except Exception as e:
        log.error(f"Failed to list campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get detailed campaign information from files"""
    try:
        campaign = _get_campaign_summary(campaign_id)
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found or summary file missing")
        
        # Load related data from files
        leads_data = _read_json_file(campaign_dir / LEADS_FILE) or []
        emails_data = _read_json_file(campaign_dir / CONTENT_FILE) or []

        # Load campaign parameters
        params_data = _read_json_file(campaign_dir / "campaign_params.json") or {}

        # The campaign summary is already a dict, but we format it for the response structure
        return {
            "campaign": {
                "campaign_id": campaign.get("campaign_id"),
                "status": campaign.get("status"),
                "product": campaign.get("product"),
                "target_industry": params_data.get("target_industry"),
                "created_at": campaign.get("created_at"),
                "completed_at": campaign.get("timestamp") if campaign.get("status") != "running" else None,
                "current_step": campaign.get("current_step", "completed"),
                "parameters": params_data,
                "errors": campaign.get("errors", [])
            },
            "statistics": {
                "leads_discovered": len(leads_data),
                "emails_generated": len(emails_data),
                "emails_sent": campaign.get("emails_sent", 0)
            },
            "leads": [
                {
                    "company_name": lead.get("company_name"),
                    "domain": lead.get("domain"),
                    "industry": lead.get("industry"),
                    "contact_email": lead.get("contact_email")
                }
                for lead in leads_data[:10]  # Show first 10
            ],
            "emails": [
                {
                    "subject": email.get("subject"),
                    "status": email.get("status"), # This status might need to be tracked more robustly
                    "generated_at": email.get("generated_at")
                }
                for email in emails_data[:10]  # Show first 10
            ]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/campaigns/{campaign_id}/status")
async def get_campaign_status(campaign_id: str):
    """Get real-time campaign status from the summary file"""
    try:
        campaign = _get_campaign_summary(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Note: The LangGraph crew updates the summary file *at the end*. 
        # For a "real-time" update during run, the LangGraph crew would need
        # to periodically update a progress file within the campaign directory.
        # We assume the last recorded summary status is the latest.
        
        return {
            "campaign_id": campaign.get("campaign_id"),
            "status": campaign.get("status"),
            "current_step": campaign.get("current_step", "N/A"),
            "progress": {
                "leads_discovered": campaign.get("leads_discovered", 0),
                "emails_generated": campaign.get("emails_generated", 0),
                "emails_sent": campaign.get("emails_sent", 0)
            },
            "errors": campaign.get("errors", []),
            "updated_at": campaign.get("timestamp") or datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get campaign status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """Get overall dashboard statistics from file summaries"""
    try:
        campaigns = _get_all_campaign_summaries()
        
        total_campaigns = len(campaigns)
        active_campaigns_count = len([c for c in campaigns if c.get("status") == "running"])
        total_leads = sum(c.get("leads_discovered", 0) for c in campaigns)
        total_emails_sent = sum(c.get("emails_sent", 0) for c in campaigns)
        
        # Calculate success rate (campaigns completed without errors)
        completed_campaigns = [c for c in campaigns if c.get("status") == "completed"]
        success_rate = (len(completed_campaigns) / total_campaigns * 100) if total_campaigns > 0 else 0
        
        return DashboardStats(
            total_campaigns=total_campaigns,
            active_campaigns=active_campaigns_count,
            total_leads=total_leads,
            total_emails_sent=total_emails_sent,
            success_rate=round(success_rate, 2)
        )
    
    except Exception as e:
        log.error(f"Failed to get dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/leads")
async def get_all_leads():
    """Get all leads across campaigns by reading all discovered_leads.json files"""
    try:
        all_leads = []
        for campaign_dir in CAMPAIGN_BASE_DIR.iterdir():
            if campaign_dir.is_dir():
                leads = _read_json_file(campaign_dir / LEADS_FILE)
                if leads:
                    all_leads.extend(leads)
                    
        return {"total": len(all_leads), "leads": all_leads[:50]}  # Return first 50
    except Exception as e:
        log.error(f"Failed to get leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/insights")
async def get_all_insights():
    """Get all strategic insights from global_insights_history.json"""
    try:
        insights_path = MEMORY_DIR / GLOBAL_INSIGHTS_FILE
        insights = _read_json_file(insights_path) or []
        
        return {"total": len(insights), "insights": insights[:50]}  # Return first 50
    except Exception as e:
        log.error(f"Failed to get insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/engagement")
async def get_engagement_history():
    """
    Get engagement event history.
    NOTE: The LangGraph crew doesn't explicitly define an engagement log file,
    so this endpoint is effectively a placeholder/stub for a file that would
    need to be created by the crew's outreach operation (e.g., 'engagement_history.json').
    We'll return an empty list for now.
    """
    try:
        # Placeholder logic: assuming engagement is tracked in a global file
        engagement_path = MEMORY_DIR / "engagement_events.json"
        events = _read_json_file(engagement_path) or []
        
        return {"total": len(events), "events": events[:50]}
    except Exception as e:
        log.error(f"Failed to get engagement history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    for d in [DATA_DIR, CAMPAIGN_BASE_DIR, MEMORY_DIR, UPLOAD_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8080)
