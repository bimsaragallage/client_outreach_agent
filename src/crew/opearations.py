from typing import List, Dict
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from pathlib import Path
import json
from datetime import datetime
from src.core.logger import log

# --- Configuration for File-Based Persistence (MANDATORY PATHS) ---
CAMPAIGN_BASE_DIR = Path("data") / "campaigns"
MEMORY_DIR = Path("data") / "memory"
# NOTE: UPLOAD_DIR is defined in outreach_lang_crew.py, but not needed here

# =========================
# Tools (Direct Functions)
# =========================

def search_companies(max_results: int = 10) -> List[Dict]:
    """
    Direct function call - no hoping agent will use it.
    FIXED: Now loads historical leads only from the CAMPAIGN_BASE_DIR 
    and saves global lead history to MEMORY_DIR.
    """
    from src.data_pipeline.scraper import LeadScraper
    
    log.info(f"🔍 Searching for {max_results} unique leads...")
    
    # Load historical companies from campaign folders only
    historical_companies = set()
    
    if CAMPAIGN_BASE_DIR.exists():
        # Iterate only over the specific campaign folders
        for campaign_dir in CAMPAIGN_BASE_DIR.iterdir():
            leads_file = campaign_dir / "discovered_leads.json"
            if leads_file.exists():
                try:
                    with open(leads_file, 'r') as f:
                        leads = json.load(f)
                    for lead in leads:
                        if isinstance(lead, dict) and 'company' in lead:
                            historical_companies.add(lead['company'].lower().strip())
                except Exception as e:
                    log.warning(f"Could not load leads from {leads_file}: {e}")
    
    log.info(f"Loaded {len(historical_companies)} historical companies")
    
    # Search for new leads
    scraper = LeadScraper()
    all_leads = scraper.search_companies(max_results=max_results * 2)  # Get more for filtering
    
    # Filter duplicates
    unique = []
    seen = set()
    
    for lead in all_leads:
        if "company" not in lead:
            continue
        
        name = lead["company"].lower().strip()
        if name in historical_companies or name in seen:
            continue
        
        unique.append(lead)
        seen.add(name)
        
        if len(unique) >= max_results:
            break
    
    log.info(f"✅ Found {len(unique)} unique leads")
    
    # Save to global history (now in MEMORY_DIR)
    if unique:
        # Saving to data/memory/all_leads_history.json
        hist_file = MEMORY_DIR / "all_leads_history.json"
        
        existing = []
        if hist_file.exists():
            try:
                with open(hist_file, 'r') as f:
                    existing = json.load(f)
            except:
                pass
        
        for lead in unique:
            lead["discovered_at"] = datetime.now().isoformat()
        
        existing.extend(unique)
        
        # Ensure MEMORY_DIR exists before writing
        MEMORY_DIR.mkdir(exist_ok=True)
        with open(hist_file, 'w') as f:
            json.dump(existing, f, indent=2)
    
    return unique


def analyze_campaigns(campaign_ids: List[str], llm: ChatGroq) -> Dict:
    """Analyze past campaign performance and include reply metadata."""
    from src.services.tracker import EngagementTracker

    if not campaign_ids:
        return {
            "campaigns_analyzed": 0,
            "insights": "No historical data available",
            "aggregate_metrics": {},
            "individual_campaigns": []
        }

    log.info(f"📊 Analyzing {len(campaign_ids)} previous campaigns...")

    tracker = EngagementTracker()
    all_metrics = []

    for campaign_id in campaign_ids[-5:]:  # analyze most recent 5 campaigns
        stats = tracker.get_campaign_stats(campaign_id)
        reply_metadata = tracker.get_reply_metadata(campaign_id)

        all_metrics.append({
            "campaign_id": campaign_id,
            "open_rate": stats.get("open_rate", 0),
            "click_rate": stats.get("click_rate", 0),
            "reply_rate": stats.get("reply_rate", 0),
            "total_sent": stats.get("total_sends", 0),
            "avg_reply_positivity": stats.get("avg_reply_positivity"),
            "reply_metadata": reply_metadata
        })

    # Aggregate metrics
    total_sent = sum(m["total_sent"] for m in all_metrics)
    if total_sent > 0:
        avg_open = sum(m["open_rate"] * m["total_sent"] for m in all_metrics) / total_sent
        avg_click = sum(m["click_rate"] * m["total_sent"] for m in all_metrics) / total_sent
        avg_reply = sum(m["reply_rate"] * m["total_sent"] for m in all_metrics) / total_sent
    else:
        avg_open = avg_click = avg_reply = 0

    result = {
        "campaigns_analyzed": len(all_metrics),
        "aggregate_metrics": {
            "avg_open_rate": avg_open,
            "avg_click_rate": avg_click,
            "avg_reply_rate": avg_reply,
            "total_sent": total_sent
        },
        "individual_campaigns": all_metrics,
        "insights": f"Analyzed {len(all_metrics)} campaigns. "
                    f"Avg open: {avg_open:.1f}%, click: {avg_click:.1f}%, reply: {avg_reply:.1f}%"
    }

    log.info("✅ Campaign analysis complete")
    return result

def generate_strategic_insights(analysis_data: Dict, llm: ChatGroq) -> Dict:
    """
    Generate strategic insights using LLM.
    FIXED: Now loads previous insights history from MEMORY_DIR.
    """
    
    log.info("💡 Generating strategic insights...")
    
    # Load previous insights to avoid repetition (now from MEMORY_DIR)
    insights_file = MEMORY_DIR / "global_insights_history.json"
    
    previous_insights = []
    if insights_file.exists():
        with open(insights_file, 'r') as f:
            history = json.load(f)
            previous_insights = [h.get("insights", {}) for h in history[-3:]]
    
    prompt = f"""You are a strategic email marketing consultant analyzing campaign performance.

ANALYSIS DATA:
{json.dumps(analysis_data, indent=2)}

PREVIOUS INSIGHTS (avoid repeating):
{json.dumps(previous_insights, indent=2)}

Generate fresh, actionable strategic insights in JSON format:
{{
    "performance_summary": "2-3 sentence summary",
    "content_guidelines": {{
        "subject_lines": ["tip 1", "tip 2", "tip 3"],
        "body_structure": ["tip 1", "tip 2"],
        "tone": ["tip 1", "tip 2"],
        "avoid": ["thing 1", "thing 2"]
    }},
    "targeting_recommendations": ["rec 1", "rec 2", "rec 3"],
    "timing_suggestions": ["suggestion 1", "suggestion 2"],
    "ab_test_ideas": ["idea 1", "idea 2", "idea 3"],
    "unique_insights": ["insight 1", "insight 2"]
}}

Be specific and actionable. Avoid generic advice."""
    
    messages = [
        SystemMessage(content="You are a strategic marketing analyst."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    
    try:
        # Extract JSON from response
        response_text = response.content
        
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_text = response_text[json_start:json_end].strip()
        elif "{" in response_text:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            json_text = response_text[json_start:json_end]
        else:
            json_text = response_text
        
        insights = json.loads(json_text)
        log.info("✅ Strategic insights generated")
        
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse insights: {e}")
        insights = {
            "performance_summary": response_text[:300],
            "content_guidelines": {},
            "targeting_recommendations": [],
            "timing_suggestions": [],
            "ab_test_ideas": [],
            "unique_insights": []
        }
    
    return insights


def generate_email_content(leads: List[Dict], product: str, insights: Dict, llm: ChatGroq) -> List[Dict]:
    """Generate personalized email content for leads (No path changes needed here)"""
    
    log.info(f"✍️ Generating content for {len(leads)} leads...")
    
    generated_emails = []
    
    # Extract key guidelines
    guidelines = insights.get("content_guidelines", {})
    subject_tips = guidelines.get("subject_lines", [])
    tone_tips = guidelines.get("tone", [])
    avoid_list = guidelines.get("avoid", [])
    
    for lead in leads:
        company = lead.get("company", "the company")
        name = lead.get("name", "there")
        title = lead.get("title", "")
        industry = lead.get("industry", "")
        
        prompt = f"""Create a personalized cold email for:
- Name: {name}
- Company: {company}
- Title: {title}
- Industry: {industry}
- Product: {product}

GUIDELINES:
- Subject tips: {', '.join(subject_tips[:2])}
- Tone: {', '.join(tone_tips[:2])}
- AVOID: {', '.join(avoid_list[:2])}

Requirements:
- Under 100 words
- Conversational and personalized
- One clear CTA
- Reference something specific about {industry} or {title}

Return JSON:
{{
    "subject": "compelling subject line",
    "body": "personalized email body",
    "cta": "clear call to action"
}}"""
        
        messages = [
            SystemMessage(content="You are an expert email copywriter."),
            HumanMessage(content=prompt)
        ]
        
        response = llm.invoke(messages)
        
        try:
            response_text = response.content
            
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "{" in response_text:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                json_text = response_text[json_start:json_end]
            else:
                json_text = response_text
            
            email = json.loads(json_text)
            
            # Add metadata
            email.update({
                "to_email": lead.get("email", ""),
                "company": company,
                "lead_name": name,
                "generated_at": datetime.now().isoformat()
            })
            
            generated_emails.append(email)
            
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse email for {company}: {e}")
            # Create fallback email
            generated_emails.append({
                "subject": f"Quick question about {company}",
                "body": f"Hi {name},\n\nI noticed {company} and thought {product} might help with your {industry} challenges.\n\nWould you be open to a brief conversation?",
                "cta": "Reply with your availability",
                "to_email": lead.get("email", ""),
                "company": company,
                "lead_name": name
            })
    
    log.info(f"✅ Generated {len(generated_emails)} emails")
    return generated_emails


def execute_outreach(emails: List[Dict], campaign_id: str) -> Dict:
    """Execute email sends with tracking (No path changes needed here)"""
    # Imports are typically outside the function in a real module, 
    # but keeping them here as per your provided snippet.
    from src.services.email_sender import EmailSender
    from src.services.tracker import EngagementTracker
    
    log.info(f"📤 Executing outreach for {len(emails)} emails...")
    
    sender = EmailSender()
    tracker = EngagementTracker()
    
    send_records = []
    stats = {"total": len(emails), "sent": 0, "failed": 0}
    
    for email in emails:
        to_email = email.get("to_email", "")
        subject = email.get("subject", "")
        body = email.get("body", "")
        
        if not to_email or not subject or not body:
            stats["failed"] += 1
            continue
        
        try:
            # 1. Attempt to send the email
            success = sender.send_email(to_email, subject, body)
            
            status = "sent" if success and not sender.dry_run else "failed"
            
            if success and not sender.dry_run:
                # FIX: Pass 'subject' and 'body' to satisfy track_send's arguments
                tracker.track_send(campaign_id, to_email, subject, body) 
                stats["sent"] += 1
            else:
                stats["failed"] += 1
            
            send_records.append({
                "to_email": to_email,
                "subject": subject,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "company": email.get("company", ""),
                "lead_name": email.get("lead_name", "")
            })
            
        except Exception as e:
            log.error(f"Error sending to {to_email}: {e}")
            stats["failed"] += 1
    
    stats["success_rate"] = (stats["sent"] / stats["total"] * 100) if stats["total"] > 0 else 0
    
    report = {
        "campaign_id": campaign_id,
        "execution_summary": stats,
        "send_records": send_records,
        "executed_at": datetime.now().isoformat()
    }
    
    log.info(f"✅ Outreach complete: {stats['sent']}/{stats['total']} sent ({stats['success_rate']:.1f}%)")
    
    return report