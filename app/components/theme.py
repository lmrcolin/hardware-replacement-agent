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
[data-testid="stMainBlockContainer"] {{ max-width: 980px; padding-top: 1rem; }}

/* ---- widget header: avatar, name, status, settings, minimize ---- */
.st-key-widget-head {{
  background: linear-gradient(120deg, {ACCENT} 0%, {ACCENT_2} 100%);
  border-radius: 18px 18px 50% 50% / 18px 18px 28px 28px;  /* curved bottom edge */
  padding: 16px 18px 22px 18px; color: #fff; margin-bottom: 10px;
}}
.st-key-widget-head a, .st-key-widget-head div {{ text-decoration: none; }}
.head-id {{ display: flex; gap: 12px; align-items: center; }}
.head-id small {{ opacity: .85; font-size: 12px; }}
.head-id b {{ font-size: 19px; }}
.avatar {{
  width: 44px; height: 44px; border-radius: 50%; background: #fff; color: {ACCENT};
  display: flex; align-items: center; justify-content: center; font-weight: 800;
  box-shadow: 0 0 0 3px rgba(255,255,255,.35);
}}
.head-status {{ font-size: 13px; opacity: .92; margin: 10px 0 4px 2px; }}
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

/* ---- quick replies: outlined pills ---- */
[class*="st-key-quick-"] {{ display: flex; flex-flow: row wrap; gap: 8px; }}
[class*="st-key-quick-"] > div {{ width: auto !important; flex: 0 0 auto; }}
[class*="st-key-quick-"] button, [class*="st-key-part-"] button {{
  border: 1.5px solid {ACCENT}; color: {ACCENT}; background: #fff; border-radius: 999px;
  padding: 4px 14px; min-height: 34px;
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
.fact {{ margin-bottom: 6px; }}
.fact span {{ display: block; font-size: 11px; color: {MUTED}; text-transform: uppercase; }}
.fact b {{ font-size: 14px; color: {INK}; }}

/* ---- rating row ---- */
[class*="st-key-rating-"] {{ border-top: 1px solid {LINE}; padding-top: 4px; margin-top: 4px; }}
[class*="st-key-rating-"] [data-testid="stColumn"]:last-child {{
  display: flex; flex-direction: row; align-items: center; justify-content: flex-end; gap: 6px;
}}
[class*="st-key-rating-"] [data-testid="stColumn"]:last-child > div {{ width: auto !important; }}

/* ---- input: rounded pill with teal send button ---- */
[data-testid="stChatInput"] {{ border-radius: 999px; border: 1.5px solid {LINE}; }}
[data-testid="stChatInput"]:focus-within {{ border-color: {ACCENT}; }}
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
  background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px;
  text-align: center;
}}

/* ---- sidebar: history and trends ---- */
[data-testid="stSidebar"] {{ background: {CARD}; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .3rem; }}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(button) {{ margin: 0; }}
[data-testid="stSidebar"] button[kind="tertiary"] {{
  color: {INK}; text-align: left; justify-content: flex-start; padding: 2px 0;
}}
[data-testid="stSidebar"] button[kind="tertiary"]:hover {{ color: {ACCENT}; }}
.trend {{ margin: -6px 0 8px 0; font-size: 12px; color: {MUTED}; }}
.trend .bar {{ height: 6px; border-radius: 3px; background: {ACCENT}; opacity: .8; margin: 2px 0; }}
.trend .up {{ color: {ACCENT}; }}
.trend .down {{ color: #B42318; }}
.trend .flat {{ color: {MUTED}; }}

@media (max-width: 640px) {{
  .pimg img {{ max-height: 110px; }}
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stChatMessageContent"] {{ max-width: 90%; }}
}}
</style>
"""
