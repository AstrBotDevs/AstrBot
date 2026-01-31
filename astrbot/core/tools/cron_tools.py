from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class CreateActiveCronTool(FunctionTool[AstrAgentContext]):
    name: str = "create_cron_job"
    description: str = (
        "Create a scheduled active agent task using a cron expression. "
        "Use this when the user asks for recurring tasks (e.g., daily reports)."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "cron_expression": {
                    "type": "string",
                    "description": "Cron expression defining when to trigger (e.g., '0 8 * * *').",
                },
                "note": {
                    "type": "string",
                    "description": "Instruction for the future agent run when the job triggers.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional job name for identification.",
                },
            },
            "required": ["cron_expression", "note"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."

        cron_expression = kwargs.get("cron_expression")
        note = str(kwargs.get("note", "")).strip()
        name = str(kwargs.get("name") or "").strip() or "active_agent_task"

        if not cron_expression or not note:
            return "error: cron_expression and note are required."

        payload = {
            "session": context.context.event.unified_msg_origin,
            "note": note,
        }

        job = await cron_mgr.add_active_job(
            name=name,
            cron_expression=str(cron_expression),
            payload=payload,
            description=note,
        )
        next_run = job.next_run_time
        return (
            f"Scheduled cron job {job.job_id} ({job.name}) with expression '{cron_expression}'. "
            f"Next run: {next_run}"
        )


@dataclass
class DeleteCronJobTool(FunctionTool[AstrAgentContext]):
    name: str = "delete_cron_job"
    description: str = "Delete a cron job by its job_id."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job_id returned when the job was created.",
                }
            },
            "required": ["job_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."
        job_id = kwargs.get("job_id")
        if not job_id:
            return "error: job_id is required."
        await cron_mgr.delete_job(str(job_id))
        return f"Deleted cron job {job_id}."


@dataclass
class ListCronJobsTool(FunctionTool[AstrAgentContext]):
    name: str = "list_cron_jobs"
    description: str = "List existing cron jobs for inspection."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "job_type": {
                    "type": "string",
                    "description": "Optional filter: basic or active_agent.",
                }
            },
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."
        job_type = kwargs.get("job_type")
        jobs = await cron_mgr.list_jobs(job_type)
        if not jobs:
            return "No cron jobs found."
        lines = []
        for j in jobs:
            lines.append(
                f"{j.job_id} | {j.name} | {j.job_type} | enabled={j.enabled} | next={j.next_run_time}"
            )
        return "\n".join(lines)


CREATE_CRON_JOB_TOOL = CreateActiveCronTool()
DELETE_CRON_JOB_TOOL = DeleteCronJobTool()
LIST_CRON_JOBS_TOOL = ListCronJobsTool()

__all__ = [
    "CREATE_CRON_JOB_TOOL",
    "DELETE_CRON_JOB_TOOL",
    "LIST_CRON_JOBS_TOOL",
    "CreateActiveCronTool",
    "DeleteCronJobTool",
    "ListCronJobsTool",
]
