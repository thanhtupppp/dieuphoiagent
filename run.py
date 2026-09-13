from nicegui import ui
from ui.app import build_ui


def main() -> None:
    """Start the NiceGUI desktop/web control surface."""
    build_ui()
    print("=" * 65)
    print("🚀 Giao diện NiceGUI đang chạy tại: http://localhost:8080")
    print("👉 Hãy mở bằng trình duyệt hiện đại (Google Chrome / Edge).")
    print("=" * 65)
    ui.run(title="AI Agent Browser Orchestrator", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
