from nicegui import ui
from ui.app import build_ui


def main() -> None:
    """Start the NiceGUI desktop/web control surface."""
    build_ui()
    ui.run(title="AI Agent Browser Orchestrator", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
