import asyncio
import json
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
from core.config_loader import AppConfig, SelectorsConfig
from core.cdp_connector import CDPConnector
from core.stream_detector import StreamDetector
from core.tag_protocol import parse_agent_output, AgentStatus, TagParseResult

class FSMState(str, Enum):
    IDLE = "IDLE"
    PERPLEXITY_SENDING = "PERPLEXITY_SENDING"
    PERPLEXITY_WAITING = "PERPLEXITY_WAITING"
    PERPLEXITY_PARSING = "PERPLEXITY_PARSING"
    WAITING_USER_APPROVAL = "WAITING_USER_APPROVAL"
    CHATGPT_SENDING = "CHATGPT_SENDING"
    CHATGPT_WAITING = "CHATGPT_WAITING"
    CHATGPT_PARSING = "CHATGPT_PARSING"
    MAX_LOOPS_HALTED = "MAX_LOOPS_HALTED"
    TASK_FINISHED = "TASK_FINISHED"
    PAUSED = "PAUSED"
    ABORTED = "ABORTED"
    RECONNECTING = "RECONNECTING"
    CDP_ERROR = "CDP_ERROR"

class OrchestratorFSM:
    def __init__(self, config: AppConfig, selectors: SelectorsConfig):
        self.config = config
        self.selectors = selectors
        self.state: FSMState = FSMState.IDLE
        self.loop_count: int = 0
        self.max_loops: int = config.max_loops
        self.auto_mode: bool = True
        self.is_running: bool = False
        
        self.connector = CDPConnector(config, selectors)
        self.detector = StreamDetector(config, selectors)
        
        self.on_state_change: Optional[Callable[[FSMState], None]] = None
        self.on_log: Optional[Callable[[str, str], None]] = None
        self.on_approval_required: Optional[Callable[[str, TagParseResult], None]] = None
        
        self.current_repo: str = ""
        self.current_branch: str = ""
        self.current_goal: str = ""
        self.pending_payload: str = ""
        self.target_agent_for_pending: str = ""
        self.approval_event = asyncio.Event()
        self.session_events: List[Dict[str, Any]] = []

    def set_state(self, new_state: FSMState):
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def log(self, source: str, message: str):
        self.session_events.append({"timestamp": time.time(), "source": source, "message": message})
        if self.on_log:
            self.on_log(source, message)

    async def start_task(self, repo: str, branch: str, goal: str, max_loops: int, auto_mode: bool = True, timeout_seconds: Optional[int] = None):
        self.current_repo = repo
        self.current_branch = branch
        self.current_goal = goal
        self.max_loops = max_loops
        self.auto_mode = auto_mode
        if timeout_seconds:
            self.config.timeout_seconds = timeout_seconds
        self.loop_count = 0
        self.is_running = True
        self.session_events = []

        self.log("system", f"Bắt đầu tác vụ cho repo: {repo} (Nhánh: {branch})")
        connected = await self.connector.connect()
        if not connected:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không thể kết nối tới trình duyệt qua cổng 9222!")
            return

        p_tab, c_tab = await self.connector.find_tabs()
        if not p_tab or not c_tab:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không tìm thấy đủ tab Perplexity và ChatGPT.")
            return

        asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        try:
            p_lead_template = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
            first_prompt = f"{p_lead_template}\n\n[MỤC TIÊU BÀI TOÁN]:\nRepository: {self.current_repo}\nBranch: {self.current_branch}\nYêu cầu: {self.current_goal}"
            
            next_prompt = first_prompt
            while self.is_running and self.loop_count < self.max_loops:
                self.loop_count += 1
                self.log("system", f"--- Bắt đầu Vòng lặp {self.loop_count} / {self.max_loops} ---")

                # 1. Gửi Perplexity
                self.set_state(FSMState.PERPLEXITY_SENDING)
                self.log("perplexity", "Gửi yêu cầu phân tích vào Perplexity...")
                await self.detector.send_prompt(self.connector.perplexity_tab, next_prompt, "perplexity")

                self.set_state(FSMState.PERPLEXITY_WAITING)
                raw_p_resp = await self.detector.wait_for_completion(
                    self.connector.perplexity_tab,
                    "perplexity",
                    on_progress=lambda msg: self.log("perplexity", msg)
                )
                
                self.set_state(FSMState.PERPLEXITY_PARSING)
                p_result = parse_agent_output(raw_p_resp, source="perplexity")
                self.log("perplexity", f"Nhận kết quả: {p_result.status.value}")

                if p_result.status == AgentStatus.COMPLETED:
                    self.set_state(FSMState.TASK_FINISHED)
                    self.log("system", "Task đã được nghiệm thu hoàn tất!")
                    self._save_session("COMPLETED")
                    return

                # Chờ duyệt nếu ở chế độ Step-by-step
                c_dev_template = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")
                chatgpt_prompt = f"{c_dev_template}\n\n[TASK_SPEC FROM TECH LEAD]:\n{raw_p_resp}\n\n[TARGET REPO]: {self.current_repo}"
                
                if not self.auto_mode:
                    self.set_state(FSMState.WAITING_USER_APPROVAL)
                    self.pending_payload = chatgpt_prompt
                    self.target_agent_for_pending = "chatgpt"
                    self.approval_event.clear()
                    if self.on_approval_required:
                        self.on_approval_required("ChatGPT", p_result)
                    await self.approval_event.wait()
                    chatgpt_prompt = self.pending_payload

                if not self.is_running:
                    break

                # 2. Gửi ChatGPT
                self.set_state(FSMState.CHATGPT_SENDING)
                self.log("chatgpt", "Chuyển payload sang ChatGPT...")
                await self.detector.send_prompt(self.connector.chatgpt_tab, chatgpt_prompt, "chatgpt")

                self.set_state(FSMState.CHATGPT_WAITING)
                raw_c_resp = await self.detector.wait_for_completion(
                    self.connector.chatgpt_tab,
                    "chatgpt",
                    on_progress=lambda msg: self.log("chatgpt", msg)
                )

                self.set_state(FSMState.CHATGPT_PARSING)
                c_result = parse_agent_output(raw_c_resp, source="chatgpt")
                self.log("chatgpt", f"Nhận kết quả: {c_result.status.value}")

                if c_result.status == AgentStatus.ERROR:
                    self.log("chatgpt", "ChatGPT báo lỗi, gửi lại Perplexity phân tích...")
                    next_prompt = f"[BÁO CÁO SỰ CỐ TỪ DEV]:\n{raw_c_resp}\nHãy phân tích nguyên nhân và cập nhật hướng dẫn sửa đổi."
                else:
                    next_prompt = f"[KẾT QUẢ PULL REQUEST TỪ DEV]:\n{raw_c_resp}\nHãy nghiệm thu mã nguồn này và xuất [STATUS: COMPLETED] nếu đạt chuẩn hoặc [STATUS: NEEDS_REVISION] nếu cần sửa."

            if self.loop_count >= self.max_loops and self.is_running:
                self.set_state(FSMState.MAX_LOOPS_HALTED)
                self.log("system", f"Đã chạm trần Max Loops ({self.max_loops}). Tạm dừng để người dùng duyệt tay.")
                self._save_session("HALTED")
        except Exception as e:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", f"Lỗi thực thi trong vòng lặp: {str(e)}")

    def approve_step(self, modified_payload: Optional[str] = None):
        if modified_payload:
            self.pending_payload = modified_payload
        self.approval_event.set()

    def pause(self):
        self.set_state(FSMState.PAUSED)
        self.log("system", "Hệ thống tạm dừng.")

    def stop(self):
        self.is_running = False
        self.approval_event.set()
        self.set_state(FSMState.IDLE)
        self.log("system", "Hệ thống đã dừng khẩn cấp.")

    def abort(self):
        self.is_running = False
        self.approval_event.set()
        self.set_state(FSMState.ABORTED)
        self.log("system", "Tác vụ đã bị hủy bỏ (Aborted).")
        self._save_session("ABORTED")

    def _save_session(self, final_status: str):
        Path("storage/sessions").mkdir(parents=True, exist_ok=True)
        filename = f"storage/sessions/{int(time.time())}_{self.current_repo.replace('/', '_')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "repo": self.current_repo,
                "branch": self.current_branch,
                "goal": self.current_goal,
                "loops": self.loop_count,
                "final_status": final_status,
                "events": self.session_events
            }, f, ensure_ascii=False, indent=2)
