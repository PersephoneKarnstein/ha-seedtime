"""Calendar entity for Seedtime planting/harvesting tasks."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TASK_TYPE_LABELS
from .coordinator import SeedtimeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seedtime calendar entity."""
    coordinator: SeedtimeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SeedtimeCalendar(coordinator, entry)])


class SeedtimeCalendar(CoordinatorEntity[SeedtimeDataUpdateCoordinator], CalendarEntity):
    """Calendar entity with planting and harvesting task events."""

    _attr_has_entity_name = True
    _attr_name = "Garden Tasks"

    def __init__(
        self,
        coordinator: SeedtimeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_garden_tasks"
        self._entry = entry

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        events = self._build_events()
        if not events:
            return None

        today = date.today()
        # Find the next event starting from today
        future = [e for e in events if e.start >= today]
        if future:
            future.sort(key=lambda e: e.start)
            return future[0]

        # If no future events, return the most recent
        events.sort(key=lambda e: e.start, reverse=True)
        return events[0]

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events in the given date range."""
        events = self._build_events()
        start_d = start_date.date() if isinstance(start_date, datetime) else start_date
        end_d = end_date.date() if isinstance(end_date, datetime) else end_date

        return [
            e
            for e in events
            if e.end > start_d and e.start < end_d
        ]

    def _build_events(self) -> list[CalendarEvent]:
        """Build calendar events from coordinator data."""
        if not self.coordinator.data:
            return []

        events: list[CalendarEvent] = []
        events.extend(self._events_from_rest_tasks())
        events.extend(self._events_from_crop_schedules())
        return events

    def _events_from_rest_tasks(self) -> list[CalendarEvent]:
        """Build events from REST API task data."""
        tasks_data = self.coordinator.data.get("tasks_rest", {})
        events: list[CalendarEvent] = []

        for category in ("overdue", "todo", "completed"):
            task_list = tasks_data.get(category, [])
            if not isinstance(task_list, list):
                continue

            for task in task_list:
                event = self._task_to_event(task, category)
                if event:
                    events.append(event)

        return events

    def _task_to_event(self, task: dict[str, Any], category: str) -> CalendarEvent | None:
        """Convert a REST task dict to a CalendarEvent."""
        task_type = task.get("task_type", "custom")
        type_label = TASK_TYPE_LABELS.get(task_type, task_type.replace("_", " ").title())

        crop_name = task.get("crop_name", "")
        summary = f"{type_label}: {crop_name}" if crop_name else type_label

        start_str = task.get("start_date")
        end_str = task.get("end_date")

        if not start_str:
            return None

        try:
            start = date.fromisoformat(start_str)
        except (ValueError, TypeError):
            return None

        if end_str:
            try:
                end = date.fromisoformat(end_str)
            except (ValueError, TypeError):
                end = start + timedelta(days=1)
        else:
            end = start + timedelta(days=1)

        # Ensure end is after start for CalendarEvent
        if end <= start:
            end = start + timedelta(days=1)

        # Build description
        desc_parts: list[str] = []
        if category == "overdue":
            desc_parts.append("Status: Overdue")
        elif category == "completed":
            desc_parts.append("Status: Completed")
        else:
            desc_parts.append("Status: To Do")

        if task.get("plant_count"):
            desc_parts.append(f"Plants: {task['plant_count']}")

        locations = task.get("planting_locations")
        if locations and isinstance(locations, list):
            loc_names = [loc.get("name", "") for loc in locations if loc.get("name")]
            if loc_names:
                desc_parts.append(f"Location: {', '.join(loc_names)}")

        if task.get("color"):
            desc_parts.append(f"Color: {task['color']}")

        return CalendarEvent(
            summary=summary,
            start=start,
            end=end,
            description="\n".join(desc_parts),
        )

    def _events_from_crop_schedules(self) -> list[CalendarEvent]:
        """Build milestone events from GraphQL crop schedule data."""
        garden = self.coordinator.data.get("garden", {})
        schedules = (garden.get("cropSchedules") or {}).get("nodes", [])
        events: list[CalendarEvent] = []

        for schedule in schedules:
            if schedule.get("disabled"):
                continue

            garden_crops = (schedule.get("gardenCrops") or {}).get("nodes", [])
            for gc in garden_crops:
                title = gc.get("title", "Unknown Crop")

                # Seeding milestone
                seeding = gc.get("seedingDate")
                if seeding:
                    try:
                        seeding_date = date.fromisoformat(seeding)
                        events.append(
                            CalendarEvent(
                                summary=f"Seeding: {title}",
                                start=seeding_date,
                                end=seeding_date + timedelta(days=1),
                                description=f"Start seeding {title}",
                            )
                        )
                    except (ValueError, TypeError):
                        pass

                # Harvest milestone
                harvesting = gc.get("harvestingDate")
                if harvesting:
                    try:
                        harvest_date = date.fromisoformat(harvesting)
                        events.append(
                            CalendarEvent(
                                summary=f"Harvest: {title}",
                                start=harvest_date,
                                end=harvest_date + timedelta(days=1),
                                description=f"Begin harvesting {title}",
                            )
                        )
                    except (ValueError, TypeError):
                        pass

        return events
