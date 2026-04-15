import asyncio
import logging
import os

import uvicorn
from dotenv import load_dotenv

from runtime.audit import AuditLogger
from runtime.memory import Memory
from runtime.orchestrator import Orchestrator
from runtime.skill_loader import SkillLoader
from runtime.logging_config import setup_logging
from api.routes import create_app

load_dotenv()
setup_logging()
logger = logging.getLogger("retailos.runtime")


async def init_runtime():
    """Initialize all runtime components and return the FastAPI app."""

    # Initialize memory (Redis — mandatory in production)
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    env = os.environ.get("RETAILOS_ENV", os.environ.get("ENV", "development")).lower()
    memory = Memory(redis_url)
    await memory.init(require_redis=(env == "production"))

    # Initialize audit logger (PostgreSQL)
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/retailos")
    audit = AuditLogger(database_url)
    await audit.init()

    # Load all skills
    skill_loader = SkillLoader(skills_dir="skills", memory=memory, audit=audit)
    skills = await skill_loader.discover_and_load()
    logger.info(
        "Loaded runtime skills",
        extra={"skill_count": len(skills), "skill_names": sorted(skills.keys())},
    )

    # Initialize orchestrator
    api_key = os.environ.get("GEMINI_API_KEY", "")
    orchestrator = Orchestrator(
        memory=memory,
        audit=audit,
        skills=skills,
        api_key=api_key,
    )

    # Start the orchestrator event loop
    await orchestrator.start()

    # Seed demo data into memory
    await _seed_memory(memory)

    # Create FastAPI app
    app = create_app(orchestrator)

    # Store references for cleanup
    app.state.orchestrator = orchestrator
    app.state.memory = memory
    app.state.audit = audit

    return app


async def _seed_memory(memory: Memory):
    """Seed memory with demo data for realistic behavior."""
    # Supplier histories
    await memory.set("supplier:SUP-001:history", {
        "name": "FreshFreeze Distributors",
        "orders": 12,
        "avg_delivery_days": 2.3,
        "reliability": "excellent",
        "last_order": "2026-03-20",
        "notes": "Consistently on time, good quality",
    })
    await memory.set("supplier:SUP-002:history", {
        "name": "CoolFoods India",
        "orders": 8,
        "avg_delivery_days": 4.1,
        "reliability": "declining",
        "last_order": "2026-03-18",
        "notes": "Last 3 of 4 orders were 2 days late",
        "late_deliveries": 3,
    })
    await memory.set("supplier:SUP-003:history", {
        "name": "MegaMart Wholesale",
        "orders": 5,
        "avg_delivery_days": 1.8,
        "reliability": "good",
        "last_order": "2026-03-15",
        "notes": "New supplier, fast so far but higher prices",
    })

    # Yesterday's analytics summary
    await memory.set("orchestrator:daily_summary", {
        "timestamp": 1711238400,
        "summary": "System processed 47 events yesterday. CoolFoods India was 2 days late on delivery again — 3rd time in 4 orders. Protein category offers had 34% conversion rate. Ice cream restocking frequency increased 20% vs last month.",
        "insights": [
            {
                "type": "supplier_reliability",
                "title": "CoolFoods delivery declining",
                "detail": "CoolFoods India has been 2 days late on 3 of the last 4 orders. Average delivery time increased from 2.5 to 4.1 days.",
                "recommendation": "Deprioritize CoolFoods in procurement rankings",
                "severity": "warning",
            },
            {
                "type": "conversion_rate",
                "title": "Protein offers converting well",
                "detail": "Offers for protein products (whey, bars, supplements) had a 34% conversion rate — highest across all categories.",
                "recommendation": "Prioritize protein category for customer outreach",
                "severity": "info",
            },
        ],
        "recommendations": [
            "Deprioritize CoolFoods India in procurement rankings",
            "Review ice cream reorder thresholds — may be set too high",
            "Focus customer offers on protein category",
        ],
    })

    logger.info("Seeded demo memory")


# Global app reference for uvicorn
app = None


async def startup():
    global app
    app = await init_runtime()
    return app


def main():
    """Entry point — starts the RetailOS runtime."""

    async def run():
        global app
        app = await init_runtime()

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(run())


if __name__ == "__main__":
    main()
