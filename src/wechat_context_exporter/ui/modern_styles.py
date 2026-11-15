"""
Modern glassmorphism UI styles for WeChat AI Memory.
Inspired by smart home interfaces with warm gradients and frosted glass effects.
"""

MODERN_STYLESHEET = """
/* === Global & Background === */
QMainWindow, QWidget#appRoot {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(250, 237, 225, 255),
        stop:0.5 rgba(245, 225, 210, 255),
        stop:1 rgba(235, 215, 200, 255)
    );
}

QWidget {
    color: #2d2520;
    font-size: 13px;
}

QLabel {
    background: transparent;
}

/* === Top Bar with Glass Effect === */
QFrame#topBar {
    background: rgba(255, 255, 255, 0.7);
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.3);
}

QLabel#brandMark {
    background: transparent;
}

QLabel#pageTitle {
    color: #3d2f28;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

QLabel#editionLabel {
    color: #9d8b7f;
    font-size: 9px;
    font-weight: 600;
}

/* === Status Badges === */
QLabel#privacyBadge, QLabel#connectionBadge {
    border-radius: 12px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(10px);
}

QLabel#privacyBadge {
    background: rgba(255, 255, 255, 0.8);
    color: #6b5d52;
    border: 1px solid rgba(255, 255, 255, 0.4);
}

QLabel#connectionBadge[state="idle"] {
    background: rgba(240, 240, 240, 0.85);
    color: #7a6e64;
    border: 1px solid rgba(255, 255, 255, 0.3);
}

QLabel#connectionBadge[state="busy"] {
    background: rgba(255, 237, 213, 0.9);
    color: #c07832;
    border: 1px solid rgba(255, 200, 150, 0.5);
}

QLabel#connectionBadge[state="connected"] {
    background: rgba(200, 240, 220, 0.9);
    color: #2d8659;
    border: 1px solid rgba(150, 220, 180, 0.5);
}

QLabel#connectionBadge[state="error"] {
    background: rgba(255, 220, 210, 0.9);
    color: #c4342d;
    border: 1px solid rgba(255, 180, 160, 0.5);
}

/* === Sidebar Glass Card === */
QFrame#sidebar {
    background: rgba(255, 255, 255, 0.6);
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.4);
    backdrop-filter: blur(20px);
}

QScrollArea#sidebarScroll,
QScrollArea#sidebarScroll > QWidget > QWidget,
QWidget#sidebarForm,
QWidget#sidebarActions {
    background: transparent;
    border: none;
}

/* === Workspace Area === */
QWidget#workspace {
    background: transparent;
}

/* === Section Labels === */
QLabel#sectionIndex {
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 8px;
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 200, 150, 0.9),
        stop:1 rgba(255, 180, 120, 0.9)
    );
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
    border: 1px solid rgba(255, 255, 255, 0.3);
}

QLabel#sectionTitle {
    color: #3d2f28;
    font-size: 14px;
    font-weight: 700;
}

/* === Metrics Panel Glass Card === */
QFrame#metricsPanel {
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: 16px;
    backdrop-filter: blur(10px);
}

QWidget#metricBlock {
    background: transparent;
    border: none;
}

QFrame#metricDivider {
    background: rgba(200, 180, 160, 0.3);
    border: none;
    margin-top: 10px;
    margin-bottom: 10px;
}

QLabel#metricValue {
    color: #3d2f28;
    font-size: 18px;
    font-weight: 700;
}

QLabel#metricCaption {
    color: #8d7d71;
    font-size: 10px;
    font-weight: 600;
}

/* === Field Labels === */
QLabel#fieldLabel {
    color: #6b5d52;
    font-size: 11px;
    font-weight: 600;
    padding-top: 2px;
}

QFrame#separator {
    border: none;
    background: rgba(200, 180, 160, 0.25);
    margin-top: 6px;
    margin-bottom: 6px;
}

QLabel#dateCaption {
    color: #6b5d52;
    font-size: 11px;
    font-weight: 600;
}

/* === Workspace Title === */
QLabel#workspaceTitle {
    color: #3d2f28;
    font-size: 22px;
    font-weight: 700;
}

QLabel#subtitle {
    color: #8d7d71;
    font-size: 12px;
}

/* === Input Fields with Glass Effect === */
QLineEdit, QComboBox, QDateEdit {
    min-height: 42px;
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    padding: 0 14px;
    selection-background-color: rgba(255, 180, 120, 0.5);
    color: #3d2f28;
    backdrop-filter: blur(8px);
}

QLineEdit:hover, QComboBox:hover, QDateEdit:hover {
    background: rgba(255, 255, 255, 0.9);
    border-color: rgba(255, 200, 150, 0.6);
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    background: rgba(255, 255, 255, 0.95);
    border: 2px solid rgba(255, 180, 120, 0.8);
    padding: 0 13px;
}

QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {
    color: #b5a89d;
    background: rgba(240, 235, 230, 0.6);
}

QLineEdit#searchField {
    background: rgba(255, 255, 255, 0.8);
    padding-left: 14px;
}

QDateEdit#dateInput {
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    padding: 0 10px;
}

/* === Buttons === */
QToolButton#calendarButton {
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-left: none;
    border-top-right-radius: 12px;
    border-bottom-right-radius: 12px;
    padding: 8px;
}

QToolButton#calendarButton:hover {
    background: rgba(255, 240, 230, 0.9);
    border-color: rgba(255, 200, 150, 0.6);
}

QToolButton#scopeSearchButton {
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    padding: 10px;
}

QToolButton#scopeSearchButton:hover {
    background: rgba(255, 240, 230, 0.9);
    border-color: rgba(255, 200, 150, 0.6);
}

/* === Primary Button with Gradient === */
QPushButton#primaryButton {
    min-height: 48px;
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 170, 100, 1),
        stop:1 rgba(255, 140, 80, 1)
    );
    color: #ffffff;
    border: none;
    border-radius: 14px;
    font-weight: 700;
    font-size: 14px;
}

QPushButton#primaryButton:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 160, 90, 1),
        stop:1 rgba(255, 130, 70, 1)
    );
}

QPushButton#primaryButton:pressed {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(245, 150, 80, 1),
        stop:1 rgba(245, 120, 60, 1)
    );
}

QPushButton#primaryButton:disabled {
    background: rgba(200, 190, 180, 0.6);
    color: rgba(255, 255, 255, 0.7);
}

/* === Standard Buttons === */
QPushButton {
    min-height: 42px;
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.8);
    color: #3d2f28;
    padding: 0 16px;
    font-weight: 600;
    backdrop-filter: blur(8px);
}

QPushButton:hover {
    background: rgba(255, 240, 230, 0.9);
    border-color: rgba(255, 200, 150, 0.7);
}

QPushButton:pressed {
    background: rgba(245, 230, 215, 0.9);
}

QPushButton:disabled {
    color: #b5a89d;
    border-color: rgba(220, 210, 200, 0.6);
    background: rgba(240, 235, 230, 0.5);
}

QPushButton#iconButton {
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
    padding: 0;
    border-radius: 12px;
}

QPushButton#connectButton {
    color: #2d8659;
    border-color: rgba(150, 220, 180, 0.6);
    background: rgba(200, 240, 220, 0.7);
}

QPushButton#connectButton:hover {
    background: rgba(190, 235, 215, 0.85);
}

/* === Checkboxes === */
QCheckBox {
    min-height: 26px;
    color: #4d423a;
    spacing: 10px;
}

QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 6px;
    border: 2px solid rgba(255, 255, 255, 0.6);
    background: rgba(255, 255, 255, 0.7);
}

QCheckBox::indicator:checked {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255, 180, 120, 1),
        stop:1 rgba(255, 150, 90, 1)
    );
    border-color: rgba(255, 180, 120, 0.8);
}

/* === Table Widget === */
QTableWidget {
    background: rgba(255, 255, 255, 0.7);
    alternate-background-color: rgba(250, 245, 240, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: 14px;
    padding: 0;
    selection-background-color: rgba(255, 220, 180, 0.5);
    selection-color: #3d2f28;
    backdrop-filter: blur(10px);
}

QTableWidget::item {
    border-bottom: 1px solid rgba(230, 220, 210, 0.5);
    padding: 8px 10px;
}

QHeaderView::section {
    background: rgba(245, 235, 225, 0.8);
    color: #5d5045;
    border: none;
    border-bottom: 2px solid rgba(255, 200, 150, 0.4);
    padding: 10px 10px;
    font-size: 11px;
    font-weight: 700;
}

/* === Scrollbar === */
QScrollBar:vertical {
    background: rgba(240, 235, 230, 0.5);
    width: 12px;
    margin: 0;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: rgba(200, 180, 160, 0.6);
    min-height: 30px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(180, 160, 140, 0.7);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* === Splitter === */
QSplitter#mainSplitter::handle {
    background: rgba(255, 255, 255, 0.3);
    width: 1px;
}

/* === Status Bar === */
QFrame#statusBar {
    background: rgba(255, 255, 255, 0.7);
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.4);
}

QLabel#statusLabel, QLabel#footerNote {
    color: #8d7d71;
    font-size: 11px;
}

/* === Progress Bar === */
QProgressBar {
    max-height: 6px;
    border: none;
    border-radius: 3px;
    background: rgba(230, 220, 210, 0.5);
}

QProgressBar::chunk {
    border-radius: 3px;
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 180, 120, 1),
        stop:1 rgba(255, 150, 90, 1)
    );
}

/* === Tooltips === */
QToolTip {
    background: rgba(60, 50, 45, 0.95);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
}

/* === Dialogs === */
QDialog#conversationSearchDialog, QDialog#datePickerDialog {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(250, 240, 230, 255),
        stop:1 rgba(245, 230, 220, 255)
    );
}

QLabel#dialogTitle {
    color: #3d2f28;
    font-size: 20px;
    font-weight: 700;
}

QLabel#calendarMonthLabel {
    color: #3d2f28;
    font-size: 16px;
    font-weight: 700;
}

/* === List Widget === */
QListWidget#conversationChoiceList {
    background: rgba(255, 255, 255, 0.8);
    alternate-background-color: rgba(250, 245, 240, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    padding: 6px;
    outline: none;
    backdrop-filter: blur(8px);
}

QListWidget#conversationChoiceList::item {
    min-height: 42px;
    padding: 0 12px;
    border-radius: 8px;
}

QListWidget#conversationChoiceList::item:selected {
    color: #3d2f28;
    background: rgba(255, 200, 150, 0.4);
    border: 1px solid rgba(255, 180, 120, 0.5);
}

QListWidget#conversationChoiceList::item:hover {
    background: rgba(255, 240, 220, 0.6);
}

/* === Calendar Navigation === */
QToolButton#calendarNavButton {
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 10px;
    padding: 8px;
}

QToolButton#calendarNavButton:hover {
    background: rgba(255, 240, 230, 0.9);
    border-color: rgba(255, 200, 150, 0.7);
}

/* === Calendar Widget === */
QCalendarWidget#rangeCalendar {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 14px;
    backdrop-filter: blur(10px);
}

QCalendarWidget#rangeCalendar QAbstractItemView:enabled {
    color: #3d2f28;
    background: transparent;
    selection-background-color: rgba(255, 180, 120, 0.9);
    selection-color: #ffffff;
    outline: none;
}

/* === Dialog Buttons === */
QPushButton#dialogPrimary {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 170, 100, 1),
        stop:1 rgba(255, 140, 80, 1)
    );
    color: #ffffff;
    border: none;
}

QPushButton#dialogPrimary:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 160, 90, 1),
        stop:1 rgba(255, 130, 70, 1)
    );
}

/* === Combo Box Dropdown === */
QComboBox::drop-down, QDateEdit::drop-down {
    border: none;
    width: 30px;
}

QComboBox QAbstractItemView {
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 10px;
    selection-background-color: rgba(255, 220, 180, 0.6);
    selection-color: #3d2f28;
    padding: 6px;
    backdrop-filter: blur(10px);
}
"""
