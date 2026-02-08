"""Constants for the Seedtime integration."""

DOMAIN = "seedtime"

# API URLs
BASE_URL = "https://app.seedtime.us"
SIGN_IN_URL = f"{BASE_URL}/users/sign_in"
REST_API_URL = f"{BASE_URL}/api"

# Config keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ENABLE_CALENDAR = "enable_calendar"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL = 1800  # 30 minutes
DEFAULT_ENABLE_CALENDAR = True
MIN_SCAN_INTERVAL = 300  # 5 minutes
MAX_SCAN_INTERVAL = 7200  # 2 hours

# Attribute keys
ATTR_GARDEN_TITLE = "garden_title"
ATTR_PLAN_WIDTH = "plan_width"
ATTR_PLAN_HEIGHT = "plan_height"
ATTR_LOCATION_COUNT = "location_count"
ATTR_CROP_COUNT = "crop_count"

# Task type display labels
TASK_TYPE_LABELS = {
    "direct_seeding": "Direct Seeding",
    "indoor_seeding": "Indoor Seeding",
    "bed_preparation": "Bed Preparation",
    "transplanting": "Transplanting",
    "harvesting": "Harvesting",
    "stale_seed_bed": "Stale Seed Bed",
    "cultivating": "Cultivating",
    "custom": "Custom Task",
}

# Platforms
PLATFORMS = ["image", "calendar"]
