from typing import Any
from nicegui import ui

from core.checkpoint_manager import load_checkpoint
from core.config_loader import load_config, load_selectors
from core.orchestrator_fsm import FSMState, OrchestratorFSM
from core.providers.base import ProviderKind
from core.providers.factory import build_provider
from core.session_history import get_recent_sessions, load_session_details
from ui.log_streamer import LogStreamer
from ui.preview_modal import PreviewModal


def _set_badge_color(badge: Any, color: str) -> None:
    badge.props(f"color={color}")


def build_ui():
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    fsm = OrchestratorFSM(config, selectors)
    streamer = LogStreamer()
    ui.page_title("AI Agent Browser Orchestrator")

    def fsm_log(source: str, msg: str) -> None:
        streamer.push(source, msg)

    fsm.on_log = fsm_log

    # Header with title and provider/history controls
    with ui.header().classes(
        "bg-slate-900 text-white p-4 flex justify-between items-center shadow-md"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon("smart_toy", size="md").classes("text-indigo-400")
            ui.label("AI AGENT BROWSER ORCHESTRATOR").classes("text-lg font-bold tracking-wider")
        with ui.row().classes("items-center gap-3"):
            header_badge = ui.badge("CDP: Port 9222 (100% Free)", color="emerald").classes(
                "px-3 py-1 text-xs font-mono"
            )
            ui.button(
                "Lịch sử Phiên",
                icon="history",
                on_click=lambda: open_history_dialog(),
            ).props("flat text-slate-300 text-xs hover:text-white")

    with ui.row().classes("w-full p-4 gap-6 items-start"):
        # Left Column: Configuration & Controls
        with ui.column().classes(
            "w-5/12 bg-white p-5 rounded-xl border border-slate-200 shadow-sm gap-4"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("tune", size="sm").classes("text-indigo-600")
                ui.label("Cấu hình Nhiệm vụ").classes("text-base font-semibold text-slate-800")

            # Checkpoint recovery card
            checkpoint_card = ui.card().classes(
                "w-full bg-indigo-50 border border-indigo-200 p-3 rounded-lg"
            )
            with checkpoint_card:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("history", size="xs").classes("text-indigo-600")
                    cp_label = ui.label("Kiểm tra Checkpoint...").classes(
                        "text-xs font-medium text-indigo-900 font-mono"
                    )

            def refresh_checkpoint_banner() -> None:
                cp = load_checkpoint()
                if cp and cp.repo:
                    checkpoint_card.set_visibility(True)
                    info = f"Checkpoint: {cp.repo} | Vòng {cp.loop_count} | Tiếp theo: {cp.next_target_agent.upper()}"
                    if cp.pr_url:
                        info += f" (PR: {cp.pr_url})"
                    cp_label.text = info
                else:
                    checkpoint_card.set_visibility(False)

            refresh_checkpoint_banner()

            # Provider selection dropdown
            provider_select = ui.select(
                label="Provider Thực thi (Backend)",
                options={
                    "cdp": "Chrome CDP (Miễn phí qua Browser, Port 9222)",
                    "api": "OpenAI API (Fallback qua API Key)",
                },
                value="cdp",
            ).classes("w-full")

            def on_provider_change(e: Any) -> None:
                kind = ProviderKind.CDP if e.value == "cdp" else ProviderKind.API
                try:
                    new_p = build_provider(kind, config, selectors)
                    fsm.provider = new_p
                    if kind == ProviderKind.CDP:
                        header_badge.text = "CDP: Port 9222 (100% Free)"
                        _set_badge_color(header_badge, "emerald")
                    else:
                        header_badge.text = "API Mode (Fallback)"
                        _set_badge_color(header_badge, "amber")
                    ui.notify(f"Đã chuyển Provider sang: {e.value.upper()}", color="positive")
                except Exception as exc:
                    ui.notify(f"Lỗi chuyển Provider {e.value}: {exc}", color="negative")
                    provider_select.value = "cdp"

            provider_select.on_value_change(on_provider_change)

            repo_input = ui.input(
                label="GitHub Repository (vd: owner/repo)",
                value="thanhtupppp/nguyencuufacepython",
            ).classes("w-full")
            branch_input = ui.input(label="Base Branch", value="main").classes("w-full")
            goal_input = ui.textarea(
                label="Mục tiêu Kỹ thuật (Task Goal)",
                value="Nâng cấp hệ thống readiness observability và runtime contract an toàn",
                placeholder="Mô tả chi tiết bug cần sửa hoặc tính năng cần lập trình...",
            ).classes("w-full h-24")

            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Giới hạn Vòng lặp:").classes("text-sm font-medium text-slate-700")
                loop_slider = ui.slider(min=1, max=10, value=5).classes("w-44")
                loop_label = ui.label("5").classes("font-mono font-bold text-indigo-600")
                loop_slider.bind_value_to(loop_label, "text", forward=lambda v: str(v))

            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Timeout bảo vệ AI/Tool:").classes("text-sm font-medium text-slate-700")
                timeout_select = ui.select(
                    options={300: "5 phút (300s)", 600: "10 phút (600s)", 900: "15 phút (900s)"},
                    value=600,
                ).classes("w-44")

            auto_switch = ui.switch("Chạy tự động (Auto-pilot)", value=True).classes(
                "text-sm text-slate-700 font-medium"
            )
            ui.separator().classes("my-1")

            with ui.row().classes("items-center gap-2"):
                ui.icon("play_circle", size="sm").classes("text-indigo-600")
                ui.label("Điều khiển Vận hành & Cứu hộ").classes(
                    "text-sm font-semibold text-slate-700"
                )

            with ui.row().classes("w-full gap-2"):
                start_btn = ui.button("Bắt đầu mới", color="indigo-600", icon="play_arrow").classes(
                    "flex-1 text-white font-medium py-2 rounded-lg"
                )
                resume_btn = ui.button(
                    "Tiếp tục (Resume)", color="teal-600", icon="fast_forward"
                ).classes("flex-1 text-white font-medium py-2 rounded-lg")

            with ui.row().classes("w-full gap-2"):
                sync_btn = ui.button("Đồng bộ từ Browser", color="sky-600", icon="sync").classes(
                    "flex-1 text-white font-medium py-2 rounded-lg"
                )
                retry_btn = ui.button(
                    "Thử lại bước (Retry)", color="blue-600", icon="refresh"
                ).classes("flex-1 text-white font-medium py-2 rounded-lg")

            with ui.row().classes("w-full gap-2"):
                pause_btn = ui.button("Tạm dừng", color="amber-600", icon="pause").classes(
                    "flex-1 text-white font-medium py-2 rounded-lg"
                )
                stop_btn = ui.button("Dừng khẩn", color="rose-600", icon="stop").classes(
                    "flex-1 text-white font-medium py-2 rounded-lg"
                )

            abort_btn = ui.button(
                "Hủy bỏ & Reset Checkpoint", color="slate-700", icon="cancel"
            ).classes("w-full text-white font-medium py-2 rounded-lg mt-1")

        # Right Column: Live Status, PR Result Card, and Filtered Logs
        with ui.column().classes(
            "w-6/12 bg-white p-5 rounded-xl border border-slate-200 shadow-sm gap-4 flex-1"
        ):
            with ui.row().classes(
                "w-full justify-between items-center border-b border-slate-100 pb-3"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.label("Trạng thái:").classes("text-sm font-semibold text-slate-700")
                    state_badge = ui.badge("IDLE", color="slate").classes(
                        "px-3 py-1 font-mono text-xs font-bold"
                    )
                with ui.row().classes("items-center gap-2"):
                    ui.label("Vòng lặp:").classes("text-sm font-semibold text-slate-700")
                    loop_badge = ui.badge("0 / 5", color="blue").classes(
                        "px-3 py-1 font-mono text-xs font-bold"
                    )
                with ui.row().classes("items-center gap-2"):
                    cb_badge = ui.badge("Circuit Breaker: 0/5", color="emerald").classes(
                        "px-3 py-1 font-mono text-xs font-bold cursor-pointer"
                    )
                    cb_badge.tooltip("Số lỗi transient liên tiếp. Bấm để reset Circuit Breaker.")

            def update_cb_badge() -> None:
                cb = fsm.circuit_breaker
                if cb.is_tripped:
                    cb_badge.text = f"Circuit Breaker: TRIPPED ({cb.failures}/{cb.max_failures})"
                    _set_badge_color(cb_badge, "rose")
                elif cb.failures > 0:
                    cb_badge.text = f"Circuit Breaker: {cb.failures}/{cb.max_failures}"
                    _set_badge_color(cb_badge, "amber")
                else:
                    cb_badge.text = f"Circuit Breaker: 0/{cb.max_failures}"
                    _set_badge_color(cb_badge, "emerald")

            def reset_cb() -> None:
                fsm.circuit_breaker.reset()
                update_cb_badge()
                ui.notify("Đã reset Circuit Breaker về 0.", color="info")

            cb_badge.on("click", reset_cb)

            # Interactive PR / Commit result card
            result_card = ui.card().classes(
                "w-full bg-slate-50 border border-slate-200 p-3 rounded-lg gap-2"
            )
            with result_card:
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("commit", size="sm").classes("text-indigo-600")
                        ui.label("Kết quả Pull Request / Commit").classes(
                            "text-sm font-bold text-slate-800"
                        )
                    pr_link_btn = ui.button(
                        "Mở GitHub PR", icon="open_in_new", color="indigo-600"
                    ).props("flat text-xs")
                with ui.row().classes("w-full gap-4 text-xs"):
                    branch_val = ui.label("Branch: -").classes(
                        "font-mono font-medium text-slate-700"
                    )
                    commit_val = ui.label("Commit: -").classes(
                        "font-mono font-medium text-slate-700"
                    )
            result_card.set_visibility(False)

            def update_result_card() -> None:
                has_info = bool(fsm.feature_branch or fsm.commit_sha or fsm.pr_url)
                result_card.set_visibility(has_info)
                if has_info:
                    branch_val.text = f"Branch: {fsm.feature_branch or '-'}"
                    commit_val.text = f"Commit: {fsm.commit_sha or '-'}"
                    if fsm.pr_url:
                        pr_link_btn.set_visibility(True)
                        pr_link_btn.on_click(lambda: ui.navigate.to(fsm.pr_url, new_tab=True))
                    else:
                        pr_link_btn.set_visibility(False)

            def on_state_update(st: FSMState) -> None:
                state_badge.text = st.value
                if st == FSMState.TASK_FINISHED:
                    _set_badge_color(state_badge, "emerald")
                elif st in (FSMState.RECOVERY_REQUIRED, FSMState.CDP_ERROR, FSMState.ABORTED):
                    _set_badge_color(state_badge, "rose")
                elif st in (FSMState.PAUSED, FSMState.WAITING_USER_APPROVAL):
                    _set_badge_color(state_badge, "amber")
                elif st == FSMState.RECONCILING:
                    _set_badge_color(state_badge, "cyan")
                else:
                    _set_badge_color(state_badge, "indigo")
                loop_badge.text = f"{fsm.loop_count} / {fsm.max_loops}"
                update_cb_badge()
                update_result_card()
                refresh_checkpoint_banner()

            fsm.on_state_change = on_state_update

            # Filtered log container & tabs
            active_filter = "all"

            with ui.tabs().classes(
                "w-full border-b border-slate-200 text-slate-600"
            ) as log_tabs:
                ui.tab("Tất cả Log")
                tab_p = ui.tab("Perplexity (Lead)")
                tab_c = ui.tab("ChatGPT (Dev)")

            log_container = ui.column().classes(
                "w-full h-[400px] overflow-y-auto bg-slate-950 text-slate-200 p-4 rounded-lg font-mono text-xs gap-1.5 shadow-inner"
            )

            def render_logs() -> None:
                log_container.clear()
                with log_container:
                    for item in streamer.logs:
                        src = str(item.get("source", "")).lower()
                        if active_filter == "all" or active_filter == src:
                            color = (
                                "text-purple-300"
                                if src == "perplexity"
                                else "text-emerald-300"
                                if src == "chatgpt"
                                else "text-cyan-300"
                            )
                            ui.label(
                                f"[{item.get('timestamp', '')}] [{src.upper()}]: {item.get('message', '')}"
                            ).classes(color)

            def on_tab_change(e: Any) -> None:
                nonlocal active_filter
                if e.value == tab_p:
                    active_filter = "perplexity"
                elif e.value == tab_c:
                    active_filter = "chatgpt"
                else:
                    active_filter = "all"
                render_logs()

            log_tabs.on_value_change(on_tab_change)

            def add_log_ui(item: dict[str, Any]) -> None:
                update_cb_badge()
                update_result_card()
                src = str(item.get("source", "")).lower()
                if active_filter == "all" or active_filter == src:
                    color = (
                        "text-purple-300"
                        if src == "perplexity"
                        else "text-emerald-300"
                        if src == "chatgpt"
                        else "text-cyan-300"
                    )
                    with log_container:
                        ui.label(
                            f"[{item.get('timestamp', '')}] [{src.upper()}]: {item.get('message', '')}"
                        ).classes(color)

            streamer.subscribe(add_log_ui)

            with ui.row().classes("w-full justify-between items-center mt-1"):
                ui.button(
                    "Xóa Log",
                    on_click=lambda: (streamer.clear(), log_container.clear()),
                ).props("flat text-slate-500 text-xs")
                ui.button(
                    "Lưu phiên (Export)",
                    on_click=lambda: ui.notify(
                        "Dữ liệu phiên đã được tự động lưu vào storage/sessions/",
                        color="positive",
                    ),
                ).props("flat text-indigo-600 text-xs")

    # Session History Dialog
    def open_history_dialog() -> None:
        sessions = get_recent_sessions(limit=25)
        with ui.dialog() as hist_dlg, ui.card().classes("w-[850px] max-w-5xl p-6 gap-4"):
            with ui.row().classes("w-full justify-between items-center border-b pb-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("folder_open", size="sm").classes("text-indigo-600")
                    ui.label("Lịch sử Phiên Điều Phối (storage/sessions)").classes(
                        "text-lg font-bold text-slate-800"
                    )
                ui.button(icon="close", on_click=hist_dlg.close).props("flat round dense")

            if not sessions:
                ui.label("Chưa có phiên lưu nào trong storage/sessions/").classes(
                    "text-sm text-slate-500 italic py-4"
                )
            else:
                with ui.column().classes("w-full max-h-[460px] overflow-y-auto gap-2.5"):
                    for s in sessions:
                        with ui.card().classes(
                            "w-full p-3 border border-slate-200 bg-slate-50 gap-1.5 rounded-lg"
                        ):
                            with ui.row().classes("w-full justify-between items-center"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(s["timestamp"]).classes(
                                        "text-xs font-mono font-bold text-slate-700"
                                    )
                                    st_color = (
                                        "emerald"
                                        if s["status"] == "COMPLETED"
                                        else "rose"
                                        if s["status"] in ("HALTED", "ABORTED")
                                        else "blue"
                                    )
                                    ui.badge(s["status"], color=st_color).classes(
                                        "text-xs font-mono"
                                    )
                                ui.label(f"Vòng lặp: {s['loops']}").classes(
                                    "text-xs font-mono text-slate-600"
                                )
                            with ui.row().classes(
                                "w-full justify-between items-center text-xs text-slate-600"
                            ):
                                ui.label(f"Repo: {s['repo']} ({s['branch']})").classes(
                                    "font-mono font-medium"
                                )
                                if s["pr_url"]:
                                    ui.link("Xem PR", s["pr_url"], new_tab=True).classes(
                                        "text-indigo-600 underline font-bold"
                                    )
                            if s["goal"]:
                                ui.label(f"Mục tiêu: {s['goal']}").classes(
                                    "text-xs text-slate-500 italic truncate"
                                )

                            with ui.row().classes("w-full justify-end"):
                                filename = s["filename"]

                                def make_detail_handler(fn: str = filename):
                                    return lambda: show_session_detail_dialog(fn)

                                ui.button(
                                    "Xem Log Sự Kiện",
                                    icon="visibility",
                                    on_click=make_detail_handler(filename),
                                ).props("flat dense text-xs text-indigo-600")

            with ui.row().classes("w-full justify-end pt-2 border-t"):
                ui.button("Đóng", on_click=hist_dlg.close).classes(
                    "bg-slate-800 text-white text-xs px-4 py-1.5 rounded"
                )
        hist_dlg.open()

    def show_session_detail_dialog(fn: str) -> None:
        det = load_session_details(fn)
        if not det:
            ui.notify(f"Không thể tải chi tiết phiên: {fn}", color="negative")
            return
        with ui.dialog() as detail_dlg, ui.card().classes("w-[750px] max-w-4xl p-5 gap-3"):
            with ui.row().classes("w-full justify-between items-center border-b pb-2"):
                ui.label(f"Chi tiết Telemetry: {fn}").classes("text-base font-bold text-slate-800")
                ui.button(icon="close", on_click=detail_dlg.close).props("flat round dense")

            evs = det.get("events", [])
            ev_box = ui.column().classes(
                "w-full h-80 overflow-y-auto bg-slate-950 p-3 rounded font-mono text-xs gap-1"
            )
            with ev_box:
                if not evs:
                    ui.label("Không có sự kiện ghi nhận.").classes("text-slate-400 italic")
                for ev in evs:
                    if isinstance(ev, dict):
                        src = str(ev.get("source", "log"))
                        msg = str(ev.get("message", ""))
                        c = (
                            "text-purple-300"
                            if src == "perplexity"
                            else "text-emerald-300"
                            if src == "chatgpt"
                            else "text-cyan-300"
                        )
                        ui.label(f"[{src.upper()}]: {msg}").classes(c)
            with ui.row().classes("w-full justify-end"):
                ui.button("Đóng", on_click=detail_dlg.close).classes(
                    "bg-slate-800 text-white text-xs px-4 py-1.5 rounded"
                )
        detail_dlg.open()

    modal = PreviewModal(
        on_approve=lambda payload: fsm.approve_step(payload),
        on_reject=lambda: fsm.abort(),
    )
    fsm.on_approval_required = lambda target, res: modal.show(target, fsm.pending_payload)

    start_btn.on_click(
        lambda: fsm.start_task(
            repo=repo_input.value,
            branch=branch_input.value,
            goal=goal_input.value,
            max_loops=int(loop_slider.value),
            auto_mode=auto_switch.value,
            timeout_seconds=int(timeout_select.value),
        )
    )
    resume_btn.on_click(lambda: fsm.resume_from_checkpoint())
    sync_btn.on_click(
        lambda: fsm.reconcile_and_resume(
            repo=repo_input.value,
            branch=branch_input.value,
            goal=goal_input.value,
            max_loops=int(loop_slider.value),
            auto_mode=auto_switch.value,
        )
    )
    retry_btn.on_click(lambda: fsm.retry_step())
    pause_btn.on_click(lambda: fsm.pause())
    stop_btn.on_click(lambda: fsm.stop())

    def handle_abort() -> None:
        fsm.abort()
        refresh_checkpoint_banner()

    abort_btn.on_click(handle_abort)

    return fsm
