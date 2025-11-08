"""
LangGraph-based Outreach System
Converts the CrewAI multi-agent system to explicit graph-based workflow
"""

from typing import TypedDict, List, Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from pathlib import Path
import json
from datetime import datetime
from src.core.logger import log
from src.crew.opearations import *

# --- Configuration for File-Based Persistence (MANDATORY PATHS) ---
UPLOAD_DIR = Path("data") / "uploaded_leads"
CAMPAIGN_BASE_DIR = Path("data") / "campaigns"
MEMORY_DIR = Path("data") / "memory"
DATA_DIR = Path("data")
# =========================
# State Definition
# =========================

class OutreachState(TypedDict):
    """State that flows through the graph"""
    campaign_id: str
    campaign_params: Dict[str, Any]
    
    # Step outputs
    discovered_leads: List[Dict]
    analysis_data: Dict
    feedback_insights: Dict
    generated_content: List[Dict]
    outreach_report: Dict
    
    # Metadata
    previous_campaigns: List[str]
    errors: List[str]
    current_step: str

# =========================
# Graph Nodes
# =========================

def discovery_node(state: OutreachState) -> OutreachState:
    """
    Node 1: Checks if leads were pre-loaded (uploaded). 
    The logic for automatic generation is removed.
    """
    
    lead_count = len(state.get("discovered_leads", []))
    
    if state["campaign_params"].get("skip_lead_generation") and lead_count > 0:
        log.info(f"=== STEP 1: Leads Pre-Loaded (Count: {lead_count}) ===")
        state["current_step"] = "discovery_skipped"
        # Leads were already saved to campaign_dir in run_campaign
    elif lead_count > 0:
        log.warning(f"=== STEP 1: Leads found in state (Count: {lead_count}), but no skip flag. Proceeding. ===")
        state["current_step"] = "leads_in_state"
    else:
        log.warning("=== STEP 1: Lead Discovery Skipped. No leads found in initial state. ===")
        state["current_step"] = "discovery_failed_no_leads"
        # The router will catch this and send it to END
    
    return state


def analyzer_node(state: OutreachState) -> OutreachState:
    log.info("=== STEP 2: Campaign Analysis ===")
    try:
        previous_campaigns = state.get("previous_campaigns", [])
        
        if not previous_campaigns:
            state["analysis_data"] = {"note": "No previous campaigns"}
            state["current_step"] = "analysis_complete"
            return state
        
        # Initialize LLM
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)
        
        # Direct function call
        analysis = analyze_campaigns(previous_campaigns, llm)
        
        state["analysis_data"] = analysis
        state["current_step"] = "analysis_complete"
        
        # Save to file (in campaign directory)
        campaign_id = state["campaign_id"]
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        
        with open(campaign_dir / "analysis_report.json", 'w') as f:
            json.dump(analysis, f, indent=2)
        
    except Exception as e:
        log.error(f"Analysis error: {e}")
        state["errors"].append(f"Analysis: {str(e)}")
        state["analysis_data"] = {}
    
    return state


def feedback_node(state: OutreachState) -> OutreachState:
    log.info("=== STEP 3: Strategic Insights ===")
    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.7)
        
        analysis_data = state.get("analysis_data", {})
        
        # Direct function call
        insights = generate_strategic_insights(analysis_data, llm)
        
        state["feedback_insights"] = insights
        state["current_step"] = "feedback_complete"
        
        # Save to file (in campaign directory)
        campaign_id = state["campaign_id"]
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        
        with open(campaign_dir / "feedback_insights.json", 'w') as f:
            json.dump(insights, f, indent=2)
        
        # Also save to global history (in MEMORY_DIR)
        insights_file = MEMORY_DIR / "global_insights_history.json"
        
        history = []
        if insights_file.exists():
            with open(insights_file, 'r') as f:
                history = json.load(f)
        
        history.append({
            "campaign_id": campaign_id,
            "generated_at": datetime.now().isoformat(),
            "insights": insights
        })
        
        # Ensure MEMORY_DIR exists before writing
        MEMORY_DIR.mkdir(exist_ok=True)
        with open(insights_file, 'w') as f:
            json.dump(history, f, indent=2)
        
    except Exception as e:
        log.error(f"Feedback error: {e}")
        state["errors"].append(f"Feedback: {str(e)}")
        state["feedback_insights"] = {}
    
    return state


def content_node(state: OutreachState) -> OutreachState:
    log.info("=== STEP 4: Content Generation ===")
    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.7)
        
        leads = state.get("discovered_leads", [])
        product = state["campaign_params"].get("product", "our solution")
        insights = state.get("feedback_insights", {})
        
        if not leads:
            log.warning("No leads found for content generation. Skipping.")
            state["current_step"] = "content_skipped"
            return state

        # Direct function call
        content = generate_email_content(leads, product, insights, llm)
        
        state["generated_content"] = content
        state["current_step"] = "content_complete"
        
        # Save to file (in campaign directory)
        campaign_id = state["campaign_id"]
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        
        with open(campaign_dir / "generated_content.json", 'w') as f:
            json.dump(content, f, indent=2)
        
    except Exception as e:
        log.error(f"Content generation error: {e}")
        state["errors"].append(f"Content: {str(e)}")
        state["generated_content"] = []
    
    return state


def outreach_node(state: OutreachState) -> OutreachState:
    log.info("=== STEP 5: Outreach Execution ===")
    try:
        emails = state.get("generated_content", [])
        campaign_id = state["campaign_id"]
        
        # Direct function call
        report = execute_outreach(emails, campaign_id)
        
        state["outreach_report"] = report
        state["current_step"] = "outreach_complete"
        
        # Save to file (in campaign directory)
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        
        with open(campaign_dir / "outreach_report.json", 'w') as f:
            json.dump(report, f, indent=2)
        
    except Exception as e:
        log.error(f"Outreach error: {e}")
        state["errors"].append(f"Outreach: {str(e)}")
        state["outreach_report"] = {}
    
    return state

# =========================
# Graph Router
# =========================

def route_after_discovery(state: OutreachState) -> Literal["analyzer", END]:
    """
    Router: Ensures we only proceed if leads are present in the state.
    """
    if not state["discovered_leads"]:
        log.warning("No leads available. Campaign ending early.")
        return END 
        
    # Standard flow continues if leads exist
    return "analyzer"

# =========================
# Build Graph (Remains the same)
# =========================

def create_outreach_graph():
    """Create the LangGraph workflow"""
    
    workflow = StateGraph(OutreachState)
    
    # Add nodes
    workflow.add_node("discovery", discovery_node)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("feedback", feedback_node)
    workflow.add_node("content", content_node)
    workflow.add_node("outreach", outreach_node)
    
    # Define edges (explicit flow)
    workflow.set_entry_point("discovery")
    
    # Use the router after discovery (can be END if no leads were found)
    workflow.add_conditional_edges(
        "discovery",
        route_after_discovery,
        {
            "analyzer": "analyzer",
            END: END,
        },
    )
    
    # Define sequential edges for the rest of the flow
    workflow.add_edge("analyzer", "feedback")
    workflow.add_edge("feedback", "content")
    
    # Use a check here to ensure we don't proceed to outreach if content failed
    def should_continue(state: OutreachState):
        return "outreach" if state["generated_content"] else END

    workflow.add_conditional_edges(
        "content",
        should_continue,
        {
            "outreach": "outreach",
            END: END,
        }
    )
    
    workflow.add_edge("outreach", END)
    
    return workflow.compile()


# =========================
# Main Execution Class (Updated to use new paths)
# =========================

class LangGraphOutreachCrew:
    """LangGraph-based outreach orchestrator"""
    
    def __init__(self):
        self.graph = create_outreach_graph()
        # Ensure all data directories are ready
        Path("data").mkdir(exist_ok=True)
        UPLOAD_DIR.mkdir(exist_ok=True)
        CAMPAIGN_BASE_DIR.mkdir(exist_ok=True)
        MEMORY_DIR.mkdir(exist_ok=True)
        log.info("LangGraph outreach system initialized")
    
    def _get_previous_campaigns(self) -> List[str]:
        """Get list of previous campaign IDs from the dedicated campaign directory"""
        # Only checks inside the CAMPAIGN_BASE_DIR
        return [d.name for d in CAMPAIGN_BASE_DIR.iterdir() if d.is_dir()]
    
    def run_campaign(self, campaign_params: Dict) -> Dict:
        """Execute campaign using LangGraph"""
        
        campaign_id = campaign_params.get('campaign_id', f"campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        uploaded_file = campaign_params.get('uploaded_leads_file')
        
        log.info(f"🚀 Starting campaign: {campaign_id}")
        
        initial_leads: List[Dict] = []
        skip_lead_generation: bool = False
        
        campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
        lead_count = int(campaign_params.get("lead_count", 10))

        # --- Handle Uploaded Leads ---
        if uploaded_file:
            upload_path = UPLOAD_DIR / uploaded_file
            if upload_path.exists():
                try:
                    with open(upload_path, 'r') as f:
                        uploaded_data = json.load(f)
                        initial_leads = uploaded_data.get("leads", [])
                        
                    if initial_leads:
                        if len(initial_leads) > lead_count:
                            log.info(f"Truncating leads to {lead_count} based on campaign settings")
                            initial_leads = initial_leads[:lead_count]

                        # Save truncated leads
                        with open(campaign_dir / "discovered_leads.json", 'w') as f:
                            json.dump(initial_leads, f, indent=2)
                            
                    else:
                        log.warning(f"Uploaded file {uploaded_file} was empty or invalid. Campaign will end after discovery check.")
                        
                except Exception as e:
                    log.error(f"Failed to process uploaded leads file {uploaded_file}: {e}. Campaign will end after discovery check.")
                    campaign_params["errors"] = campaign_params.get("errors", []) + [f"Upload error: {e}"]
            else:
                log.warning(f"Uploaded file {uploaded_file} not found. Campaign will end after discovery check.")
        else:
            # Explicitly mark for no lead generation/no leads if no file was specified
            log.warning("No 'uploaded_leads_file' provided. Campaign requires pre-loaded leads to proceed.")


        # Initialize state
        initial_state: OutreachState = {
            "campaign_id": campaign_id,
            "campaign_params": campaign_params,
            # Set discovered_leads based on upload, otherwise it's empty
            "discovered_leads": initial_leads, 
            "analysis_data": {},
            "feedback_insights": {},
            "generated_content": [],
            "outreach_report": {},
            "previous_campaigns": self._get_previous_campaigns(),
            "errors": campaign_params.get("errors", []), # Carry over any initial errors
            "current_step": "initializing"
        }
        
        # Mark the lead generation for skipping if leads were loaded
        if skip_lead_generation:
            campaign_params["skip_lead_generation"] = True 

        # Save campaign params (including the new skip flag) using the campaign_dir
        campaign_dir.mkdir(exist_ok=True)
        
        with open(campaign_dir / "campaign_params.json", 'w') as f:
            json.dump(campaign_params, f, indent=2)
        
        # Execute graph
        final_state = self.graph.invoke(initial_state)
        
        # Create summary
        summary = {
            "campaign_id": campaign_id,
            "status": "completed" if not final_state["errors"] and final_state.get("discovered_leads") else "completed_with_errors",
            "timestamp": datetime.now().isoformat(),
            "steps_completed": [
                "upload",
                "analysis",
                "feedback",
                "content_generation",
                "outreach"
            ],
            "leads_discovered": len(final_state["discovered_leads"]),
            "emails_generated": len(final_state["generated_content"]),
            "emails_sent": final_state["outreach_report"].get("execution_summary", {}).get("sent", 0),
            "errors": final_state["errors"]
        }
        
        with open(campaign_dir / "campaign_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        log.info(f"✅ Campaign {campaign_id} completed")
        
        return summary


# =========================
# Usage Example (Updated for new logic)
# =========================

if __name__ == "__main__":
    crew = LangGraphOutreachCrew()
    
    # Example 1: **NO** Automatic Discovery - Will end immediately
    result_fail = crew.run_campaign({
        "product": "Product A",
        "target_industry": "Tech",
        "campaign_id": "test_campaign_fail_no_leads"
    })
    print(f"--- No Leads Result (Expected END) ---")
    print(json.dumps(result_fail, indent=2))
    
    # Example 2: Uploaded Leads (assuming a file named 'my_leads.json' exists in data/uploaded_leads)
    # NOTE: This REQUIRES a leads JSON file to be present in data/uploaded_leads
    result_upload = crew.run_campaign({
        "product": "Cybersecurity Service",
        "target_industry": "Finance",
        "campaign_id": "test_campaign_upload_only",
        "uploaded_leads_file": "example_leads_file.json" # <-- Must exist for success
    })
    print(f"--- Uploaded Leads Result ---")
    print(json.dumps(result_upload, indent=2))