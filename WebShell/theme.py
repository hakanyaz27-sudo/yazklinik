LIGHT = {
    "bg":"#FAFAFA","surface":"#FFFFFF","surface_alt":"#F4F4F4",
    "border":"#E5E5E5","border_hover":"#D0D0D0",
    "text":"#1A1A1A","text_muted":"#6B6B6B","text_dim":"#9A9A9A",
    "primary":"#0067C0","primary_hover":"#0078D4","primary_pressed":"#005A9E",
    "danger":"#D13438","success":"#107C10",
}
DARK = {
    "bg":"#1F1F1F","surface":"#2B2B2B","surface_alt":"#252525",
    "border":"#3A3A3A","border_hover":"#4A4A4A",
    "text":"#F0F0F0","text_muted":"#A8A8A8","text_dim":"#7A7A7A",
    "primary":"#4CC2FF","primary_hover":"#69CCFF","primary_pressed":"#36A6E0",
    "danger":"#F1707A","success":"#6CCB5F",
}
COLORS = dict(LIGHT)

def _qss(C):
    dark = C["bg"].lower() == DARK["bg"].lower()
    sidebar_mid = "#202A33" if dark else "#EAF8FF"
    sidebar_edge = "#303B45" if dark else "#BFE7F5"
    sidebar_head_0 = "#26313A" if dark else "#FFFFFF"
    sidebar_head_1 = "#1F2A34" if dark else "#EDF9FF"
    header_0 = "#25313B" if dark else "#FFFFFF"
    header_1 = "#1F2A33" if dark else "#F2FBFF"
    header_edge = "#303B45" if dark else "#D7ECF7"
    cat_color = "#8AA5B8" if dark else "#648399"
    return f"""
* {{ font-family:'Segoe UI Variable','Segoe UI',sans-serif; font-size:14px; color:{C['text']}; }}
QMainWindow,QDialog {{ background:{C['bg']}; }}
QFrame[role="sidebar"] {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {C['surface']}, stop:0.52 {sidebar_mid}, stop:1 {C['surface_alt']});
    border-right:1px solid {sidebar_edge};
}}
QFrame[role="sidebarHead"] {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {sidebar_head_0}, stop:1 {sidebar_head_1});
    border:1px solid {sidebar_edge};
    border-radius:14px;
}}
QFrame[role="header"] {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {header_0}, stop:1 {header_1});
    border-bottom:1px solid {header_edge};
}}
QLabel[role="brand"] {{ color:{C['primary']}; font-size:21px; font-weight:850; }}
QLabel[role="muted"] {{ color:{C['text_muted']}; font-size:12px; }}
QLabel[role="accelerator"] {{
    color:#FFFFFF;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0EA5E9, stop:1 #14B8A6);
    border:1px solid rgba(255,255,255,0.45);
    border-radius:12px;
    padding:6px 10px;
    font-size:12px;
    font-weight:850;
}}
QLabel[role="cat"] {{
    color:{cat_color};
    font-size:11px;
    font-weight:750;
    letter-spacing:1px;
    padding:14px 10px 3px;
}}
QPushButton {{ background:{C['surface']}; border:1px solid {C['border']}; border-radius:10px; padding:6px 12px; color:{C['text']}; }}
QPushButton:hover {{ background:{C['surface_alt']}; }}
QPushButton[role="primary"] {{ background:{C['primary']}; color:white; border:none; font-weight:600; }}
QPushButton[role="nav"] {{
    text-align:left;
    border:none;
    border-radius:12px;
    background:transparent;
    padding:0;
    min-height:50px;
}}
QLineEdit,QComboBox {{ background:{C['surface']}; border:1px solid {C['border']}; border-radius:10px; padding:6px 10px; color:{C['text']}; }}
QLineEdit:focus {{ border-color:{C['primary']}; }}
QStatusBar {{ background:{C['surface']}; border-top:1px solid {C['border']}; color:{C['text_muted']}; padding-left:8px; }}
QListWidget {{ background:{C['surface']}; border:1px solid {C['border']}; border-radius:6px; color:{C['text']}; }}
QListWidget::item {{ padding:8px; }}
QListWidget::item:selected {{ background:{C['primary']}; color:white; }}
QScrollBar:vertical {{ background:transparent; width:10px; }}
QScrollBar::handle:vertical {{ background:{C['border']}; border-radius:4px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{C['border_hover']}; }}
QScrollBar::add-line,QScrollBar::sub-line {{ border:none; background:none; }}
"""

def apply(app, dark=False):
    global COLORS
    C = DARK if dark else LIGHT
    COLORS.clear(); COLORS.update(C)
    try:
        from PySide6.QtGui import QFontDatabase, QFont
        for n in ("Segoe UI Variable","Segoe UI","Tahoma","Arial"):
            if n in QFontDatabase.families():
                app.setFont(QFont(n, 10)); break
    except Exception: pass
    app.setStyleSheet(_qss(C))
