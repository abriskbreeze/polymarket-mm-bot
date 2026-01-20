"""
Market discovery using Polymarket Gamma API.
"""

import json
import requests
from typing import List, Optional, Dict, Any
from src.config import GAMMA_API_URL
from src.models import Market, Event, Outcome
from src.utils import setup_logging

logger = setup_logging()


def fetch_active_markets(
    limit: int = 100,
    offset: int = 0,
    order: str = "volume",
    ascending: bool = False
) -> List[Market]:
    """
    Fetch active markets from Gamma API.

    Args:
        limit: Maximum number of markets to return (max 100)
        offset: Pagination offset
        order: Sort field (volume, liquidity, etc.)
        ascending: Sort direction

    Returns:
        List of Market objects
    """
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": min(limit, 100),
        "offset": offset,
        "active": "true",
        "closed": "false",
        "order": order,
        "ascending": str(ascending).lower()
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    markets_data = response.json()
    return [_parse_market(m) for m in markets_data]


def fetch_market_by_id(condition_id: str) -> Optional[Market]:
    """
    Fetch a single market by condition ID.

    Args:
        condition_id: The market's condition ID

    Returns:
        Market object or None if not found
    """
    url = f"{GAMMA_API_URL}/markets/{condition_id}"

    response = requests.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()

    return _parse_market(response.json())


def fetch_market_by_slug(slug: str) -> Optional[Market]:
    """
    Fetch a single market by slug.

    Args:
        slug: The market's URL slug

    Returns:
        Market object or None if not found
    """
    url = f"{GAMMA_API_URL}/markets"
    params = {"slug": slug}

    response = requests.get(url, params=params)
    response.raise_for_status()

    markets = response.json()
    if not markets:
        return None

    return _parse_market(markets[0])


def fetch_events(
    limit: int = 50,
    active: bool = True,
    closed: bool = False
) -> List[Event]:
    """
    Fetch events from Gamma API.

    Args:
        limit: Maximum number of events
        active: Filter for active events
        closed: Filter for closed events

    Returns:
        List of Event objects
    """
    url = f"{GAMMA_API_URL}/events"
    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower()
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    events_data = response.json()
    return [_parse_event(e) for e in events_data]


def search_markets(query: str, limit: int = 20) -> List[Market]:
    """
    Search markets by text query.

    Args:
        query: Search string
        limit: Maximum results

    Returns:
        List of matching Market objects
    """
    url = f"{GAMMA_API_URL}/search"
    params = {
        "q": query,
        "limit": limit
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    # Search endpoint returns markets directly
    results = response.json()
    markets = results.get("markets", results) if isinstance(results, dict) else results

    return [_parse_market(m) for m in markets if m]


def _parse_market(data: Dict[str, Any]) -> Market:
    """Parse raw API response into Market object"""

    # Parse outcomes - handle different API response formats
    outcomes = []

    # Try to get token IDs from clobTokenIds field
    clob_token_ids_raw = data.get("clobTokenIds", [])
    outcome_names_raw = data.get("outcomes", [])

    # Parse JSON strings if needed
    if isinstance(clob_token_ids_raw, str):
        try:
            clob_token_ids = json.loads(clob_token_ids_raw)
        except json.JSONDecodeError:
            clob_token_ids = []
    else:
        clob_token_ids = clob_token_ids_raw

    if isinstance(outcome_names_raw, str):
        try:
            outcome_names = json.loads(outcome_names_raw)
        except json.JSONDecodeError:
            outcome_names = []
    else:
        outcome_names = outcome_names_raw

    if clob_token_ids and outcome_names:
        # Standard format with clobTokenIds
        for i, token_id in enumerate(clob_token_ids):
            name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
            outcomes.append(Outcome(
                name=name,
                token_id=token_id
            ))
    elif "tokens" in data:
        # Alternative format with tokens array
        for token in data["tokens"]:
            outcomes.append(Outcome(
                name=token.get("outcome", "Unknown"),
                token_id=token.get("token_id", "")
            ))

    return Market(
        condition_id=data.get("conditionId", data.get("condition_id", "")),
        question=data.get("question", ""),
        slug=data.get("slug", ""),
        outcomes=outcomes,
        active=data.get("active", True),
        closed=data.get("closed", False),
        volume=float(data.get("volume", 0) or 0),
        liquidity=float(data.get("liquidity", 0) or 0),
        end_date=data.get("endDate"),
        description=data.get("description")
    )


def _parse_event(data: Dict[str, Any]) -> Event:
    """Parse raw API response into Event object"""

    markets = []
    if "markets" in data:
        markets = [_parse_market(m) for m in data["markets"]]

    return Event(
        event_id=data.get("id", ""),
        title=data.get("title", ""),
        slug=data.get("slug", ""),
        markets=markets,
        active=data.get("active", True)
    )
