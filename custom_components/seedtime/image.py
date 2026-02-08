"""Image entity for Seedtime garden plan."""

from __future__ import annotations

import hashlib
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTR_CROP_COUNT, ATTR_GARDEN_TITLE, ATTR_LOCATION_COUNT, ATTR_PLAN_HEIGHT, ATTR_PLAN_WIDTH, DOMAIN
from .coordinator import SeedtimeDataUpdateCoordinator
from .garden_renderer import render_garden_svg

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seedtime garden image entity."""
    coordinator: SeedtimeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SeedtimeGardenImage(coordinator, entry)])


class SeedtimeGardenImage(CoordinatorEntity[SeedtimeDataUpdateCoordinator], ImageEntity):
    """Image entity serving the garden plan as SVG."""

    _attr_content_type = "image/svg+xml"
    _attr_has_entity_name = True
    _attr_name = "Garden Plan"

    def __init__(
        self,
        coordinator: SeedtimeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{entry.entry_id}_garden_plan"
        self._entry = entry
        self._cached_svg: bytes | None = None
        self._cached_hash: str | None = None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Return extra attributes about the garden plan."""
        garden = self.coordinator.data.get("garden", {}) if self.coordinator.data else {}
        plan = garden.get("gardenPlan") or {}
        locations = (plan.get("plantingLocations") or {}).get("nodes", [])

        # Count unique crops
        crop_titles: set[str] = set()
        for loc in locations:
            for f in (loc.get("plantingFormations") or {}).get("nodes", []):
                gc = f.get("gardenCrop")
                if gc and gc.get("title"):
                    crop_titles.add(gc["title"])

        return {
            ATTR_GARDEN_TITLE: garden.get("title"),
            ATTR_PLAN_WIDTH: plan.get("width"),
            ATTR_PLAN_HEIGHT: plan.get("height"),
            ATTR_LOCATION_COUNT: len(locations),
            ATTR_CROP_COUNT: len(crop_titles),
        }

    async def async_image(self) -> bytes | None:
        """Return the garden plan SVG image bytes."""
        if not self.coordinator.data:
            return None

        garden = self.coordinator.data.get("garden", {})
        if not garden.get("gardenPlan"):
            return None

        # Hash the plan data to avoid unnecessary re-renders
        plan_str = str(garden.get("gardenPlan"))
        plan_hash = hashlib.md5(plan_str.encode()).hexdigest()

        if plan_hash != self._cached_hash:
            svg = await self.hass.async_add_executor_job(
                render_garden_svg, garden
            )
            self._cached_svg = svg.encode("utf-8")
            self._cached_hash = plan_hash
            self._attr_image_last_updated = dt_util.utcnow()

        return self._cached_svg
