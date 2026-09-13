import asyncio
import json
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List

from core.checkpoint_manager import (
    TaskCheckpoint,
    clear_checkpoint,
    load_checkpoint,
    reconcile_from_tabs,
    save_checkpoint,
)
from core.cdp_connector import CDPConnector
from core.config_loader import AppConfig, SelectorsConfig
from core.stream_detector import StreamDetector
from core.tag_protocol import AgentStatus, TagParseResult, parse_agent_output


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
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECONCILING = "RECONCILING"


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
        self.feature_branch: str = ""
        self.commit_sha: str = ""
        self.pr_url: str = ""
        self.pending_payload: str = ""
        self.target_agent_for_pending: str = ""
        self.last_attempted_agent: str = ""
        self.last_attempted_payload: str = ""
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

    async def ensure_cdp(self) -> bool:
        connected = await self.connector.connect()
        if not connected:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không thể kết nối tới trình duyệt qua cổng 9222!")
            return False
        p_tab, c_tab = await self.connector.find_tabs()
        if not p_tab or not c_tab:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không tìm thấy đủ tab Perplexity và ChatGPT.")
            return False
        return True

    async def start_task(
        self,
        repo: str,
        branch: str,
        goal: str,
        max_loops: int,
        auto_mode: bool = True,
        timeout_seconds: Optional[int] = None,
    ):
        self.current_repo = repo
        self.current_branch = branch
        self.current_goal = goal
        self.max_loops = max_loops
        self.auto_mode = auto_mode
        self.feature_branch = ""
        self.commit_sha = ""
        self.pr_url = ""
        if timeout_seconds:
            self.config.timeout_seconds = timeout_seconds
        self.loop_count = 0
        self.is_running = True
        self.session_events = []
        self.log("system", f"Bắt đầu tác vụ mới cho repo: {repo} (Nhánh: {branch})")
        if not await self.ensure_cdp():
            return
        asyncio.create_task(self._run_loop(start_agent="perplexity", start_payload=None))

    async def resume_from_checkpoint(self, checkpoint: Optional[TaskCheckpoint] = None):
        cp = checkpoint or load_checkpoint()
        if not cp:
            self.log("system", "Không tìm thấy checkpoint hợp lệ để khôi phục.")
            return
        self.current_repo = cp.repo
        self.current_branch = cp.branch
        self.current_goal = cp.goal
        self.loop_count = max(
            0,
            cp.loop_count - 1
            if cp.next_target_agent == "chatgpt" and cp.loop_count > 0
            else cp.loop_count,
        )
        self.max_loops = cp.max_loops
        self.auto_mode = cp.auto_mode
        self.feature_branch = cp.feature_branch
        self.commit_sha = cp.commit_sha
        self.pr_url = cp.pr_url
        self.is_running = True
        self.log(
            "system",
            "Khôi phục tiến trình từ Checkpoint: "
            f"Vòng lặp {cp.loop_count}, mục tiêu tiếp theo: {cp.next_target_agent.upper()}",
        )
        if self.pr_url:
            self.log("system", f"Đã ghi nhận PR: {self.pr_url} (Nhánh: {self.feature_branch})")
        if not await self.ensure_cdp():
            return
        asyncio.create_task(
            self._run_loop(
                start_agent=cp.next_target_agent,
                start_payload=cp.next_prompt_payload,
            )
        )

    async def retry_step(self):
        self.log("system", "Thực hiện thử lại bước hiện tại...")
        await self.resume_from_checkpoint()

    async def reconcile_and_resume(
        self,
        repo: str,
        branch: str,
        goal: str,
        max_loops: int = 5,
        auto_mode: bool = True,
    ):
        self.set_state(FSMState.RECONCILING)
        self.log("system", "Bắt đầu tự động quét và đồng bộ trạng thái từ các tab trình duyệt...")
        if not await self.ensure_cdp():
            return
        cp = await reconcile_from_tabs(
            p_tab=self.connector.perplexity_tab,
            c_tab=self.connector.chatgpt_tab,
            repo=repo,
            branch=branch,
            goal=goal,
            selectors=self.selectors,
            max_loops=max_loops,
            auto_mode=auto_mode,
        )
        save_checkpoint(cp)
        self.log(
            "system",
            f"Đồng bộ thành công: Trạng thái [{cp.status_label}], "
            f"Agent tiếp theo: [{cp.next_target_agent.upper()}].",
        )
        if cp.pr_url:
            self.log("system", f"Phát hiện PR hiện có: {cp.pr_url} (Branch: {cp.feature_branch})")
        await self.resume_from_checkpoint(cp)

    async def _run_loop(self, start_agent: str = "perplexity", start_payload: Optional[str] = None):
        try:
            p_lead_template = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
            c_dev_template = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")
            first_prompt = (
                f"{p_lead_template}\n\n[MỤC TIÊU BÀI TOÁN]:\n"
                f"Repository: {self.current_repo}\nBranch: {self.current_branch}\n"
                f"Yêu cầu: {self.current_goal}"
            )
            next_prompt = start_payload or first_prompt
            current_turn = start_agent
            while self.is_running and self.loop_count < self.max_loops:
                if current_turn == "perplexity":
                    self.loop_count += 1
                    self.log(
                        "system",
                        f"--- Bắt đầu Vòng lặp {self.loop_count} / {self.max_loops} ---",
                    )
                    self.set_state(FSMState.PERPLEXITY_SENDING)
                    self.last_attempted_agent = "perplexity"
                    self.last_attempted_payload = next_prompt
                    self.log("perplexity", "Gửi yêu cầu phân tích vào Perplexity...")
                    await self.detector.send_prompt(
                        self.connector.perplexity_tab, next_prompt, "perplexity"
                    )
                    self.set_state(FSMState.PERPLEXITY_WAITING)
                    raw_p_resp = await self.detector.wait_for_completion(
                        self.connector.perplexity_tab,
                        "perplexity",
                        on_progress=lambda msg: self.log("perplexity", msg),
                    )
                    self.set_state(FSMState.PERPLEXITY_PARSING)
                    p_result = parse_agent_output(raw_p_resp, source="perplexity")
                    self.log("perplexity", f"Nhận kết quả: {p_result.status.value}")
                    if p_result.status == AgentStatus.COMPLETED:
                        self.set_state(FSMState.TASK_FINISHED)
                        self.log("system", "Task đã được nghiệm thu hoàn tất!")
                        self._save_session("COMPLETED")
                        clear_checkpoint()
                        return
                    chatgpt_prompt = (
                        f"{c_dev_template}\n\n[TASK_SPEC FROM TECH LEAD]:\n"
                        f"{raw_p_resp}\n\n[TARGET REPO]: {self.current_repo}"
                    )
                    save_checkpoint(
                        TaskCheckpoint(
                            repo=self.current_repo,
                            branch=self.current_branch,
                            goal=self.current_goal,
                            loop_count=self.loop_count,
                            max_loops=self.max_loops,
                            auto_mode=self.auto_mode,
                            last_successful_agent="perplexity",
                            next_target_agent="chatgpt",
                            feature_branch=self.feature_branch,
                            commit_sha=self.commit_sha,
                            pr_url=self.pr_url,
                            last_raw_response=raw_p_resp,
                            next_prompt_payload=chatgpt_prompt,
                            status_label=p_result.status.value,
                        )
                    )
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
                    next_prompt = chatgpt_prompt
                    current_turn = "chatgpt"
                if current_turn == "chatgpt":
                    self.set_state(FSMState.CHATGPT_SENDING)
                    self.last_attempted_agent = "chatgpt"
                    self.last_attempted_payload = next_prompt
                    self.log("chatgpt", "Chuyển payload sang ChatGPT...")
                    await self.detector.send_prompt(
                        self.connector.chatgpt_tab, next_prompt, "chatgpt"
                    )
                    self.set_state(FSMState.CHATGPT_WAITING)
                    raw_c_resp = await self.detector.wait_for_completion(
                        self.connector.chatgpt_tab,
                        "chatgpt",
                        on_progress=lambda msg: self.log("chatgpt", msg),
                    )
                    self.set_state(FSMState.CHATGPT_PARSING)
                    c_result = parse_agent_output(raw_c_resp, source="chatgpt")
                    self.log("chatgpt", f"Nhận kết quả: {c_result.status.value}")
                    if c_result.payload:
                        self.feature_branch = (
                            getattr(c_result.payload, "branch", self.feature_branch)
                            or self.feature_branch
                        )
                        self.commit_sha = (
                            getattr(c_result.payload, "commit_sha", self.commit_sha)
                            or self.commit_sha
                        )
                        self.pr_url = (
                            getattr(c_result.payload, "pr_url", self.pr_url)
                            or self.pr_url
                        )
                    if c_result.status == AgentStatus.ERROR:
                        self.log("chatgpt", "ChatGPT báo lỗi, gửi lại Perplexity phân tích...")
                        next_prompt = (
                            f"[BÁO CÁO SỰ CỐ TỪ DEV]:\n{raw_c_resp}\n"
                            "Hãy phân tích nguyên nhân và cập nhật hướng dẫn sửa đổi."
                        )
                    else:
                        next_prompt = (
                            "[KẾT QUẢ PULL REQUEST TỪ DEV]:\n"
                            f"{raw_c_resp}\n"
                            "Hãy nghiệm thu mã nguồn này và xuất [STATUS: COMPLETED] "
                            "nếu đạt chuẩn hoặc [STATUS: NEEDS_REVISION] nếu cần sửa."
                        )
                    save_checkpoint(
                        TaskCheckpoint(
                            repo=self.current_repo,
                            branch=self.current_branch,
                            goal=self.current_goal,
                            loop_count=self.loop_count,
                            max_loops=self.max_loops,
                            auto_mode=self.auto_mode,
                            last_successful_agent="chatgpt",
                            next_target_agent="perplexity",
                            feature_branch=self.feature_branch,
                            commit_sha=self.commit_sha,
                            pr_url=self.pr_url,
                            last_raw_response=raw_c_resp,
                            next_prompt_payload=next_prompt,
                            status_label=c_result.status.value,
                        )
                    )
                    current_turn = "perplexity"
            if self.loop_count >= self.max_loops and self.is_running:
                self.set_state(FSMState.MAX_LOOPS_HALTED)
                self.log(
                    "system",
                    f"Đã chạm trần Max Loops ({self.max_loops}). Tạm dừng để người dùng duyệt tay.",
                )
                self._save_session("HALTED")
        except Exception as e:
            err_msg = str(e)
            self.set_state(FSMState.RECOVERY_REQUIRED)
            self.is_running = False
            self.log(
                "system",
                f"Sự cố thực thi: {err_msg}. Đã lưu trạng thái phục hồi (Checkpoint).",
            )
            self.log(
                "system",
                "Hệ thống đang chờ lệnh cứu hộ: bạn có thể bấm 'Thử lại bước' "
                "(Retry) hoặc 'Tiếp tục từ Checkpoint' (Resume).",
            )
            save_checkpoint(
                TaskCheckpoint(
                    repo=self.current_repo,
                    branch=self.current_branch,
                    goal=self.current_goal,
                    loop_count=self.loop_count,
                    max_loops=self.max_loops,
                    auto_mode=self.auto_mode,
                    last_successful_agent=self.last_attempted_agent,
                    next_target_agent=self.last_attempted_agent or "perplexity",
                    feature_branch=self.feature_branch,
                    commit_sha=self.commit_sha,
                    pr_url=self.pr_url,
                    next_prompt_payload=self.last_attempted_payload,
                    status_label="RECOVERY_REQUIRED",
                    error_message=err_msg,
                )
            )

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
        clear_checkpoint()

    def _save_session(self, final_status: str):
        Path("storage/sessions").mkdir(parents=True, exist_ok=True)
        filename = (
            f"storage/sessions/{int(time.time())}_"
            f"{self.current_repo.replace('/', '_')}.json"
        )
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "status": final_status,
                    "repo": self.current_repo,
                    "branch": self.current_branch,
                    "goal": self.current_goal,
                    "loops": self.loop_count,
                    "feature_branch": self.feature_branch,
                    "commit_sha": self.commit_sha,
                    "pr_url": self.pr_url,
                    "events": self.session_events,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
