# Trading Bot Dashboard Design Guidelines

## Design Approach
**Material Design System** optimized for dark mode data visualization. Reference: Bloomberg Terminal's information density + Robinhood's clean aesthetics + Linear's modern polish.

## Core Design Principles
- Information first: Every pixel serves trader decision-making
- Scannable hierarchy: Critical metrics immediately visible
- Real-time clarity: Live data updates without cognitive overload
- Professional restraint: Minimal decorative elements

## Typography
- **Primary Font**: Inter (via Google Fonts CDN)
- **Monospace**: JetBrains Mono for numbers, metrics, prices
- **Hierarchy**:
  - Dashboard title: text-2xl font-semibold
  - Section headers: text-lg font-medium
  - Metrics/values: text-3xl font-mono font-bold (for large numbers)
  - Labels: text-sm font-medium uppercase tracking-wide
  - Body/secondary: text-sm
  - Small data: text-xs font-mono

## Layout System
**Spacing Units**: Tailwind 2, 4, 6, 8 (p-4, gap-6, m-8)
- Consistent 6-unit (24px) gaps between dashboard panels
- 4-unit internal padding for cards/panels
- 8-unit margins for major sections

## Page Structure

### 1. Top Navigation Bar (Sticky)
- Logo left, AI Strategy Generator button (primary action), account/settings right
- Height: h-16, backdrop blur with subtle border-b
- Include connection status indicator (WebSocket live icon)

### 2. Dashboard Grid Layout
Three-column responsive grid (grid-cols-1 lg:grid-cols-3, gap-6):

**Left Column (lg:col-span-2):**
- **Performance Overview Panel**: Large chart showing portfolio value over time with timeframe toggles (1H, 24H, 7D, 30D, ALL)
- **Active Strategies Table**: Sortable table with columns: Strategy Name, Status (live badge), PnL, Win Rate, Actions (pause/stop icons)
- **Recent Trades Feed**: Scrollable list with buy/sell indicators, timestamps, amounts

**Right Column (lg:col-span-1):**
- **Key Metrics Cards** (stacked):
  - Total Portfolio Value (large monospace number)
  - 24h PnL (with percentage, green/red indicator)
  - Active Bots count
  - Win Rate percentage
- **Quick Actions Panel**: Start New Bot, Deploy AI Strategy buttons
- **Market Sentiment Widget**: Compact AI-generated insights with confidence score

### 3. AI Strategy Generator Modal (Overlay)
- Full-screen overlay (md:max-w-4xl centered)
- Multi-step form: Market Selection → Risk Parameters → AI Analysis → Deploy
- Real-time AI suggestion preview on right side
- Progress indicator at top

### 4. Real-Time Control Strip (Bottom Docked)
- Fixed bottom bar with emergency controls
- "Stop All Bots" (destructive), "Pause Trading", current system status
- Height: h-14

## Component Library

### Data Cards/Panels
- Rounded corners: rounded-xl
- Border: border with subtle glow on active states
- Padding: p-6
- Backdrop blur for depth on overlays

### Charts
- Use Chart.js or Recharts via CDN
- Grid lines: minimal, subtle
- Tooltips: Large readable values with context
- Color scheme: Green (profit), Red (loss), Blue (neutral/info)

### Tables
- Zebra striping for row readability
- Sticky headers on scroll
- Sortable columns with arrow indicators
- Row hover states with subtle highlight
- Monospace for all numerical columns

### Badges/Status Indicators
- Pill-shaped: rounded-full px-3 py-1
- Size: text-xs font-medium uppercase
- Types: Live (pulsing green dot), Paused (amber), Stopped (gray), Profitable (green bg)

### Buttons
- Primary (AI actions): Prominent, medium size
- Secondary (controls): Outlined style
- Destructive (stop/pause): Red accent
- Icon buttons: w-8 h-8 for table actions
- Glass morphism effect for buttons over charts/images

### Form Inputs
- Outlined style with focus states
- Labels: Always above, text-sm font-medium
- Number inputs: Monospace font
- Sliders for risk parameters with value display

## Icons
**Heroicons** (via CDN) - outline style for UI, solid for status/alerts
- Key icons: ChartBarIcon, BoltIcon, CpuChipIcon, PlayIcon, PauseIcon, StopIcon, CogIcon

## Animations
**Minimal, purposeful only:**
- Live data pulse on connection status
- Smooth transitions for panel expansion (duration-200)
- Number counter animation for large metric changes
- No scroll animations or decorative effects

## Images
**No hero image needed** - this is a functional dashboard prioritizing immediate data access. Optionally include:
- Logo/brand mark in top nav (small, 32x32px)
- Empty state illustrations for "No Active Strategies" scenarios
- AI avatar/icon for strategy generator feature

## Accessibility
- High contrast ratios for dark mode text
- Focus indicators on all interactive elements
- ARIA labels for icon-only buttons
- Keyboard shortcuts for critical actions (document in help panel)

---

**Final Polish**: Professional trader aesthetic - think "mission control" not "gaming setup". Every element earns its place through utility. Data clarity trumps visual flair.