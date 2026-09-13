from nicegui import ui

from core.checkpoint_manager import load_checkpoint
from core.config_loader import load_config, load_selectors
from core.orchestrator_fsm import FSMState, OrchestratorFSM
from ui.log_streamer import LogStreamer
from ui.preview_modal import PreviewModal


def build_ui():
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    fsm = OrchestratorFSM(config, selectors)
    streamer = LogStreamer()
    ui.page_title("AI Agent Browser Orchestrator")

    def fsm_log(source, msg):
        streamer.push(source, msg)

    fsm.on_log = fsm_log

    with ui.header().classes("bg-slate-900 text-white p-4 flex justify-between items-center shadow-md"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("smart_toy", size="md").classes("text-indigo-400")
            ui.label("AI AGENT BROWSER ORCHESTRATOR").classes("text-lg font-bold tracking-wider")
        with ui.row().classes("items-center gap-3"):
            ui.badge("CDP: Port 9222", color="emerald").classes("px-3 py-1 text-xs font-mono")

    with ui.row().classes("w-full p-4 gap-6 items-start"):
        with ui.column().classes("w-5/12 bg-white p-5 rounded-xl border border-slate-200 shadow-sm gap-4"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("tune", size="sm").classes("text-indigo-600")
                ui.label("Cấu hình Nhiệm vụ").classes("text-base font-semibold text-slate-800")
            checkpoint_card = ui.card().classes("w-full bg-indigo-50 border border-indigo-200 p-3 rounded-lg")
            with checkpoint_card:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("history", size="xs").classes("text-indigo-600")
                    cp_label = ui.label("Kiểm tra Checkpoint...").classes("text-xs font-medium text-indigo-900 font-mono")

            def refresh_checkpoint_banner():
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
            repo_input = ui.input(label="GitHub Repository (vd: owner/repo)", value="thanhtupppp/nguyencuufacepython").classes("w-full")
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
            auto_switch = ui.switch("Chạy tự động (Auto-pilot)", value=True).classes("text-sm text-slate-700 font-medium")
            ui.separator().classes("my-1")
            with ui.row().classes("items-center gap-2"):
                ui.icon("play_circle", size="sm").classes("text-indigo-600")
                ui.label("Điều khiển Vận hành & Cứu hộ").classes("text-sm font-semibold text-slate-700")
            with ui.row().classes("w-full gap-2"):
                start_btn = ui.button("Bắt đầu mới", color="indigo-600", icon="play_arrow").classes("flex-1 text-white font-medium py-2 rounded-lg")
                resume_btn = ui.button("Tiếp tục (Resume)", color="teal-600", icon="fast_forward").classes("flex-1 text-white font-medium py-2 rounded-lg")
            with ui.row().classes("w-full gap-2"):
                sync_btn = ui.button("Đồng bộ từ Browser", color="sky-600", icon="sync").classes("flex-1 text-white font-medium py-2 rounded-lg")
                retry_btn = ui.button("Thử lại bước (Retry)", color="blue-600", icon="refresh").classes("flex-1 text-white font-medium py-2 rounded-lg")
            with ui.row().classes("w-full gap-2"):
                pause_btn = ui.button("Tạm dừng", color="amber-600", icon="pause").classes("flex-1 text-white font-medium py-2 rounded-lg")
                stop_btn = ui.button("Dừng khẩn", color="rose-600", icon="stop").classes("flex-1 text-white font-medium py-2 rounded-lg")
            abort_btn = ui.button("Hủy bỏ & Reset Checkpoint", color="slate-700", icon="cancel").classes("w-full text-white font-medium py-2 rounded-lg mt-1")

        with ui.column().classes("w-6/12 bg-white p-5 rounded-xl border border-slate-200 shadow-sm gap-4 flex-1"):
            with ui.row().classes("w-full justify-between items-center border-b border-slate-100 pb-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.label("Trạng thái:").classes("text-sm font-semibold text-slate-700")
                    state_badge = ui.badge("IDLE", color="slate").classes("px-3 py-1 font-mono text-xs font-bold")
                with ui.row().classes("items-center gap-2"):
                    ui.label("Vòng lặp:").classes("text-sm font-semibold text-slate-700")
                    loop_badge = ui.badge("0 / 5", color="blue").classes("px-3 py-1 font-mono text-xs font-bold")

            def on_state_update(st: FSMState):
                state_badge.text = st.value
                if st == FSMState.TASK_FINISHED:
                    state_badge.color = "emerald"
                elif st in (FSMState.RECOVERY_REQUIRED, FSMState.CDP_ERROR, FSMState.ABORTED):
                    state_badge.color = "rose"
                elif st in (FSMState.PAUSED, FSMState.WAITING_USER_APPROVAL):
                    state_badge.color = "amber"
                elif st == FSMState.RECONCILING:
                    state_badge.color = "cyan"
                else:
                    state_badge.color = "indigo"
                loop_badge.text = f"{fsm.loop_count} / {fsm.max_loops}"
                refresh_checkpoint_banner()

            fsm.on_state_change = on_state_update
            with ui.tabs().classes("w-full border-b border-slate-200 text-slate-600"):
                ui.tab("Tất cả Log")
                ui.tab("Perplexity (Lead)")
                ui.tab("ChatGPT (Dev)")
            log_container = ui.column().classes("w-full h-[440px] overflow-y-auto bg-slate-950 text-slate-200 p-4 rounded-lg font-mono text-xs gap-1.5 shadow-inner")

            def add_log_ui(item):
                color = "text-purple-300" if item["source"] == "perplexity" else "text-emerald-300" if item["source"] == "chatgpt" else "text-cyan-300"
                with log_container:
                    ui.label(f"[{item['timestamp']}] [{item['source'].upper()}]: {item['message']}").classes(color)

            streamer.subscribe(add_log_ui)
            with ui.row().classes("w-full justify-between items-center mt-1"):
                ui.button("Xóa Log", on_click=lambda: (streamer.clear(), log_container.clear())).props("flat text-slate-500 text-xs")
                ui.button("Lưu phiên (Export)", on_click=lambda: ui.notify("Dữ liệu phiên đã được tự động lưu vào storage/sessions/", color="positive")).props("flat text-indigo-600 text-xs")

    modal = PreviewModal(
        on_approve=lambda payload: fsm.approve_step(payload),
        on_reject=lambda: fsm.abort(),
    )
    fsm.on_approval_required = lambda target, res: modal.show(target, fsm.pending_payload)
    start_btn.on_click(lambda: fsm.start_task(
        repo=repo_input.value,
        branch=branch_input.value,
        goal=goal_input.value,
        max_loops=int(loop_slider.value),
        auto_mode=auto_switch.value,
        timeout_seconds=int(timeout_select.value),
    ))
    resume_btn.on_click(lambda: fsm.resume_from_checkpoint())
    sync_btn.on_click(lambda: fsm.reconcile_and_resume(
        repo=repo_input.value,
        branch=branch_input.value,
        goal=goal_input.value,
        max_loops=int(loop_slider.value),
        auto_mode=auto_switch.value,
    ))
    retry_btn.on_click(lambda: fsm.retry_step())
    pause_btn.on_click(lambda: fsm.pause())
    stop_btn.on_click(lambda: fsm.stop())
    abort_btn.on_click(lambda: (fsm.abort(), refresh_checkpoint_banner()))
    return fsm
