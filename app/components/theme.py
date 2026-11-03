"""Agent look: calm neutral chat, compact result cards, visible reasoning timeline.

Only CSS. Elements are targeted through the ``st-key-<key>`` classes Streamlit adds to keyed
containers and widgets, so the styling does not depend on Streamlit's internal markup.
"""

from __future__ import annotations

ACCENT = "#0F766E"  # teal: agent identity
ACCENT_SOFT = "#E6F4F1"
INK = "#1F2933"
MUTED = "#5F6B76"
LINE = "#DDE3E8"
CARD = "#FFFFFF"
PAGE = "#F6F8FA"

CSS = f"""
<style>
.stApp {{ background: {PAGE}; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1100px; padding-top: 1.2rem; }}

/* ---- header ---- */
.chat-head {{
  display: flex; flex-direction: column; gap: 2px; padding: 4px 0 12px 0;
  border-bottom: 1px solid {LINE}; margin-bottom: 8px;
}}
.chat-head b {{ font-size: 20px; color: {INK}; }}
.chat-head span {{ font-size: 13px; color: {MUTED}; }}

/* ---- sidebar: agent identity and tools ---- */
.agent-id {{ display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }}
.agent-id small {{ color: {MUTED}; }}
.avatar {{
  width: 38px; height: 38px; border-radius: 50%; background: {ACCENT}; color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
}}
.tool {{
  border-left: 3px solid {ACCENT}; background: {CARD}; padding: 6px 10px; margin: 6px 0;
  border-radius: 0 6px 6px 0; font-size: 13px; line-height: 1.35;
}}
.tool b {{ display: block; color: {INK}; }}
.tool span {{ color: {MUTED}; word-break: break-word; }}

/* ---- reasoning timeline ---- */
ol.steps {{ list-style: none; padding-left: 0; margin: 0; counter-reset: s; }}
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
  background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 12px 14px;
}}
[class*="st-key-card-"] h3 {{ font-size: 17px; padding: 0; color: {INK}; }}
.fact {{ margin-bottom: 6px; }}
.fact span {{ display: block; font-size: 11px; color: {MUTED}; text-transform: uppercase; }}
.fact b {{ font-size: 14px; color: {INK}; }}

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
  background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px;
  text-align: center;
}}

@media (max-width: 640px) {{
  .pimg img {{ max-height: 110px; }}
}}
</style>
"""
