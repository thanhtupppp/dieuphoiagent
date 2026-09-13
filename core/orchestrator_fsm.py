import asyncio
from typing import Any, Callable, Dict, List, Optional

from core.cdp_connector import CDPConnector
from core.checkpoint_manager import (
    TaskCheckpoint,
    clear_checkpoint,
    load_checkpoint,
    reconcile_from_tabs,
    save_checkpoint,
)
from core.config_loader import AppConfig, SelectorsConfig
from core.fsm import (
    CircuitBreaker,
    FSMState,
    RunContext,
    run_fsm,
    save_session_record,
)
from core.providers.base import AgentProvider
from core.providers.cdp_provider import CdpProvider
from core.stream_detector import StreamDetector
from core.tag_protocol import TagParseResult


class OrchestratorFSM:
    """Facade orchestrator coordinating agent turns, checkpoints, and telemetry.

    Delegates internal state transition handling to the core.fsm modular engine.
    """

    def __init__(
        self,
        config: AppConfig,
        selectors: SelectorsConfig,
        provider: Optional[AgentProvider] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.config = config
        self.selectors = selectors
        self.state: FSMState = FSMState.IDLE
        self.loop_count: int = 0
        self.max_loops: int = config.max_loops
        self.auto_mode: bool = True
        self.is_running: bool = False
        self.circuit_breaker = circuit_breaker or CircuitBreaker(max_failures=5)
        self.provider: AgentProvider = (
            provider if provider is not None else CdpProvider(config, selectors)
        )
        if isinstance(self.provider, CdpProvider):
            self.connector = self.provider.connector
            self.detector = self.provider.detector
        else:
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
        self._active_context: Optional[RunContext] = None

    def set_state(self, new_state: FSMState) -> None:
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def log(self, source: str, message: str) -> None:
        self.session_events.append({"source": source, "message": message})
        if self.on_log:
            self.on_log(source, message)

    async def ensure_cdp(self) -> bool:
        try:
            healthy = await self.provider.health_check()
            if not healthy:
                self.set_state(FSMState.CDP_ERROR)
                self.log("system", "Không tìm thấy đủ tab Perplexity và ChatGPT.")
                return False
            return True
        except Exception as e:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", f"Lỗi kết nối CDP: {e}")
            return False

    async def start_task(
        self,
        repo: str,
        branch: str,
        goal: str,
        max_loops: int,
        auto_mode: bool = True,
        timeout_seconds: Optional[int] = None,
    ) -> None:
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

    async def resume_from_checkpoint(self, checkpoint: Optional[TaskCheckpoint] = None) -> None:
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

    async def retry_step(self) -> None:
        self.log("system", "Thực hiện thử lại bước hiện tại...")
        self.circuit_breaker.reset()
        await self.resume_from_checkpoint()

    async def reconcile_and_resume(
        self,
        repo: str,
        branch: str,
        goal: str,
        max_loops: int = 5,
        auto_mode: bool = True,
    ) -> None:
        self.set_state(FSMState.RECONCILING)
        self.log("system", "Bắt đầu tự động quét và đồng bộ trạng thái từ các tab trình duyệt...")
        if not await self.ensure_cdp():
            return
        p_tab = getattr(self.connector, "perplexity_tab", None)
        c_tab = getattr(self.connector, "chatgpt_tab", None)
        if not p_tab or not c_tab:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không tìm thấy đủ tab Perplexity và ChatGPT để đồng bộ.")
            return
        cp = await reconcile_from_tabs(
            p_tab=p_tab,
            c_tab=c_tab,
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

    async def _run_loop(self, start_agent: str = "perplexity", start_payload: Optional[str] = None) -> None:
        """Delegate state transition execution to core.fsm.machine.run_fsm."""
        ctx = RunContext(
            current_turn=start_agent,
            loop_count=self.loop_count,
            max_loops=self.max_loops,
            auto_mode=self.auto_mode,
            is_running=self.is_running,
            state=self.state,
            current_repo=self.current_repo,
            current_branch=self.current_branch,
            current_goal=self.current_goal,
            feature_branch=self.feature_branch,
            commit_sha=self.commit_sha,
            pr_url=self.pr_url,
            next_prompt=start_payload or "",
            pending_payload=self.pending_payload,
            approval_event=self.approval_event,
            on_state_change=self.set_state,
            on_log=self.log,
            on_approval_required=self.on_approval_required,
            logs=self.session_events,
            save_checkpoint_fn=lambda cp: save_checkpoint(cp),
            clear_checkpoint_fn=lambda: clear_checkpoint(),
        )
        self._active_context = ctx

        await run_fsm(ctx, self.provider, circuit_breaker=self.circuit_breaker)

        # Synchronize context back to OrchestratorFSM properties
        self.loop_count = ctx.loop_count
        self.state = ctx.state
        self.is_running = ctx.is_running
        self.feature_branch = ctx.feature_branch
        self.commit_sha = ctx.commit_sha
        self.pr_url = ctx.pr_url
        self.pending_payload = ctx.pending_payload
        self.target_agent_for_pending = ctx.target_agent_for_pending
        self.last_attempted_agent = ctx.last_attempted_agent
        self.last_attempted_payload = ctx.last_attempted_payload

    def approve_step(self, modified_payload: Optional[str] = None) -> None:
        if modified_payload:
            self.pending_payload = modified_payload
            if self._active_context:
                self._active_context.pending_payload = modified_payload
        self.approval_event.set()

    def pause(self) -> None:
        self.set_state(FSMState.PAUSED)
        self.log("system", "Hệ thống tạm dừng.")

    def stop(self) -> None:
        self.is_running = False
        if self._active_context:
            self._active_context.is_running = False
        self.approval_event.set()
        self.set_state(FSMState.IDLE)
        self.log("system", "Hệ thống đã dừng khẩn cấp.")

    def abort(self) -> None:
        self.is_running = False
        if self._active_context:
            self._active_context.is_running = False
        self.approval_event.set()
        self.set_state(FSMState.ABORTED)
        self.log("system", "Tác vụ đã bị hủy bỏ (Aborted).")
        self._save_session("ABORTED")
        clear_checkpoint()

    def _save_session(self, final_status: str) -> None:
        ctx = self._active_context
        if not ctx:
            ctx = RunContext(
                current_repo=self.current_repo,
                current_branch=self.current_branch,
                current_goal=self.current_goal,
                loop_count=self.loop_count,
                feature_branch=self.feature_branch,
                commit_sha=self.commit_sha,
                pr_url=self.pr_url,
                logs=self.session_events,
            )
        save_session_record(ctx, final_status)

    async def close(self) -> None:
        await self.provider.close()
