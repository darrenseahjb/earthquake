from __future__ import annotations

BACK_LABEL = "Back"
CANCEL_LABEL = "Cancel ❌"
CONFIRM_LABEL = "Confirm ✅"
SUBSCRIBE_LABEL = "Subscribe"
SUBSCRIBE_ALL_OPTION_LABEL = "To all"
SUBSCRIBE_REGION_OPTION_LABEL = "By region"
LATEST_LABEL = "Latest, all"
LATEST_SUBSCRIBED_LABEL = "Latest subscribed"
STATUS_LABEL = "Status"
UNSUBSCRIBE_LABEL = "Unsubscribe"
TIMEZONE_LABEL = "Edit Timezone"
ADMIN_TEST_LABEL = "Send demo alert"
ADMIN_HEALTH_LABEL = "Health snapshot"
ADMIN_BROADCAST_USAGE = "/broadcast your message here"
SELECTED_PREFIX = "[x] "
TIMEZONE_COUNTRY_PAGE_SIZE = 8
TIMEZONE_ZONE_PAGE_SIZE = 8

CONTINENT_COUNTRIES: dict[str, list[str]] = {
    "Asia": ["Japan", "Indonesia", "Philippines", "Taiwan", "Nepal", "Turkey"],
    "Europe": ["Greece", "Italy", "Iceland", "Romania", "Turkey", "Portugal"],
    "North America": ["Alaska", "California", "Mexico", "Guatemala", "Costa Rica", "Puerto Rico"],
    "South America": ["Chile", "Peru", "Ecuador", "Colombia", "Argentina", "Bolivia"],
    "Oceania": ["New Zealand", "Papua New Guinea", "Fiji", "Tonga", "Vanuatu", "Solomon Islands"],
    "Africa": ["Morocco", "Algeria", "Ethiopia", "Tanzania", "Uganda", "Kenya"],
}

REGION_FLAGS: dict[str, str] = {
    "Japan": "🇯🇵",
    "Indonesia": "🇮🇩",
    "Philippines": "🇵🇭",
    "Taiwan": "🇹🇼",
    "Nepal": "🇳🇵",
    "Turkey": "🇹🇷",
    "Greece": "🇬🇷",
    "Italy": "🇮🇹",
    "Iceland": "🇮🇸",
    "Romania": "🇷🇴",
    "Portugal": "🇵🇹",
    "Alaska": "🇺🇸",
    "California": "🇺🇸",
    "Mexico": "🇲🇽",
    "Guatemala": "🇬🇹",
    "Costa Rica": "🇨🇷",
    "Puerto Rico": "🇵🇷",
    "Chile": "🇨🇱",
    "Peru": "🇵🇪",
    "Ecuador": "🇪🇨",
    "Colombia": "🇨🇴",
    "Argentina": "🇦🇷",
    "Bolivia": "🇧🇴",
    "New Zealand": "🇳🇿",
    "Papua New Guinea": "🇵🇬",
    "Fiji": "🇫🇯",
    "Tonga": "🇹🇴",
    "Vanuatu": "🇻🇺",
    "Solomon Islands": "🇸🇧",
    "Morocco": "🇲🇦",
    "Algeria": "🇩🇿",
    "Ethiopia": "🇪🇹",
    "Tanzania": "🇹🇿",
    "Uganda": "🇺🇬",
    "Kenya": "🇰🇪",
}
