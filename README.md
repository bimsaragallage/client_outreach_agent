# Client Outreach Agent

A production-ready, LangGraph-based automated client outreach system that manages lead discovery, content generation, campaign execution, and performance analysis — all running locally with data persistence.

## Features

- **LangGraph Node Orchestration**: Workflow powered by LangGraph nodes executing each stage in sequence  
- **Local Data Storage**: Saves process data and results in JSON format  
- **Memory-Enabled**: Learns from previous campaigns for continuous improvement  
- **Modular Architecture**: Easily extendable and customizable components  
- **Production-Ready**: Includes structured logging, error handling, and testing

## Architecture

Discovery → Analyze Previous Mails → Feedback/Insights → Content Generation → Outreach

## Prerequisites

- Python 3.10+
- Groq API key
- SMTP credentials (for sending emails)

##  Quick Start

### 1. Clone and Setup

```bash
# Clone repository
git clone <https://github.com/bimsaragallage/clent_outreach_agent>
cd client_outreach_agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your settings
nano .env
```

### 3. Run Outreach Campaign Dashboard

```bash
# Using Python directly
python -m src.app
```

### 4. Data Upload

Before running a campaign, you need to upload your lead dataset.

## Dataset Requirements

Your dataset must be a CSV file containing at least the following columns:

| Column | Description |
|---------|--------------|
| `Business Name` | The name of the company or client |
| `Email` | The recipient’s email address |

##  Project Structure

```
client_outreach_full
├── data
│   ├── campaigns
│   ├── leads
│   ├── memory
│   └── uploaded_leads
├── logs
├── src
│   ├── api
│   ├── app.py
│   ├── core
│   ├── crew
│   ├── services
│   └── web
├── .env.example
├── docker-compose.yml
├── dockerfile
├── README.md
└── requirements.txt
```

## Docker Deployment

```bash
# Build and start the Outreach API service
docker-compose up -d

# View logs from the outreach_api container
docker-compose logs -f outreach_api

# Stop and remove containers
docker-compose down
```

**Services included:**
- Main application

## Configuration

### Environment Variables (.env)

| Variable | Description | Default |
|-----------|-------------|---------|
| `GROQ_API_KEY` | API key for Groq LLM services | Required |
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USER` | SMTP username (email address) | Required |
| `SMTP_PASSWORD` | SMTP password (or app-specific password) | Required |
| `FROM_EMAIL` | Sender email address | Required |
| `IMAP_SERVER` | IMAP server hostname for reading replies | `imap.gmail.com` |
| `IMAP_PORT` | IMAP port | `993` |
| `APP_PASSWORD` | App-specific password for email access | Required |
| `CHROMA_PERSIST_DIR` | Local directory for vector memory persistence | `./data/memory` |
| `LOG_LEVEL` | Logging verbosity level | `INFO` |

##  Monitoring

### Logs

```bash
# View real-time logs
tail -f logs/app_$(date +%Y-%m-%d).log

# Search for specific log entries (e.g., errors)
grep "ERROR" logs/app_*.log
```

### Metrics

Check `data/campaigns/campaign_id/outreach_report.json` for campaign outputs.

##  Security

- **Never commit `.env`** - Contains API keys
- **Use app passwords** - For Gmail SMTP
- **Enable 2FA** - On all API accounts
- **DRY_RUN_MODE** - Test safely before production

### Email Sending Fails

- Check SMTP credentials
- Enable "Less secure app access" (Gmail)
- Use app-specific password

##  Tips

- Use small `lead_count` values during development
- Check logs regularly for errors

##  Support

For issues and questions:
- Open GitHub Issue
- Review logs in logs/