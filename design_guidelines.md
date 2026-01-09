# Trading Bot Interface Design Guidelines

## Design Approach
**Reference-Based**: Drawing from modern trading platforms (Robinhood, Webull, TradingView) combined with Material Design Dark principles for information-dense desktop applications.

## Core Design Principles
1. **Information Hierarchy**: Critical data (price, P&L) most prominent
2. **Glanceable Metrics**: Key stats accessible at a glance
3. **Minimal Distraction**: Reduce visual noise for focus
4. **Data-First**: Charts and numbers over decorative elements

---

## Layout System

### Primary Layout Structure
```
┌─────────────────────────────────────────────┐
│  HEADER (60px) - Account, Status, Settings  │
├──────────┬──────────────────────────────────┤
│          │                                   │
│ SIDEBAR  │     MAIN TRADING AREA            │
│ (240px)  │     (Primary workspace)          │
│          │                                   │
│ Bot List │     Charts + Orders + Positions  │
│ &        │                                   │
│ Controls │                                   │
│          │                                   │
├──────────┴──────────────────────────────────┤
│  FOOTER (40px) - Connection, Logs, Status   │
└─────────────────────────────────────────────┘
```

### Spacing Units
Use consistent 8px base unit: **8, 16, 24, 32px** for padding/margins
- Component spacing: 16px
- Section spacing: 24px
- Major divisions: 32px
- Tight groupings: 8px

---

## Typography

### Font Stack
**Primary**: `"Inter", "Segoe UI", -apple-system, sans-serif`
**Monospace** (for numbers/data): `"JetBrains Mono", "Consolas", monospace`

### Type Scale
- **H1 (Dashboard Title)**: 24px, Semi-Bold (600)
- **H2 (Section Headers)**: 18px, Medium (500)
- **H3 (Card Titles)**: 14px, Medium (500)
- **Body**: 13px, Regular (400)
- **Data/Numbers**: 14px, Mono, Medium (500)
- **Small Labels**: 11px, Regular (400)
- **Tiny Metadata**: 10px, Regular (400)

---

## Component Library

### 1. Header Bar (60px height)
Left: Application logo + Bot name
Center: Active bot status indicator with pulsing dot
Right: Account balance, connection status, settings icon

### 2. Sidebar (240px width)
**Bot Selection Panel**:
- Dropdown for bot strategy selection
- Start/Stop toggle (prominent, 120px wide)
- Configuration button

**Quick Stats Card** (compact):
- Today's P&L (large, colored)
- Win rate percentage
- Total trades count
All in single condensed card with 16px padding

### 3. Main Trading Area (3-panel grid)
**Top Section (40% height)**: 
- Price chart (TradingView-style candlesticks)
- Timeframe selector tabs (1m, 5m, 15m, 1h, 4h)
- Overlay indicators toggle

**Middle Section (35% height)**:
Split into 2 columns (60/40):
- **Left**: Open positions table (Symbol, Entry, Current, P&L, Actions)
- **Right**: Order history list with status badges

**Bottom Section (25% height)**:
Activity log with timestamp, color-coded severity

### 4. Data Tables
- **Row height**: 36px
- **Header**: 11px uppercase, medium weight
- **Zebra striping**: Subtle (5% opacity difference)
- **Hover state**: 10% lighter background
- **Alternating rows**: For better scanning

### 5. Cards & Panels
- **Border radius**: 8px
- **Background**: Elevated surface (lighter than base)
- **Border**: 1px subtle outline
- **Shadow**: Minimal depth (2px blur)
- **Padding**: 16px standard, 24px for spacious cards

### 6. Buttons
- **Primary CTA**: 36px height, 16px horizontal padding, 8px radius
- **Secondary**: Same size, outlined style
- **Icon buttons**: 32px square
- **Start/Stop toggle**: 48px height, distinct color states

### 7. Status Indicators
- **Connection**: Dot (8px) + label in header
- **Bot Running**: Animated pulsing green dot
- **Bot Stopped**: Gray dot
- **Error**: Red dot with warning icon

### 8. Charts Integration
Use TradingView-style charting:
- Dark grid background
- Candlestick default view
- Volume bars below
- Overlays: MA lines, Bollinger bands
- Crosshair on hover

---

## Information Density Strategy

### Priority Levels
**Level 1 (Always Visible)**: Current price, bot status, account balance, P&L
**Level 2 (Glanceable)**: Open positions, pending orders, key metrics
**Level 3 (On-Demand)**: Historical logs, detailed settings, performance analytics

### Data Visualization
- **Positive numbers**: Green with + prefix
- **Negative numbers**: Red with - prefix
- **Percentages**: In parentheses, smaller font
- **Prices**: Always monospace, 2-4 decimal precision
- **Sparklines**: Mini charts for trend indication (40x16px)

---

## Animations
**Minimal and purposeful only**:
- Number changes: Brief highlight flash (200ms)
- Status transitions: Fade (150ms)
- Panel expand/collapse: Smooth slide (250ms)
- NO decorative animations

---

## Desktop-Specific Considerations
- Window minimum size: 1280x720px
- Optimal size: 1440x900px
- Resizable panels with drag handles
- Support system-level dark mode detection
- Keyboard shortcuts for critical actions (Space: Start/Stop, Esc: Close dialogs)