"""Marketplace look: dark top bar with central search, light page, white cards, yellow actions.

Only CSS. Elements are targeted through the ``st-key-<key>`` classes Streamlit adds to keyed
containers and widgets, so the styling does not depend on Streamlit's internal markup.
"""

from __future__ import annotations

NAV = "#131921"  # top bar
SUBNAV = "#232F3E"  # quick-links strip and footer
FOOTER_TOP = "#37475A"  # "back to top" strip
PAGE = "#EAEDED"
CARD_BORDER = "#D5D9D9"
TEXT = "#0F1111"
MUTED = "#565959"
LINK = "#007185"
LINK_HOVER = "#C7511F"
SEARCH_BUTTON = "#FEBD69"
ACTION = "#FFD814"
ACTION_BORDER = "#FCD200"
IN_STOCK = "#007600"
ALERT = "#B12704"
WARNING_BG = "#FFF4E5"

CSS = f"""
<style>
.stApp {{ background: {PAGE}; }}
header[data-testid="stHeader"] {{ display: none; }}
[data-testid="stMainBlockContainer"] {{
  padding: 0 1rem 0 1rem; max-width: 1500px;
}}
.stApp a {{ color: {LINK}; text-decoration: none; }}
.stApp a:hover {{ color: {LINK_HOVER}; text-decoration: underline; }}

/* ---- top bar ---- */
.st-key-topbar {{
  background: {NAV}; padding: 10px 0;
  box-shadow: 0 0 0 100vmax {NAV}; clip-path: inset(0 -100vmax);  /* full-bleed */
}}
.st-key-topbar [data-testid="stForm"] {{ border: none; padding: 0; }}
.st-key-topbar [data-testid="stHorizontalBlock"] {{ gap: 0; align-items: center; }}
.st-key-topbar .brand {{
  color: #fff; line-height: 1.05; padding-right: 18px; white-space: nowrap;
}}
.st-key-topbar .brand b {{ font-size: 21px; letter-spacing: -0.3px; }}
.st-key-topbar .brand b span {{ color: #FF9900; }}
.st-key-topbar .brand small {{ color: #CCC; font-size: 11px; }}
.st-key-topbar .account {{ color: #fff; font-size: 12px; line-height: 1.2; padding-left: 18px; }}
.st-key-topbar .account b {{ font-size: 14px; }}
.st-key-category [data-baseweb="select"] > div {{
  background: #F3F3F3; border: none; border-radius: 4px 0 0 4px; min-height: 40px;
  font-size: 12px; color: {MUTED};
}}
.st-key-q input {{ height: 40px; font-size: 15px; }}
.st-key-q [data-baseweb="input"], .st-key-q [data-baseweb="base-input"] {{
  border: none; border-radius: 0;
}}
.st-key-search button {{
  background: {SEARCH_BUTTON}; color: {TEXT}; border: none; border-radius: 0 4px 4px 0;
  height: 40px; min-height: 40px; width: 100%; font-weight: 700;
}}
.st-key-search button:hover {{ background: #F3A847; color: {TEXT}; }}
.st-key-topbar [data-testid="stFormSubmitButton"] {{ width: 100%; }}

/* ---- quick-links strip ---- */
.st-key-subnav {{
  background: {SUBNAV}; padding: 2px 0; margin-bottom: 14px;
  box-shadow: 0 0 0 100vmax {SUBNAV}; clip-path: inset(0 -100vmax);  /* full-bleed */
}}
.st-key-subnav [data-testid="stHorizontalBlock"] {{ gap: 2px; flex-wrap: wrap; }}
.st-key-subnav [data-testid="stColumn"] {{ width: auto; flex: 0 0 auto; min-width: 0; }}
.st-key-subnav button {{
  background: transparent; border: 1px solid transparent; color: #fff; font-size: 13px;
  padding: 2px 8px; min-height: 30px;
}}
.st-key-subnav button:hover {{ border-color: #fff; color: #fff; background: transparent; }}
.st-key-subnav button p {{ font-size: 13px; }}

/* ---- results header and left rail ---- */
.results-bar {{
  background: #fff; border-bottom: 1px solid {CARD_BORDER}; margin: -14px -1rem 14px -1rem;
  padding: 8px 1.2rem; font-size: 14px; box-shadow: 0 2px 5px rgba(15,17,17,.08);
}}
.results-bar .term {{ color: {LINK_HOVER}; font-weight: 700; }}
.st-key-rail h4, .rail-title {{ font-size: 14px; font-weight: 700; margin: 10px 0 2px 0; }}
.st-key-rail {{ font-size: 14px; }}

/* ---- cards ---- */
[class*="st-key-card-"], .st-key-original, [class*="st-key-tile-"] {{
  background: #fff; border: 1px solid {CARD_BORDER}; border-radius: 8px; padding: 14px 18px;
}}
[class*="st-key-card-"] h3 {{ color: {LINK}; font-size: 18px; font-weight: 400; padding: 0; }}
[class*="st-key-card-"] h3:hover {{ color: {LINK_HOVER}; }}
.thumb {{
  aspect-ratio: 1; background: #F7F8F8; border-radius: 4px; display: flex;
  align-items: center; justify-content: center; flex-direction: column; color: {MUTED};
  font-size: 12px; text-align: center; padding: 6px;
}}
.thumb b {{ font-size: 28px; color: {SUBNAV}; }}
.choice {{
  display: inline-block; background: {SUBNAV}; color: #fff; font-size: 12px; padding: 3px 8px;
  border-radius: 0 0 4px 0; margin-bottom: 6px;
}}
.choice span {{ color: #FF9900; }}
.price {{ font-size: 28px; line-height: 1; color: {TEXT}; }}
.price sup {{ font-size: 13px; top: -0.9em; }}
.no-price {{ font-size: 14px; color: {MUTED}; }}
.stock-in {{ color: {IN_STOCK}; font-size: 15px; }}
.stock-out {{ color: {ALERT}; font-size: 15px; }}
.muted {{ color: {MUTED}; font-size: 13px; }}
.coverage {{
  height: 8px; background: #E3E6E6; border-radius: 4px; overflow: hidden; margin: 4px 0;
}}
.coverage div {{ height: 100%; background: #FFA41C; }}
.status-red {{ color: {ALERT}; font-weight: 700; }}

/* ---- section bands ---- */
.band {{ font-size: 21px; font-weight: 700; margin: 18px 0 6px 0; }}
.band-warn {{
  background: {WARNING_BG}; border-left: 4px solid #FF9900; padding: 8px 12px; font-size: 14px;
  margin-bottom: 8px; border-radius: 0 4px 4px 0;
}}
.band-gray {{
  background: #F3F3F3; border-left: 4px solid #8D9096; padding: 8px 12px; font-size: 14px;
  margin-bottom: 8px; border-radius: 0 4px 4px 0;
}}

/* ---- yellow pill actions ---- */
[data-testid="stBaseButton-primary"] {{
  background: {ACTION}; border: 1px solid {ACTION_BORDER}; color: {TEXT}; border-radius: 100px;
}}
[data-testid="stBaseButton-primary"]:hover {{
  background: #F7CA00; color: {TEXT}; border-color: #F2C200;
}}

/* ---- phone width: compact bar, results before the filters rail ---- */
@media (max-width: 640px) {{
  .st-key-topbar .account, .st-key-topbar .brand small {{ display: none; }}
  .st-key-topbar [data-testid="stColumn"] {{ margin-bottom: 4px; }}
  .st-key-topbar .brand {{ padding: 8px 0 2px 0; line-height: 1.4; margin-bottom: 1.2rem; }}
  .thumb {{ display: none; }}
  .st-key-category [data-baseweb="select"] > div, .st-key-q [data-baseweb="input"] {{
    border-radius: 4px;
  }}
  .st-key-search button {{ border-radius: 4px; }}
  [data-testid="stColumn"]:has(.st-key-rail) {{ order: 2; }}
}}

/* ---- footer ---- */
.backtop {{
  background: {FOOTER_TOP}; color: #fff; text-align: center; font-size: 13px; padding: 14px;
  margin: 32px -1rem 0 -1rem;
}}
.backtop a, .backtop a:hover {{ color: #fff; }}
.footer {{
  background: {SUBNAV}; color: #DDD; font-size: 12px; padding: 22px 1.2rem;
  margin: 0 -1rem; line-height: 1.7;
}}
.footer b {{ color: #fff; }}
</style>
"""
