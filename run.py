from nicegui import ui
from ui.app import build_ui

if __name__ in {"__main__", "__mp_main__"}:
    build_ui()
    ui.run(title="AI Agent Browser Orchestrator", port=8080, reload=False)
