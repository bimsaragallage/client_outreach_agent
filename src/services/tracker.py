import json
import os
import re
import imaplib
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
from src.core.logger import log
from src.core.config import settings


class EngagementTracker:
    """Track full campaign engagement with content, timing, and sentiment details."""

    MEMORY_DIR = Path("data") / "memory"
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_PATH = MEMORY_DIR / "engagement_events.json"

    def __init__(self):
        self.sender_id = settings.from_email
        self.events: List[Dict] = self._load_events()

    # ---------------------- Internal Utilities ---------------------- #
    def _load_events(self) -> List[Dict]:
        """Load engagement events from disk."""
        if self.STORAGE_PATH.exists():
            try:
                with open(self.STORAGE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load engagement data: {e}")
        return []

    def _save_events(self) -> None:
        """Atomically save engagement events to disk."""
        try:
            tmp_path = self.STORAGE_PATH.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.events, f, indent=2)
            os.replace(tmp_path, self.STORAGE_PATH)
        except Exception as e:
            log.error(f"Failed to save engagement data: {e}")

    def _record_event(self, event: Dict) -> None:
        """Append and persist a new event."""
        self.events.append(event)
        self._save_events()
        log.debug(f"Tracked event: {event}")

    def _get_last_send_time(self, campaign_id: str, lead_email: str) -> Optional[datetime]:
        """Find the last send event for a lead."""
        send_events = [
            e for e in self.events
            if e["campaign_id"] == campaign_id and e["email"] == lead_email and e["type"] == "send"
        ]
        if send_events:
            send_events.sort(key=lambda x: x["timestamp"])
            return datetime.fromisoformat(send_events[-1]["timestamp"])
        return None

    # ---------------------- Tracking Methods ---------------------- #
    def track_send(
        self,
        campaign_id: str,
        lead_email: str,
        subject: str,
        body: str,
        send_time: Optional[datetime] = None,
    ) -> None:
        """Record email send event with content details."""
        event = {
            "type": "send",
            "campaign_id": campaign_id,
            "email": lead_email,
            "sender": self.sender_id,
            "timestamp": (send_time or datetime.utcnow()).isoformat(),
            "subject": subject,
            "body": body,
        }
        self._record_event(event)

    def track_open(self, campaign_id: str, lead_email: str, open_time: Optional[datetime] = None) -> None:
        """Record open event (placeholder for pixel tracking integration)."""
        pass

    def track_click(self, campaign_id: str, lead_email: str, url: str) -> None:
        """Record click event (placeholder for redirect tracking integration)."""
        pass

    def track_reply(
        self,
        campaign_id: str,
        lead_email: str,
        reply_text: str,
        positivity_score: Optional[float] = None,
        reply_time: Optional[datetime] = None,
    ) -> None:
        """Record reply with sentiment or positivity metadata."""
        event = {
            "type": "reply",
            "campaign_id": campaign_id,
            "email": lead_email,
            "sender": self.sender_id,
            "timestamp": (reply_time or datetime.utcnow()).isoformat(),
            "reply_text": reply_text,
            "positivity_score": positivity_score,
        }
        self._record_event(event)

    # ---------------------- GMAIL SYNC FUNCTIONALITY ---------------------- #
    def _get_email_body(self, msg) -> str:
        """Extracts the plain text body from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get("Content-Disposition"))
                if ctype == "text/plain" and "attachment" not in cdispo:
                    try:
                        return part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="ignore"
                        )
                    except Exception:
                        continue
        else:
            if msg.get_content_type() == "text/plain":
                try:
                    return msg.get_payload(decode=True).decode(
                        msg.get_content_charset() or "utf-8", errors="ignore"
                    )
                except Exception:
                    return ""
        return ""

    def _extract_reply_metadata(self, msg) -> Optional[Dict]:
        """Identify campaign data from a reply email using subject matching."""
        subject = msg.get("Subject", "")
        sender = msg.get("From", "").split("<")[-1].replace(">", "").strip()
        body = self._get_email_body(msg)

        # Parse reply time robustly
        try:
            reply_time = parsedate_to_datetime(msg.get("Date"))
            if reply_time.tzinfo is None:
                reply_time = reply_time.replace(tzinfo=timezone.utc)
            else:
                reply_time = reply_time.astimezone(timezone.utc)
        except Exception:
            reply_time = datetime.utcnow().replace(tzinfo=timezone.utc)

        if not re.match(r"^Re:\s", subject, re.IGNORECASE):
            return None

        clean_reply_subject = re.sub(r"^Re:\s*", "", subject, flags=re.IGNORECASE).strip().lower()

        relevant_sends = [
            e for e in self.events
            if e["type"] == "send" and e["email"].lower() == sender.lower()
        ]

        for send_event in relevant_sends:
            sent_subject_lower = send_event["subject"].lower().strip()
            send_time = datetime.fromisoformat(send_event["timestamp"])
            if send_time.tzinfo is None:
                send_time = send_time.replace(tzinfo=timezone.utc)

            if sent_subject_lower == clean_reply_subject and reply_time > send_time:
                return {
                    "campaign_id": send_event["campaign_id"],
                    "lead_email": sender,
                    "reply_text": body,
                    "reply_time": reply_time,
                    "positivity_score": None,
                }

        log.debug(f"Unmatched reply from {sender} with subject: {clean_reply_subject}")
        return None

    def sync_replies_from_gmail(self, mark_as_read: bool = True) -> int:
        """Fetch unseen replies via IMAP and log them (live sync)."""
        if not all([settings.imap_server, settings.app_password, settings.from_email]):
            log.warning("IMAP settings incomplete. Skipping Gmail sync.")
            return 0

        new_replies_count = 0
        mail = None

        try:
            log.info("📧 Connecting to IMAP server for reply sync...")
            mail = imaplib.IMAP4_SSL(settings.imap_server, settings.imap_port)
            mail.login(settings.from_email, settings.app_password)
            mail.select("inbox")

            status, email_ids = mail.search(None, "UNSEEN")
            if status != "OK":
                log.error(f"IMAP search failed: {email_ids}")
                return 0

            id_list = email_ids[0].split()
            log.info(f"Found {len(id_list)} new email(s).")

            for email_id in id_list:
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue

                msg = message_from_bytes(msg_data[0][1])
                reply_data = self._extract_reply_metadata(msg)

                if reply_data:
                    already_tracked = any(
                        e["type"] == "reply"
                        and e["email"].lower() == reply_data["lead_email"].lower()
                        and e["timestamp"] == reply_data["reply_time"].isoformat()
                        for e in self.events
                    )

                    if not already_tracked:
                        self.track_reply(**reply_data)
                        new_replies_count += 1
                        log.info(
                            f"📨 Tracked reply from {reply_data['lead_email']} "
                            f"for campaign {reply_data['campaign_id']}."
                        )

                if mark_as_read:
                    mail.store(email_id, "+FLAGS", "\\Seen")

            log.info(f"✅ Gmail sync complete. Logged {new_replies_count} new replies.")

        except imaplib.IMAP4.error as e:
            log.error(f"IMAP connection error: {e}")
        except Exception as e:
            log.error(f"Critical Gmail sync error: {e}")
        finally:
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass

        return new_replies_count

    # ---------------------- Reporting ---------------------- #
    def get_campaign_stats(self, campaign_id: str) -> Dict:
        """Return advanced campaign metrics with timing & sentiment info."""
        self.sync_replies_from_gmail()

        campaign_events = [
            e for e in self.events
            if e["campaign_id"] == campaign_id and e["sender"] == self.sender_id
        ]

        sends = [e for e in campaign_events if e["type"] == "send"]
        opens = [e for e in campaign_events if e["type"] == "open"]
        clicks = [e for e in campaign_events if e["type"] == "click"]
        replies = [e for e in campaign_events if e["type"] == "reply"]

        sent_emails = len(sends)
        unique_opens = len({e["email"] for e in opens})
        unique_clicks = len({e["email"] for e in clicks})
        unique_replies = len({e["email"] for e in replies})

        open_rate = unique_opens / sent_emails * 100 if sent_emails else 0
        click_rate = unique_clicks / sent_emails * 100 if sent_emails else 0
        reply_rate = unique_replies / sent_emails * 100 if sent_emails else 0

        avg_open_delay = (
            sum(e.get("minutes_since_send", 0) for e in opens if e.get("minutes_since_send"))
            / len(opens)
            if opens else None
        )

        avg_positivity = (
            sum(e.get("positivity_score", 0) for e in replies if e.get("positivity_score"))
            / len(replies)
            if replies else None
        )

        return {
            "campaign_id": campaign_id,
            "total_sends": sent_emails,
            "total_opens": unique_opens,
            "total_clicks": unique_clicks,
            "total_replies": unique_replies,
            "open_rate": open_rate,
            "click_rate": click_rate,
            "reply_rate": reply_rate,
            "avg_open_delay_minutes": avg_open_delay,
            "avg_reply_positivity": avg_positivity,
        }

    def get_reply_metadata(self, campaign_id: str) -> List[Dict]:
        """Return all reply-level metadata for a given campaign."""
        replies = [
            e for e in self.events
            if e["campaign_id"] == campaign_id and e["type"] == "reply"
        ]

        reply_metadata = []
        for r in replies:
            reply_metadata.append({
                "lead_email": r.get("email"),
                "reply_time": r.get("timestamp"),
                "positivity_score": r.get("positivity_score"),
                "reply_excerpt": (r.get("reply_text") or "")[:200],
            })

        return reply_metadata

    def is_ready_for_analysis(self, campaign_id: str, min_responses: int = 1) -> bool:
        stats = self.get_campaign_stats(campaign_id)
        total_responses = stats.get("total_replies", 0)
        log.info(f"Analysis check: {total_responses} replies found for {campaign_id}")
        return total_responses >= min_responses