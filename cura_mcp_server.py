"""Cura MCP Server -- eldercare companion as MCP tools.

Exposes Cura's capabilities so Claude Code, Claude Desktop, or any
MCP client can use the eldercare companion without replacing their
existing workflow.

Tools:
  cura_ask        -- Core companion interaction (conversation, crisis, scam)
  cura_checkin    -- Run a daily check-in protocol (morning or evening)
  cura_scam_check -- Analyze a message/call for scam indicators
  cura_summary    -- Generate a caregiver summary for today
  cura_health     -- Agent status (pulse metrics, adherence, observations)

Resources:
  cura://profile  -- Elder profile configuration
  cura://memory   -- Companion memory context

Usage:
  python cura_mcp_server.py --config config/VALUES.json
  python cura_mcp_server.py --elder-name Margaret

  # In Claude Code .claude/mcp.json:
  {
    "mcpServers": {
      "cura": {
        "command": "python",
        "args": ["cura_mcp_server.py", "--elder-name", "Margaret"]
      }
    }
  }

Liberation Labs / TH Coalition. Proprietary.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("cura.mcp")

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, Resource
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

from cura.pulse.eldercare_pulse import (
    ElderProfile,
    EldercarePulseConfig,
    CheckInResult,
    HealthObservation,
)
from cura.pulse.checkin_composer import CheckinComposer, ComposedCheckin
from cura.privacy.scam_shield import ScamShield, ScamAlert
from cura.comms.caregiver_summary import CaregiverSummaryBuilder, DailySummary
from cura.memory.companion_memory import CompanionMemory, MemoryStore


def _load_config(config_path: str) -> dict:
    p = Path(config_path)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _build_profile(
    elder_name: str,
    config: dict,
    medications: list[str] | None = None,
) -> ElderProfile:
    from cura.pulse.medication import split_medication
    # Never fabricate a timing. An invented "morning" is announced as fact.
    meds = [split_medication(m) for m in (medications or [])]
    return ElderProfile(
        name=elder_name,
        preferred_name=elder_name,
        medications=meds,
        emergency_contacts=[],
        primary_caregiver={},
    )


def _json_response(data: dict) -> "list[TextContent]":
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def create_server(
    elder_name: str,
    config_path: str = "",
    data_dir: str = "",
) -> "Server":
    if not HAS_MCP:
        raise ImportError(
            "MCP SDK not installed. Install with: pip install mcp"
        )

    server = Server("cura")
    config = _load_config(config_path) if config_path else {}
    profile = _build_profile(elder_name, config)
    pulse = EldercarePulseConfig(profile)
    composer = CheckinComposer()
    scam_shield = ScamShield()
    summary_builder = CaregiverSummaryBuilder()
    memory_store = MemoryStore(data_dir)
    memory = memory_store.load(elder_name)

    # -- Tools --

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="cura_ask",
                description=(
                    "Core companion interaction. Send a message as or on "
                    "behalf of the elder. Handles conversation, medication "
                    "questions, scam detection, crisis keywords, and general "
                    "companionship. Returns the companion's response."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The message from or about the elder",
                        },
                        "context": {
                            "type": "string",
                            "description": "Interaction context (checkin, inbound, caregiver)",
                            "default": "conversation",
                        },
                    },
                    "required": ["message"],
                },
            ),
            Tool(
                name="cura_checkin",
                description=(
                    "Run a daily check-in protocol. Generates a personalized "
                    "greeting, medication reminder, enrichments (hydration, "
                    "cognitive exercises, safety tips), and memory-based "
                    "conversation touches. Returns the full check-in script."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "time_of_day": {
                            "type": "string",
                            "description": "morning or evening",
                            "default": "morning",
                        },
                        "weather": {
                            "type": "object",
                            "description": "Optional weather data (temp_f, condition, humidity)",
                        },
                    },
                },
            ),
            Tool(
                name="cura_scam_check",
                description=(
                    "Analyze a message, call transcript, or email for scam "
                    "indicators targeting elders. Checks for IRS impostor, "
                    "Medicare fraud, grandchild emergency, tech support, "
                    "romance scams, sweepstakes, and secrecy requests. "
                    "Returns severity, keywords found, and recommended action."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The message or transcript to analyze",
                        },
                    },
                    "required": ["message"],
                },
            ),
            Tool(
                name="cura_summary",
                description=(
                    "Generate a caregiver summary. Compiles today's check-in "
                    "results, mood observations, medication adherence, "
                    "wearable data, scam alerts, and highlights into a "
                    "summary suitable for SMS or detailed report."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "Output format: sms (brief) or detailed",
                            "default": "detailed",
                        },
                        "checkin_results": {
                            "type": "array",
                            "description": "List of check-in result objects from today",
                            "items": {"type": "object"},
                        },
                        "wearable_data": {
                            "type": "object",
                            "description": "Wearable sensor data (steps, heart_rate, baseline_steps)",
                        },
                    },
                },
            ),
            Tool(
                name="cura_health",
                description=(
                    "Agent health check. Returns pulse status, medication "
                    "adherence rate, recent observations, check-in history, "
                    "memory statistics, and active scam alerts."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "cura_ask":
            return await _handle_ask(arguments)
        elif name == "cura_checkin":
            return await _handle_checkin(arguments)
        elif name == "cura_scam_check":
            return await _handle_scam_check(arguments)
        elif name == "cura_summary":
            return await _handle_summary(arguments)
        elif name == "cura_health":
            return await _handle_health(arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    # -- Handlers --

    async def _handle_ask(args: dict) -> list[TextContent]:
        message = args.get("message", "")
        context = args.get("context", "conversation")
        lower = message.lower()
        name = profile.display_name

        alert = scam_shield.analyze_response(message)
        if alert:
            memory.add_observation(
                content=f"Scam indicator detected: {alert.description}",
                category="concern",
                source=context,
            )
            return _json_response({
                "status": "scam_alert",
                "response": scam_shield.get_reassurance(),
                "alert": {
                    "severity": alert.severity,
                    "type": alert.alert_type,
                    "keywords": alert.description,
                    "action": alert.recommended_action,
                },
                "caregiver_notify": alert.severity >= 0.8,
            })

        crisis_words = ["help", "emergency", "hurt", "fall", "fell", "pain", "scared"]
        if any(w in lower for w in crisis_words):
            memory.add_observation(
                content=f"Crisis keyword detected: {message[:200]}",
                category="concern",
                source=context,
                follow_up=True,
            )
            return _json_response({
                "status": "crisis",
                "response": (
                    f"{name}, I hear you. I'm alerting your family right now. "
                    "Stay calm, stay where you are. You're not alone."
                ),
                "action": "alert_caregiver",
                "severity": 0.9,
            })

        med_words = ["medication", "medicine", "pill", "pills", "prescription"]
        if any(w in lower for w in med_words):
            meds = profile.medications
            if meds:
                med_list = ", ".join(m.get("name", "medication") for m in meds)
                response = f"Your current medications are: {med_list}."
            else:
                response = (
                    "I don't have your medication list yet. "
                    "Ask your caregiver to add them to your profile."
                )
            return _json_response({
                "status": "ok",
                "response": response,
                "topic": "medication",
            })

        lonely_words = ["lonely", "alone", "miss", "sad", "bored"]
        if any(w in lower for w in lonely_words):
            memory.record_mood(
                mood="lonely" if "lonely" in lower or "alone" in lower else "sad",
                context=message[:100],
            )
            return _json_response({
                "status": "ok",
                "response": (
                    f"I'm sorry you're feeling that way, {name}. "
                    "I'm here with you right now, and I enjoy our talks. "
                    "Would you like to play a word game, or just keep chatting?"
                ),
                "mood_logged": True,
            })

        memory.add_observation(
            content=message[:300],
            category="daily_life",
            source=context,
        )
        memory.conversation_count += 1

        responses = [
            f"Thank you for sharing that, {name}. Tell me more.",
            f"That's interesting. What else is on your mind?",
            f"I hear you, {name}. I'm glad you told me.",
            f"That's wonderful. I enjoy hearing about your day.",
            f"How does that make you feel, {name}?",
        ]
        return _json_response({
            "status": "ok",
            "response": random.choice(responses),
            "memory_context": memory.generate_context()[:500],
        })

    async def _handle_checkin(args: dict) -> list[TextContent]:
        time_of_day = args.get("time_of_day", "morning")
        weather = args.get("weather")

        if time_of_day == "evening":
            checkin = composer.compose_evening(pulse, weather=weather)
        else:
            checkin = composer.compose_morning(pulse, weather=weather)

        enrichment_data = []
        for e in checkin.enrichments:
            enrichment_data.append({
                "message": e.message,
                "priority": e.priority,
                "category": e.category,
            })

        return _json_response({
            "status": "ok",
            "time_of_day": time_of_day,
            "elder_name": profile.display_name,
            "greeting": checkin.greeting,
            "medication_reminder": checkin.medication_reminder,
            "memory_touches": checkin.memory_touches,
            "enrichments": enrichment_data,
            "wearable_observations": checkin.wearable_observations,
            "scam_tip": checkin.scam_addition,
            "all_messages": checkin.all_messages,
        })

    async def _handle_scam_check(args: dict) -> list[TextContent]:
        message = args.get("message", "")
        alert = scam_shield.analyze_response(message)

        if not alert:
            return _json_response({
                "status": "clean",
                "message": "No scam indicators detected.",
                "scam_detected": False,
            })

        return _json_response({
            "status": "alert",
            "scam_detected": True,
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "keywords_found": alert.description,
            "elder_statement": alert.elder_statement,
            "recommended_action": alert.recommended_action,
            "reassurance": scam_shield.get_reassurance(),
        })

    async def _handle_summary(args: dict) -> list[TextContent]:
        fmt = args.get("format", "detailed")
        checkin_results = args.get("checkin_results", [])
        wearable_data = args.get("wearable_data")

        summary = summary_builder.build(
            elder_name=profile.display_name,
            memory=memory,
            checkin_results=checkin_results,
            wearable_data=wearable_data,
            scam_alerts=len(scam_shield.unnotified_alerts),
            medications_total=len(profile.medications),
        )

        formatted = summary.format_sms() if fmt == "sms" else summary.format_detailed()

        return _json_response({
            "status": "ok",
            "elder_name": summary.elder_name,
            "date": summary.date,
            "morning_reached": summary.morning_reached,
            "evening_reached": summary.evening_reached,
            "medications": f"{summary.medications_confirmed}/{summary.medications_total}",
            "mood": summary.mood,
            "concerns": summary.concerns,
            "highlights": summary.highlights,
            "people_mentioned": summary.people_mentioned,
            "scam_alerts": summary.scam_alerts,
            "formatted": formatted,
        })

    async def _handle_health(args: dict) -> list[TextContent]:
        from cura.readiness import gaps_for_health
        return _json_response({
            "status": "healthy",
            "gaps": gaps_for_health(config_path),
            "elder_name": profile.display_name,
            "pulse": {
                "checkins_7d": len(pulse.recent_checkins),
                "observations_7d": len(pulse.recent_observations),
                "adherence_rate_7d": round(pulse.adherence_rate_7d, 2),
                "missed_this_week": pulse.missed_checkins_this_week,
                "needs_social_outreach": pulse.needs_social_outreach,
                "needs_elevated_monitoring": pulse.needs_elevated_monitoring,
                "days_since_outing": pulse.days_since_outing,
            },
            "memory": {
                "observations": len(memory.observations),
                "people_tracked": len(memory.people),
                "upcoming_events": len(memory.upcoming_events),
                "conversation_count": memory.conversation_count,
                "pending_followups": len(memory.pending_followups()),
                "topics": memory.topics_of_interest[:10],
            },
            "scam_shield": {
                "total_alerts": len(scam_shield.alerts),
                "unnotified": len(scam_shield.unnotified_alerts),
            },
            "profile": {
                "medications": len(profile.medications),
                "emergency_contacts": len(profile.emergency_contacts),
                "mobility": profile.mobility_baseline,
                "cognitive": profile.cognitive_baseline,
            },
        })

    # -- Resources --

    @server.list_resources()
    async def list_resources():
        return [
            Resource(
                uri=f"cura://{profile.display_name}/profile",
                name="Elder Profile",
                description="Current elder profile and care configuration",
                mimeType="application/json",
            ),
            Resource(
                uri=f"cura://{profile.display_name}/memory",
                name="Companion Memory",
                description="Conversation context and relationship memory",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str):
        if uri.endswith("/profile"):
            data = {
                "name": profile.name,
                "preferred_name": profile.preferred_name,
                "medications": profile.medications,
                "morning_time": profile.morning_time,
                "evening_time": profile.evening_time,
                "timezone": profile.timezone,
                "mobility": profile.mobility_baseline,
                "cognitive": profile.cognitive_baseline,
                "emergency_contacts": profile.emergency_contacts,
            }
            return json.dumps(data, indent=2)
        elif uri.endswith("/memory"):
            return memory.generate_context()
        return json.dumps({"error": f"Unknown resource: {uri}"})

    return server


async def main(elder_name: str, config_path: str = "", data_dir: str = ""):
    server = create_server(elder_name, config_path, data_dir)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="Cura MCP Server")
    parser.add_argument(
        "--elder-name", default="friend",
        help="Elder's preferred name",
    )
    parser.add_argument(
        "--config", default="",
        help="Path to VALUES.json config",
    )
    parser.add_argument(
        "--data-dir", default="",
        help="Directory for memory storage (default: ~/.cura/memory)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.elder_name, args.config, args.data_dir))
