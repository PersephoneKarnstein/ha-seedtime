/**
 * Seedtime Garden Card — Interactive Lovelace card for Seedtime garden plan.
 *
 * Renders the garden plan SVG as live DOM (not <img>) so we can attach
 * hover/click listeners to [data-crop] elements for interactive tooltips.
 * Includes a timeline slider to scrub through past/future dates.
 */

const CARD_VERSION = "0.3.2";

class SeedtimeGardenCard extends HTMLElement {
  static get properties() {
    return {
      hass: {},
      config: {},
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialize();
    }
    this._updateImage();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity");
    }
    this._config = config;
    this._lastImageUrl = null;
  }

  _initialize() {
    if (this._initialized) return;
    this._initialized = true;

    // Create shadow DOM
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .card {
          position: relative;
          overflow: hidden;
          border-radius: var(--ha-card-border-radius, 12px);
          background: var(--ha-card-background, var(--card-background-color, white));
          box-shadow: var(--ha-card-box-shadow, none);
        }
        .header {
          padding: 12px 16px 4px;
          font-size: 1.1em;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .garden-container {
          padding: 8px;
          display: flex;
          justify-content: center;
        }
        .garden-container svg {
          max-width: 100%;
          height: auto;
          border-radius: 8px;
        }
        /* Timeline slider controls */
        .timeline-controls {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 16px 12px;
        }
        .timeline-slider {
          flex: 1;
          height: 4px;
          accent-color: #6b8e23;
          cursor: pointer;
        }
        .timeline-btn {
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--primary-text-color);
          --mdc-icon-size: 24px;
        }
        .timeline-btn:hover {
          opacity: 0.7;
        }
        .timeline-today {
          background: none;
          border: 1px solid #6b8e23;
          border-radius: 4px;
          padding: 2px 8px;
          cursor: pointer;
          font-size: 11px;
          color: #6b8e23;
          white-space: nowrap;
          flex-shrink: 0;
        }
        .timeline-today:hover {
          background: #6b8e231a;
        }
        .timeline-date {
          font-size: 12px;
          color: var(--primary-text-color);
          min-width: 110px;
          text-align: center;
          white-space: nowrap;
          flex-shrink: 0;
        }
        /* Tooltip */
        .tooltip {
          display: none;
          position: absolute;
          background: white;
          border: 1px solid #e0e0e0;
          border-radius: 8px;
          padding: 10px 14px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.15);
          font-size: 13px;
          line-height: 1.5;
          z-index: 100;
          pointer-events: none;
          max-width: 250px;
          color: #212121;
        }
        .tooltip.visible {
          display: block;
        }
        .tooltip .crop-name {
          font-weight: 600;
          font-size: 14px;
          margin-bottom: 4px;
        }
        .tooltip .crop-detail {
          color: #616161;
        }
        .tooltip .color-dot {
          display: inline-block;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          margin-right: 6px;
          vertical-align: middle;
        }
        .no-data {
          padding: 32px;
          text-align: center;
          color: var(--secondary-text-color);
        }
        /* Highlight planting location on hover */
        .garden-container .planting-location:hover > path:first-of-type {
          stroke: #333;
          stroke-width: 2;
          filter: brightness(1.1);
        }
        /* Highlight individual crop formation on hover */
        .garden-container .tooltip-target:hover > path:first-of-type {
          filter: brightness(1.15);
          stroke: #333;
          stroke-width: 1;
        }
        .garden-container .tooltip-target {
          cursor: pointer;
        }
      </style>
      <ha-card>
        <div class="card">
          <div class="header"></div>
          <div class="garden-container"></div>
          <div class="timeline-controls">
            <button class="timeline-btn" id="prev-day"><ha-icon icon="mdi:arrow-left-circle"></ha-icon></button>
            <input type="range" class="timeline-slider" id="date-slider" min="0" max="1" value="0">
            <button class="timeline-btn" id="next-day"><ha-icon icon="mdi:arrow-right-circle"></ha-icon></button>
            <span class="timeline-date" id="date-label"></span>
            <button class="timeline-today" id="today-btn">Today</button>
          </div>
          <div class="tooltip">
            <div class="crop-name"></div>
            <div class="crop-detail"></div>
          </div>
        </div>
      </ha-card>
    `;

    this._container = this.shadowRoot.querySelector(".garden-container");
    this._tooltip = this.shadowRoot.querySelector(".tooltip");
    this._header = this.shadowRoot.querySelector(".header");
    this._slider = this.shadowRoot.querySelector("#date-slider");
    this._dateLabel = this.shadowRoot.querySelector("#date-label");

    // Timeline event listeners
    this._slider.addEventListener("input", () => this._onSliderChange());
    this.shadowRoot.querySelector("#prev-day").addEventListener("click", () => this._stepDay(-1));
    this.shadowRoot.querySelector("#next-day").addEventListener("click", () => this._stepDay(1));
    this.shadowRoot.querySelector("#today-btn").addEventListener("click", () => this._goToToday());
  }

  async _updateImage() {
    if (!this._hass || !this._config) return;

    const entity = this._hass.states[this._config.entity];
    if (!entity) {
      this._container.innerHTML =
        '<div class="no-data">Entity not found</div>';
      return;
    }

    // Update header
    const title =
      this._config.title ||
      entity.attributes.garden_title ||
      "Garden Plan";
    this._header.textContent = title;

    // entity_picture already includes ?token= param
    const imageUrl = entity.attributes.entity_picture;
    if (imageUrl && imageUrl !== this._lastImageUrl) {
      this._lastImageUrl = imageUrl;
      await this._loadSvg(imageUrl);
    }
  }

  async _loadSvg(url) {
    try {
      const resp = await fetch(url, { credentials: "same-origin" });
      if (!resp.ok) {
        this._container.innerHTML =
          '<div class="no-data">Failed to load garden plan</div>';
        return;
      }

      const svgText = await resp.text();

      // Inject SVG as live DOM
      this._container.innerHTML = svgText;

      // Attach hover listeners to planting locations
      this._attachTooltipListeners();

      // Initialize the timeline slider from formation date attributes
      this._initTimeline();
    } catch (err) {
      console.error("Seedtime: Failed to load SVG", err);
      this._container.innerHTML =
        '<div class="no-data">Error loading garden plan</div>';
    }
  }

  // ── Timeline slider ──────────────────────────────────────────

  _initTimeline() {
    const timelineEl = this.shadowRoot.querySelector(".timeline-controls");
    const formations = this._container.querySelectorAll("[data-ground-start]");
    if (!formations.length) {
      if (timelineEl) timelineEl.style.display = "none";
      return;
    }
    if (timelineEl) timelineEl.style.display = "";

    let minMs = Infinity;
    let maxMs = -Infinity;

    formations.forEach((el) => {
      const s = el.dataset.groundStart;
      const e = el.dataset.groundEnd;
      if (s) {
        const ms = new Date(s + "T00:00:00").getTime();
        if (ms < minMs) minMs = ms;
      }
      if (e) {
        const ms = new Date(e + "T00:00:00").getTime();
        if (ms > maxMs) maxMs = ms;
      }
    });

    if (!isFinite(minMs) || !isFinite(maxMs)) return;

    const DAY_MS = 86400000;
    this._timelineMinMs = minMs;
    this._timelineMaxMs = maxMs;

    const totalDays = Math.round((maxMs - minMs) / DAY_MS);
    this._slider.min = 0;
    this._slider.max = totalDays;

    // Default to today (local time), clamped within range
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const todayMs = new Date(todayStr + "T00:00:00").getTime();
    const todayDay = Math.round((todayMs - minMs) / DAY_MS);
    this._todayDay = Math.max(0, Math.min(totalDays, todayDay));
    this._slider.value = this._todayDay;

    this._applyDateFromSlider();
  }

  _sliderToIso(val) {
    const DAY_MS = 86400000;
    const ms = this._timelineMinMs + val * DAY_MS;
    const d = new Date(ms);
    // Use local date components to avoid UTC timezone shift
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  _applyDateFromSlider() {
    const iso = this._sliderToIso(Number(this._slider.value));
    this._applyDateFilter(iso);
    this._updateDateLabel(iso);
  }

  _applyDateFilter(isoDateStr) {
    const sel = new Date(isoDateStr + "T00:00:00").getTime();
    this._container.querySelectorAll("[data-ground-start]").forEach((el) => {
      const startStr = el.dataset.groundStart;
      const endStr = el.dataset.groundEnd;
      if (!startStr || !endStr) {
        el.style.display = "";
        return;
      }
      const start = new Date(startStr + "T00:00:00").getTime();
      const end = new Date(endStr + "T00:00:00").getTime();
      el.style.display = (sel >= start && sel <= end) ? "" : "none";
    });
  }

  _updateDateLabel(isoDateStr) {
    const d = new Date(isoDateStr + "T12:00:00");
    const opts = { month: "short", day: "numeric", year: "numeric" };
    this._dateLabel.textContent = d.toLocaleDateString("en-US", opts);
  }

  _onSliderChange() {
    this._applyDateFromSlider();
  }

  _stepDay(delta) {
    const val = Number(this._slider.value) + delta;
    const clamped = Math.max(Number(this._slider.min), Math.min(Number(this._slider.max), val));
    this._slider.value = clamped;
    this._applyDateFromSlider();
  }

  _goToToday() {
    if (this._todayDay !== undefined) {
      this._slider.value = this._todayDay;
      this._applyDateFromSlider();
    }
  }

  // ── Tooltips ─────────────────────────────────────────────────

  _attachTooltipListeners() {
    const targets = this._container.querySelectorAll("[data-crop]");
    targets.forEach((el) => {
      el.addEventListener("mouseenter", (e) => this._showTooltip(e, el));
      el.addEventListener("mousemove", (e) => this._positionTooltip(e));
      el.addEventListener("mouseleave", () => this._hideTooltip());

      // Touch support
      el.addEventListener("touchstart", (e) => {
        e.preventDefault();
        this._showTooltip(e, el);
        this._positionTooltip(e.touches[0]);
      });
    });

    // Hide tooltip on touch outside
    this._container.addEventListener("touchstart", (e) => {
      if (!e.target.closest("[data-crop]")) {
        this._hideTooltip();
      }
    });
  }

  _showTooltip(event, el) {
    const crop = el.dataset.crop || "Unknown";
    const seeding = el.dataset.seeding || "";
    const harvest = el.dataset.harvest || "";
    const plants = el.dataset.plants || "";
    const color = el.dataset.color || "#6b8e23";

    const nameEl = this._tooltip.querySelector(".crop-name");
    const detailEl = this._tooltip.querySelector(".crop-detail");

    nameEl.innerHTML = `<span class="color-dot" style="background:${color}"></span>${this._escHtml(crop)}`;

    const details = [];
    if (seeding) details.push(`Seeding: ${this._escHtml(seeding)}`);
    if (harvest) details.push(`Harvest: ${this._escHtml(harvest)}`);
    if (plants && plants !== "0")
      details.push(`Plants: ${this._escHtml(plants)}`);

    detailEl.innerHTML = details
      .map((d) => `<div class="crop-detail">${d}</div>`)
      .join("");

    this._tooltip.classList.add("visible");
  }

  _positionTooltip(event) {
    const cardRect = this.shadowRoot
      .querySelector(".card")
      .getBoundingClientRect();
    const x = (event.clientX || event.pageX) - cardRect.left + 12;
    const y = (event.clientY || event.pageY) - cardRect.top + 12;

    this._tooltip.style.left = `${x}px`;
    this._tooltip.style.top = `${y}px`;
  }

  _hideTooltip() {
    this._tooltip.classList.remove("visible");
  }

  _escHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  getCardSize() {
    return 5;
  }

  static getConfigElement() {
    return document.createElement("seedtime-garden-card-editor");
  }

  static getStubConfig() {
    return { entity: "" };
  }
}

/**
 * Card editor for entity selection.
 */
class SeedtimeGardenCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) this._initialize();
  }

  setConfig(config) {
    this._config = { ...config };
    if (this._entityInput) {
      this._entityInput.value = config.entity || "";
    }
  }

  _initialize() {
    this._initialized = true;
    this.innerHTML = `
      <div style="padding: 16px;">
        <label style="display:block; margin-bottom:4px; font-weight:500;">Entity</label>
        <input type="text" id="entity" style="width:100%; padding:8px; box-sizing:border-box; border:1px solid #ccc; border-radius:4px;"
          placeholder="image.seedtime_garden_plan" />
        <p style="margin-top:8px; font-size:12px; color:#888;">
          Select the Seedtime garden plan image entity.
        </p>
        <label style="display:block; margin-top:16px; margin-bottom:4px; font-weight:500;">Title (optional)</label>
        <input type="text" id="title" style="width:100%; padding:8px; box-sizing:border-box; border:1px solid #ccc; border-radius:4px;"
          placeholder="My Garden" />
      </div>
    `;

    this._entityInput = this.querySelector("#entity");
    this._titleInput = this.querySelector("#title");

    if (this._config) {
      this._entityInput.value = this._config.entity || "";
      this._titleInput.value = this._config.title || "";
    }

    this._entityInput.addEventListener("input", () => this._fireChanged());
    this._titleInput.addEventListener("input", () => this._fireChanged());
  }

  _fireChanged() {
    const config = {
      ...this._config,
      entity: this._entityInput.value,
      title: this._titleInput.value || undefined,
    };
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config } })
    );
  }
}

// Register components
customElements.define("seedtime-garden-card", SeedtimeGardenCard);
customElements.define("seedtime-garden-card-editor", SeedtimeGardenCardEditor);

// Register with Home Assistant custom card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "seedtime-garden-card",
  name: "Seedtime Garden Plan",
  description: "Interactive garden plan with crop tooltips",
  preview: true,
  documentationURL:
    "https://github.com/PersephoneKarnstein/Seedtime-API",
});

console.info(
  `%c SEEDTIME-GARDEN-CARD %c v${CARD_VERSION} `,
  "color: white; background: #6b8e23; font-weight: bold; padding: 2px 6px; border-radius: 3px 0 0 3px;",
  "color: #6b8e23; background: #f5f0e8; font-weight: bold; padding: 2px 6px; border-radius: 0 3px 3px 0;"
);
