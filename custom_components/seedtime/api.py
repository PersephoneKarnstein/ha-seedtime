"""API client for Seedtime garden planner."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import json

import aiohttp

from .const import BASE_URL, REST_API_URL, SIGN_IN_URL

GRAPHQL_URL = f"{BASE_URL}/graphql"

_LOGGER = logging.getLogger(__name__)

# GraphQL query that fetches the full garden plan with all geometry data
GARDEN_PLAN_QUERY = """
query FetchGardenPlan {
  primaryGarden {
    id
    title
    firstFrostMonthday { month day }
    lastFrostMonthday { month day }
    gardenPlan {
      id
      width
      height
      plantingLocations(first: 500) {
        nodes {
          id
          name
          fillColor
          hidden
          index
          groupId
          shape {
            rotation
            segments {
              start { x y }
              bezierControlPoints { x y }
            }
          }
          plantingFormations(first: 100) {
            nodes {
              id
              draft
              pattern
              plantSpacing
              rowSpacing
              shape {
                rotation
                segments {
                  start { x y }
                  bezierControlPoints { x y }
                }
              }
              clusters {
                plantCount
                shape {
                  rotation
                  segments {
                    start { x y }
                    bezierControlPoints { x y }
                  }
                }
                rows {
                  start { x y }
                  end { x y }
                }
              }
              gardenCrop {
                id
                title
                color
                seedingDate
                harvestingDate
                groundOccupationStart
                groundOccupationEnd
                cropName
                cropDefinition {
                  id
                  plantSpacingInches
                  rowSpacingInches
                }
              }
            }
          }
        }
      }
      landmarks(first: 500) {
        nodes {
          id
          name
          fillColor
          strokeColor
          strokeWidth
          iconName
          hidden
          index
          groupId
          shape {
            rotation
            segments {
              start { x y }
              bezierControlPoints { x y }
            }
          }
        }
      }
      groups(first: 200) {
        nodes {
          id
          name
          hidden
          index
          groupId
        }
      }
      texts(first: 200) {
        nodes {
          id
          text
          fontSize
          hidden
          groupId
          shape {
            rotation
            segments {
              start { x y }
              bezierControlPoints { x y }
            }
          }
        }
      }
    }
    cropSchedules(first: 50) {
      nodes {
        id
        name
        disabled
        gardenCrops(startDate: "$start_date", endDate: "$end_date", first: 500) {
          nodes {
            id
            title
            color
            seedingDate
            harvestingDate
            groundOccupationStart
            groundOccupationEnd
          }
        }
      }
    }
  }
}
"""


class SeedtimeAuthError(Exception):
    """Raised when authentication fails."""


class SeedtimeConnectionError(Exception):
    """Raised when connection to Seedtime fails."""


class SeedtimeApiClient:
    """Client for the Seedtime API."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._csrf_token: str | None = None
        self._authenticated = False

    async def authenticate(self) -> None:
        """Authenticate with Seedtime via Devise form login."""
        try:
            # Step 1: GET login page to extract CSRF token
            async with self._session.get(SIGN_IN_URL) as resp:
                if resp.status != 200:
                    raise SeedtimeConnectionError(
                        f"Failed to load login page: HTTP {resp.status}"
                    )
                html = await resp.text()

            token = self._extract_csrf_token(html)
            if not token:
                raise SeedtimeConnectionError(
                    "Could not find CSRF token on login page"
                )

            # Step 2: POST form login
            form_data = {
                "utf8": "\u2713",
                "authenticity_token": token,
                "user[email]": self._email,
                "user[password]": self._password,
                "commit": "Log in",
            }
            async with self._session.post(
                SIGN_IN_URL,
                data=form_data,
                allow_redirects=True,
            ) as resp:
                # Successful login typically redirects to dashboard
                if resp.status == 200:
                    body = await resp.text()
                    # Check if we're still on the login page (failed auth)
                    if "Invalid Email or password" in body or 'id="new_user"' in body:
                        raise SeedtimeAuthError("Invalid email or password")
                    # Extract fresh CSRF token from the post-login page
                    fresh_token = self._extract_csrf_token(body)
                    if fresh_token:
                        self._csrf_token = fresh_token
                    self._authenticated = True
                    return
                if resp.status in (301, 302):
                    # Redirect after login is expected success
                    self._authenticated = True
                    # Fetch the redirected page to get a fresh CSRF token
                    await self._refresh_csrf_token()
                    return

            # Fallback: try JSON login endpoint
            await self._authenticate_json()

        except (aiohttp.ClientError, TimeoutError) as err:
            raise SeedtimeConnectionError(
                f"Connection error during authentication: {err}"
            ) from err

    async def _authenticate_json(self) -> None:
        """Fallback: authenticate via JSON endpoint."""
        json_url = f"{SIGN_IN_URL}.json"
        payload = {
            "user": {
                "email": self._email,
                "password": self._password,
            }
        }
        async with self._session.post(json_url, json=payload) as resp:
            if resp.status == 401:
                raise SeedtimeAuthError("Invalid email or password")
            if resp.status not in (200, 201):
                raise SeedtimeConnectionError(
                    f"JSON login failed: HTTP {resp.status}"
                )
            self._authenticated = True

    @staticmethod
    def _extract_csrf_token(html: str) -> str | None:
        """Extract CSRF authenticity_token from Devise login page HTML."""
        # Look for meta tag first
        match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html
        )
        if match:
            return match.group(1)
        # Fall back to hidden input
        match = re.search(
            r'<input[^>]+name="authenticity_token"[^>]+value="([^"]+)"', html
        )
        if match:
            return match.group(1)
        # Try reverse attribute order
        match = re.search(
            r'<input[^>]+value="([^"]+)"[^>]+name="authenticity_token"', html
        )
        if match:
            return match.group(1)
        return None

    async def _refresh_csrf_token(self) -> None:
        """Fetch an authenticated page to get a fresh CSRF token for API calls."""
        try:
            async with self._session.get(BASE_URL) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    token = self._extract_csrf_token(html)
                    if token:
                        self._csrf_token = token
                        _LOGGER.debug("Refreshed CSRF token")
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Failed to refresh CSRF token")

    async def _ensure_authenticated(self) -> None:
        """Re-authenticate if needed."""
        if not self._authenticated:
            await self.authenticate()

    async def graphql_query(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query, retrying once on auth failure."""
        await self._ensure_authenticated()

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(2):
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._csrf_token:
                headers["X-CSRF-Token"] = self._csrf_token

            try:
                async with self._session.post(
                    GRAPHQL_URL,
                    json=payload,
                    headers=headers,
                ) as resp:
                    # Auth/CSRF failure: 401, 422, or redirect to login
                    if resp.status in (401, 422) or (
                        resp.status in (301, 302)
                        and "/sign_in" in str(resp.headers.get("Location", ""))
                    ):
                        if attempt == 0:
                            self._authenticated = False
                            await self.authenticate()
                            continue
                        raise SeedtimeAuthError("Session expired")

                    if resp.status != 200:
                        raise SeedtimeConnectionError(
                            f"GraphQL request failed: HTTP {resp.status}"
                        )

                    body = await resp.json(content_type=None)
                    if "errors" in body and not body.get("data"):
                        raise SeedtimeConnectionError(
                            f"GraphQL errors: {body['errors']}"
                        )
                    return body.get("data", {})

            except json.JSONDecodeError as err:
                raise SeedtimeConnectionError(
                    f"GraphQL response was not valid JSON: {err}"
                ) from err
            except (aiohttp.ClientError, TimeoutError) as err:
                if attempt == 0:
                    self._authenticated = False
                    await self.authenticate()
                    continue
                raise SeedtimeConnectionError(
                    f"GraphQL connection error: {err}"
                ) from err

        raise SeedtimeConnectionError("GraphQL request failed after retry")

    async def rest_get(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        """Make authenticated REST GET request."""
        await self._ensure_authenticated()
        url = f"{REST_API_URL}/{endpoint}"

        for attempt in range(2):
            try:
                async with self._session.get(url, params=params) as resp:
                    if resp.status == 401 or (
                        resp.status in (301, 302)
                        and "/sign_in" in str(resp.headers.get("Location", ""))
                    ):
                        if attempt == 0:
                            self._authenticated = False
                            await self.authenticate()
                            continue
                        raise SeedtimeAuthError("Session expired")

                    if resp.status != 200:
                        raise SeedtimeConnectionError(
                            f"REST request to {endpoint} failed: HTTP {resp.status}"
                        )

                    return await resp.json(content_type=None)

            except json.JSONDecodeError as err:
                raise SeedtimeConnectionError(
                    f"REST response was not valid JSON: {err}"
                ) from err
            except (aiohttp.ClientError, TimeoutError) as err:
                if attempt == 0:
                    self._authenticated = False
                    await self.authenticate()
                    continue
                raise SeedtimeConnectionError(
                    f"REST connection error: {err}"
                ) from err

        raise SeedtimeConnectionError("REST request failed after retry")

    async def fetch_garden_data(self) -> dict[str, Any]:
        """Fetch complete garden plan data via GraphQL."""
        today = date.today()
        start_date = today.replace(month=1, day=1).isoformat()
        end_date = today.replace(month=12, day=31).isoformat()

        query = GARDEN_PLAN_QUERY.replace("$start_date", start_date).replace(
            "$end_date", end_date
        )

        data = await self.graphql_query(query)

        # Also fetch user info
        user_data = await self.graphql_query("{ me { id email } }")

        return {
            "user": user_data.get("me", {}),
            "garden": data.get("primaryGarden", {}),
        }

    async def fetch_tasks(
        self, target_date: date | None = None, view: str = "month"
    ) -> dict[str, Any]:
        """Fetch tasks from REST API."""
        if target_date is None:
            target_date = date.today()

        params = {"date": target_date.isoformat(), "view": view}
        return await self.rest_get("tasks", params=params)

    async def validate_credentials(self) -> bool:
        """Validate credentials by authenticating and running a test query."""
        await self.authenticate()
        result = await self.graphql_query("{ me { id } }")
        return bool(result.get("me", {}).get("id"))
