"""Chat-widget look in the agent's teal palette: gradient header with avatar and online status,
bot/customer bubbles, pill quick replies, rating row, rounded input, history and trends sidebar.

Only CSS. Elements are targeted through the ``st-key-<key>`` classes Streamlit adds to keyed
containers and widgets, so the styling does not depend on Streamlit's internal markup (chat
bubbles use the avatar test ids Streamlit renders inside each message).
"""

from __future__ import annotations

ACCENT = "#0F766E"  # teal: agent identity
ACCENT_2 = "#0D9488"  # lighter teal for gradients
ACCENT_SOFT = "#E6F4F1"
INK = "#1F2933"
MUTED = "#5F6B76"
LINE = "#DDE3E8"
CARD = "#FFFFFF"
PAGE = "#F6F8FA"
BOT_BUBBLE = "#EEF2F4"

CSS = f"""
<style>
.stApp {{ background: {PAGE}; }}
/* main column and the pinned input share the same width and gutters (no misalignment) */
[data-testid="stMainBlockContainer"], [data-testid="stBottomBlockContainer"] {{
  max-width: 980px; padding-left: 1.5rem; padding-right: 1.5rem;
}}
[data-testid="stMainBlockContainer"] {{ padding-top: 1rem; padding-bottom: 6rem; }}

/* ---- widget header: avatar, name, status, settings, minimize ---- */
/* Streamlit's own top bar: transparent and click-through (only its buttons react), so it
   never paints a band over the conversation; the widget header below is the real top bar. */
header[data-testid="stHeader"] {{ background: transparent; pointer-events: none; }}
header[data-testid="stHeader"] button, header[data-testid="stHeader"] a {{ pointer-events: auto; }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stExpandSidebarButton"] {{ color: #fff; }}

/* The widget header sticks to the top; messages scroll underneath it. The opaque page-colored
   box keeps text from showing through the curved corners; the teal shape is drawn by ::before. */
[data-testid="stLayoutWrapper"]:has(> .st-key-widget-head) {{
  position: sticky; top: 0; z-index: 50; background: {PAGE};
}}
.st-key-widget-head {{
  position: relative; isolation: isolate;
  background: {PAGE}; padding: 16px 18px 22px 18px; color: #fff; margin-bottom: 10px;
}}
.st-key-widget-head::before {{
  content: ""; position: absolute; inset: 0; z-index: -1;
  background: linear-gradient(120deg, {ACCENT} 0%, {ACCENT_2} 100%);
  border-radius: 18px 18px 50% 50% / 18px 18px 28px 28px;  /* curved bottom edge */
  box-shadow: 0 6px 14px rgba(15, 118, 110, .18);
}}
/* sidebar closed: Streamlit's » button floats at the top-left, over the header; make room */
.stApp:has([data-testid="stExpandSidebarButton"]) .st-key-widget-head {{ padding-left: 64px; }}
.st-key-widget-head a, .st-key-widget-head div {{ text-decoration: none; }}
.head-id {{ display: flex; gap: 12px; align-items: center; }}
.head-id small {{ opacity: .85; font-size: 12px; }}
.head-id b {{ font-size: 19px; }}
.avatar {{
  width: 44px; height: 44px; border-radius: 50%; background: #fff; color: {ACCENT};
  display: flex; align-items: center; justify-content: center; font-weight: 800;
  box-shadow: 0 0 0 3px rgba(255,255,255,.35);
}}
.head-status {{ font-size: 13px; opacity: .92; margin: 10px 0 4px 14px; }}  /* clear of the curve */
.head-status .dot {{
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #5EEAD4;
  margin-right: 6px; box-shadow: 0 0 0 3px rgba(94,234,212,.25);
}}
.st-key-widget-head button {{
  background: transparent; border: none; color: #fff; box-shadow: none;
}}
.st-key-widget-head button:hover {{ background: rgba(255,255,255,.15); color: #fff; }}

/* ---- settings popover content ---- */
.tool {{
  border-left: 3px solid {ACCENT}; background: {CARD}; padding: 6px 10px; margin: 6px 0;
  border-radius: 0 6px 6px 0; font-size: 13px; line-height: 1.35;
}}
.tool b {{ display: block; color: {INK}; }}
.tool span {{ color: {MUTED}; word-break: break-word; }}

/* ---- bubbles: bot left (grey), customer right (teal) ---- */
[data-testid="stChatMessage"] {{ background: transparent; padding: 4px 0; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
  [data-testid="stChatMessageContent"] {{
  background: {BOT_BUBBLE}; border-radius: 4px 16px 16px 16px; padding: 10px 14px;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
  flex-direction: row-reverse; justify-content: flex-start;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
  [data-testid="stChatMessageContent"] {{
  background: linear-gradient(120deg, {ACCENT} 0%, {ACCENT_2} 100%); color: #fff;
  border-radius: 16px 4px 16px 16px; padding: 10px 14px; flex: 0 1 auto; max-width: 75%;
  width: auto; margin: 0 0 0 auto !important;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
  [data-testid="stChatMessageContent"] * {{ color: #fff !important; }}
[data-testid="stChatMessageAvatarAssistant"] {{ background: {ACCENT}; color: #fff; }}
[data-testid="stChatMessageAvatarUser"] {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}

/* ---- quick replies: outlined pills (horizontal containers wrap on their own) ---- */
[class*="st-key-quick-"] button {{
  border: 1.5px solid {ACCENT}; color: {ACCENT}; background: #fff; border-radius: 999px;
  padding: 4px 14px; min-height: 34px; white-space: nowrap;
}}
[class*="st-key-part-"] button {{
  border: 1.5px solid {ACCENT}; color: {ACCENT}; background: #fff; border-radius: 10px;
  padding: 2px 6px; min-height: 30px;
}}
[class*="st-key-part-"] button p {{
  font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
[class*="st-key-quick-"] button:hover, [class*="st-key-part-"] button:hover {{
  background: {ACCENT}; color: #fff; border-color: {ACCENT};
}}

/* ---- reasoning timeline ---- */
ol.steps {{ list-style: none; padding-left: 0; margin: 0; }}
ol.steps li {{
  position: relative; padding: 4px 0 8px 22px; border-left: 2px solid {LINE}; margin-left: 6px;
}}
ol.steps li::before {{
  content: ""; position: absolute; left: -6px; top: 8px; width: 10px; height: 10px;
  border-radius: 50%; background: {ACCENT};
}}
.step-key {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
  background: {ACCENT_SOFT}; color: {ACCENT}; padding: 1px 6px; border-radius: 4px;
}}
.step-detail {{ color: {MUTED}; font-size: 13px; margin-top: 2px; }}

/* ---- result cards inside the chat ---- */
[class*="st-key-card-"] {{
  background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; padding: 12px 14px;
}}
[class*="st-key-card-"] h3 {{ font-size: 17px; padding: 0; color: {INK}; }}
/* image column keeps a fixed width so photo credits never collapse letter by letter */
[class*="st-key-card-"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {{
  flex: 0 0 120px !important; min-width: 120px; max-width: 120px;
}}
.facts {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 4px 0; }}
.facts span {{
  background: {ACCENT_SOFT}; border-radius: 8px; padding: 4px 10px; line-height: 1.25;
}}
.facts small {{ display: block; font-size: 10px; color: {MUTED}; text-transform: uppercase; }}
.facts b {{ font-size: 13px; color: {INK}; white-space: nowrap; }}

/* ---- rating row ---- */
[class*="st-key-rating-"] {{ border-top: 1px solid {LINE}; padding-top: 6px; margin-top: 4px; }}

/* ---- input: rounded pill with teal send button ---- */
/* Streamlit paints its own border (radius 8px) on the inner wrapper and turns it teal on
   focus; its corners poked out of our pill. Only the inner wrapper draws the border now. */
[data-testid="stChatInput"] {{ border: none; border-radius: 999px; }}
[data-testid="stChatInput"] > div {{
  border-radius: 999px; border: 1.5px solid {LINE}; outline: none; box-shadow: none;
}}
[data-testid="stChatInput"]:focus-within > div {{ border-color: {ACCENT}; }}
[data-testid="stChatInputSubmitButton"] {{
  background: {ACCENT}; color: #fff; border-radius: 50%;
}}

/* ---- product images ---- */
.pimg {{ background: #fff; border-radius: 6px; }}
.pimg img {{
  width: 100%; height: auto; max-height: 140px; object-fit: contain; display: block; margin: 0 auto;
}}
.pimg-mini img {{ max-height: 70px; }}
.pimg-note {{
  font-size: 10px; color: {MUTED}; text-align: center; line-height: 1.3; margin-top: 3px;
}}
.pimg-note a {{ color: {MUTED}; text-decoration: underline; }}
.pimg-mini .pimg-note {{ display: none; }}
[class*="st-key-part-"] {{
  background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 8px 6px;
  text-align: center; gap: 8px;
}}
/* no negative markdown margins inside tiles: image, badge and button stack without touching */
[class*="st-key-part-"] [data-testid="stMarkdownContainer"],
[class*="st-key-part-"] [data-testid="stMarkdownContainer"] p {{
  margin: 0 !important; font-size: 11px; line-height: 1.4;
}}
[class*="st-key-part-"] [data-testid="stElementContainer"] {{ margin: 0 !important; }}

.st-key-tts {{ position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; }}

/* ---- sidebar: history and trends ---- */
[data-testid="stSidebar"] {{ background: {CARD}; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .55rem; }}
[data-testid="stSidebar"] h3 {{ padding: 0; line-height: 1.3; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ margin: 0; line-height: 1.35; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
[data-testid="stSidebar"] button[kind="tertiary"] {{
  color: {INK}; text-align: left; justify-content: flex-start; padding: 0; min-height: 0;
}}
[data-testid="stSidebar"] button[kind="tertiary"]:hover {{ color: {ACCENT}; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
  font-size: 12px; line-height: 1.4;
}}
/* section title: name plus a one-line explanation, separated by a rule */
.hist-head {{ border-top: 1px solid {LINE}; padding-top: 12px; margin-top: 4px; }}
.hist-head b {{ display: block; font-size: 14px; color: {INK}; }}
.hist-head span {{ display: block; font-size: 12px; color: {MUTED}; line-height: 1.35; }}
/* one entry = a compact stack (button + details); entries are separated by the block gap */
[data-testid="stSidebar"] [class*="st-key-hist-"] {{ gap: 3px; padding-bottom: 4px; }}
[class*="st-key-hist-trend-"] button p {{ font-weight: 600; letter-spacing: .01em; }}
[class*="st-key-hist-recent-"] button p {{
  font-size: 14px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; text-overflow: ellipsis;
}}
.chip {{
  display: inline-block; font-size: 10px; font-weight: 600; letter-spacing: .02em;
  padding: 0 6px; border-radius: 999px; line-height: 16px; white-space: nowrap;
}}
.chip.bad {{ background: #FEE4E2; color: #B42318; }}
.chip.warn {{ background: #FEF0C7; color: #B54708; }}
.chip.ok {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
.trend {{ font-size: 12px; color: {MUTED}; line-height: 1.4; }}
.trend-bar {{
  height: 6px; border-radius: 3px; background: {LINE}; margin: 4px 0; overflow: hidden;
}}
.trend-bar div {{ height: 100%; border-radius: 3px; background: {ACCENT}; }}
.trend-count {{
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 2px 8px;
}}
.trend-count b {{
  font-size: 11px; font-weight: 600; padding: 0 7px; border-radius: 999px; line-height: 17px;
  cursor: help; white-space: nowrap;
}}
.trend-count b.new, .trend-count b.up {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
.trend-count b.down, .trend-count b.flat {{ background: {PAGE}; color: {MUTED}; }}
.recent-meta {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 2px 10px; font-size: 12px;
  color: {MUTED}; line-height: 1.4;
}}
.outcome {{ white-space: nowrap; }}
.outcome::before {{
  content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  margin-right: 5px; background: {MUTED}; vertical-align: 1px;
}}
.outcome.recommended {{ color: {ACCENT}; }}
.outcome.recommended::before {{ background: {ACCENT}; }}
.outcome.risky {{ color: #B54708; }}
.outcome.risky::before {{ background: #B54708; }}
.outcome.none {{ color: #B42318; }}
.outcome.none::before {{ background: #B42318; }}
.outcome.clarify::before {{ background: transparent; box-shadow: inset 0 0 0 1.5px {MUTED}; }}
[data-testid="stSidebar"] .st-key-history-menu button {{ color: {MUTED}; padding: 2px 6px 2px 0; }}

@media (max-width: 640px) {{
  .pimg img {{ max-height: 110px; }}
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stChatMessageContent"] {{ max-width: 90%; }}
}}
</style>
"""
