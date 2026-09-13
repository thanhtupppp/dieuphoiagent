from abc import ABC, abstractmethod
from pathlib import Path

from core.checkpoint_manager import TaskCheckpoint
from core.fsm.context import FSMState, RunContext
from core.providers.base import AgentProvider, AgentRequest, AgentRole
from core.tag_protocol import AgentStatus, parse_agent_output


class StateHandler(ABC):
    @abstractmethod
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        """Execute state logic, returning the next state name."""


class PerplexityLeadHandler(StateHandler):
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        if not context.is_running:
            return "done"

        p_lead_template = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
        c_dev_template = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")

        first_prompt = (
            f"{p_lead_template}\n\n[MỤC TIÊU BÀI TOÁN]:\n"
            f"Repository: {context.current_repo}\nBranch: {context.current_branch}\n"
            f"Yêu cầu: {context.current_goal}"
        )
        prompt_to_send = context.next_prompt or first_prompt

        context.loop_count += 1
        context.log(
            "system",
            f"--- Bắt đầu Vòng lặp {context.loop_count} / {context.max_loops} ---",
        )

        context.set_state(FSMState.PERPLEXITY_SENDING)
        context.last_attempted_agent = "perplexity"
        context.last_attempted_payload = prompt_to_send
        context.log("perplexity", "Gửi yêu cầu phân tích vào Perplexity...")

        context.set_state(FSMState.PERPLEXITY_WAITING)
        resp = await provider.send(
            AgentRequest(
                role=AgentRole.TECH_LEAD,
                system_prompt="",
                user_prompt=prompt_to_send,
                on_progress=lambda msg: context.log("perplexity", msg),
            )
        )
        raw_p_resp = resp.content
        context.last_raw_response = raw_p_resp

        context.set_state(FSMState.PERPLEXITY_PARSING)
        p_result = parse_agent_output(raw_p_resp, source="perplexity")
        context.log("perplexity", f"Nhận kết quả: {p_result.status.value}")

        if p_result.status == AgentStatus.COMPLETED:
            context.set_state(FSMState.TASK_FINISHED)
            context.log("system", "Task đã được nghiệm thu hoàn tất!")
            context.clear_checkpoint()
            return "done"

        chatgpt_prompt = (
            f"{c_dev_template}\n\n[TASK_SPEC FROM TECH LEAD]:\n"
            f"{raw_p_resp}\n\n[TARGET REPO]: {context.current_repo}"
        )

        context.save_checkpoint(
            TaskCheckpoint(
                repo=context.current_repo,
                branch=context.current_branch,
                goal=context.current_goal,
                loop_count=context.loop_count,
                max_loops=context.max_loops,
                auto_mode=context.auto_mode,
                last_successful_agent="perplexity",
                next_target_agent="chatgpt",
                feature_branch=context.feature_branch,
                commit_sha=context.commit_sha,
                pr_url=context.pr_url,
                last_raw_response=raw_p_resp,
                next_prompt_payload=chatgpt_prompt,
                status_label=p_result.status.value,
            )
        )

        if not context.auto_mode:
            context.pending_payload = chatgpt_prompt
            context.target_agent_for_pending = "chatgpt"
            return "approval"

        context.next_prompt = chatgpt_prompt
        return "chatgpt"


class ApprovalHandler(StateHandler):
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        context.set_state(FSMState.WAITING_USER_APPROVAL)
        context.approval_event.clear()
        if context.on_approval_required:
            p_result = parse_agent_output(context.last_raw_response, source="perplexity")
            context.on_approval_required("ChatGPT", p_result)

        await context.approval_event.wait()
        if not context.is_running:
            return "done"

        context.next_prompt = context.pending_payload
        return "chatgpt"


class ChatGptDevHandler(StateHandler):
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        if not context.is_running:
            return "done"

        context.set_state(FSMState.CHATGPT_SENDING)
        context.last_attempted_agent = "chatgpt"
        context.last_attempted_payload = context.next_prompt
        context.log("chatgpt", "Chuyển payload sang ChatGPT...")

        context.set_state(FSMState.CHATGPT_WAITING)
        resp = await provider.send(
            AgentRequest(
                role=AgentRole.CORE_DEV,
                system_prompt="",
                user_prompt=context.next_prompt,
                on_progress=lambda msg: context.log("chatgpt", msg),
            )
        )
        raw_c_resp = resp.content
        context.last_raw_response = raw_c_resp

        context.set_state(FSMState.CHATGPT_PARSING)
        c_result = parse_agent_output(raw_c_resp, source="chatgpt")
        context.log("chatgpt", f"Nhận kết quả: {c_result.status.value}")

        if c_result.payload:
            context.feature_branch = (
                getattr(c_result.payload, "branch", context.feature_branch)
                or context.feature_branch
            )
            context.commit_sha = (
                getattr(c_result.payload, "commit_sha", context.commit_sha)
                or context.commit_sha
            )
            context.pr_url = (
                getattr(c_result.payload, "pr_url", context.pr_url)
                or context.pr_url
            )

        if c_result.status == AgentStatus.ERROR:
            context.log("chatgpt", "ChatGPT báo lỗi, gửi lại Perplexity phân tích...")
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

        context.next_prompt = next_prompt

        context.save_checkpoint(
            TaskCheckpoint(
                repo=context.current_repo,
                branch=context.current_branch,
                goal=context.current_goal,
                loop_count=context.loop_count,
                max_loops=context.max_loops,
                auto_mode=context.auto_mode,
                last_successful_agent="chatgpt",
                next_target_agent="perplexity",
                feature_branch=context.feature_branch,
                commit_sha=context.commit_sha,
                pr_url=context.pr_url,
                last_raw_response=raw_c_resp,
                next_prompt_payload=next_prompt,
                status_label=c_result.status.value,
            )
        )

        return "perplexity"
