"""Shared desktop UI tokens. DESIGN.md documents this runtime source."""
COLORS = dict(background="#242333", surface="#302E43", field="#1D1C2B",
              text="#F4EFFA", muted="#C2BBD3", primary="#C9B4F4",
              border="#56516D", error="#FFC0CC")


def stylesheet():
    c = COLORS
    return f"""
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 14px; }}
    QWidget#chat {{ background: {c['background']}; }}
    QLabel#title {{ font-size: 24px; font-weight: 600; }}
    QLabel#muted, QLabel#status {{ color: {c['muted']}; }}
    QLabel#error {{ color: {c['error']}; }}
    QGroupBox {{ border: 1px solid {c['border']}; border-radius: 10px; margin-top: 12px; padding: 16px 12px 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
    QLineEdit, QPlainTextEdit, QComboBox {{ background: {c['field']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 9px; selection-background-color: {c['primary']}; selection-color: {c['field']}; }}
    QComboBox QAbstractItemView, QListWidget {{ background: {c['field']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    QListWidget::item {{ padding: 10px; border-bottom: 1px solid {c['border']}; }}
    QListWidget::item:selected {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['primary']}; }}
    QTabWidget::pane {{ border: 1px solid {c['border']}; }}
    QTabBar::tab {{ background: {c['field']}; color: {c['muted']}; padding: 9px 14px; }}
    QTabBar::tab:selected {{ background: {c['surface']}; color: {c['text']}; border-bottom: 2px solid {c['primary']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QListWidget:focus {{ border: 2px solid {c['primary']}; }}
    QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 12px; min-height: 20px; }}
    QPushButton:hover {{ border-color: {c['primary']}; }}
    QPushButton:focus {{ border: 2px solid {c['primary']}; }}
    QPushButton:pressed {{ background: {c['field']}; }}
    QPushButton:disabled {{ color: {c['muted']}; background: {c['field']}; }}
    QPushButton#primary {{ color: {c['field']}; background: {c['primary']}; font-weight: 600; }}
    QPushButton#primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QWidget#messages {{ background: transparent; }}
    QFrame#bubble {{ background: {c['surface']}; border-radius: 10px; }}
    QLabel#speaker {{ color: {c['primary']}; font-size: 12px; font-weight: 600; }}
    QScrollBar:vertical {{ background: {c['background']}; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 24px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['primary']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
