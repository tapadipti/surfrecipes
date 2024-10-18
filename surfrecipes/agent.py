import logging
import os
import time
import traceback
from typing import Final, List, Optional, Tuple, Type

from agentdesk.device_v1 import Desktop
from devicebay import Device
from pydantic import BaseModel
from rich.console import Console
from rich.json import JSON
from skillpacks.server.models import V1ActionSelection, V1EnvState
from skillpacks import EnvState
from surfkit.agent import TaskAgent
from taskara import Task, TaskStatus
from tenacity import before_sleep_log, retry, stop_after_attempt
from threadmem import RoleMessage, RoleThread
from toolfuse.util import AgentUtils

from .tool import SurfRecipesTool, router

logging.basicConfig(level=logging.INFO)
logger: Final = logging.getLogger(__name__)
logger.setLevel(int(os.getenv("LOG_LEVEL", str(logging.DEBUG))))

console = Console(force_terminal=True)


class SurfRecipesConfig(BaseModel):
    pass


class SurfRecipes(TaskAgent):
    """An AI agent that finds recipes"""

    def solve_task(
        self,
        task: Task,
        device: Optional[Device] = None,
        max_steps: int = 30,
    ) -> Task:
        """Solve a task

        Args:
            task (Task): Task to solve.
            max_steps (int, optional): Max steps to try and solve. Defaults to 30.

        Returns:
            Task: The task
        """

        # Post a message to the default thread to let the user know the task is in progress
        task.post_message("assistant", f"Starting task '{task.description}'")

        # Create threads in the task to update the user
        console.print("creating threads...")
        task.ensure_thread("debug")
        task.post_message("assistant", f"I'll post debug messages here", thread="debug")

        recipetool = SurfRecipesTool(task=task)

        tools = recipetool.json_schema()
        console.print("tools: ", style="purple")
        console.print(JSON.from_data(tools))

        # Create our thread and start with a system prompt
        thread = RoleThread()
        thread.post(
            role="user",
            msg=(
                "You are a helpful AI assistant that analyzes user requirements and suggests actions that must be executed to meet those requirements."
                "You will receive details of a task and your job is to suggest what action should be taken next."
                f"The actions available to you are {tools}."
                "When you respond, always give a raw JSON adhering to the following schema and with the correct action called."
                f"Schema: {V1ActionSelection.model_json_schema()}"
                "If no further action is needed, return 'result' as the action_name."
                "Let me know when you are ready and I'll send you the user requirement."
            ),
        )
        console.print(f"thread messages: {thread.messages()}", style="blue")
        response = router.chat(thread, namespace="system")
        console.print(f"system prompt response: {response}", style="blue")
        thread.add_msg(response.msg)

        # The initial state is the task description itself.
        current_state = task.description

        # Loop to run actions
        for i in range(max_steps):
            console.print(f"-------step {i + 1}", style="green")

            try:
                thread, current_state, done = self.take_action(recipetool, task, thread, current_state)
            except Exception as e:
                console.print(f"Error: {e}", style="red")
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.save()
                task.post_message("assistant", f"❗ Error taking action: {e}")
                return task

            if done:
                console.print("task is done", style="green")
                return task

            time.sleep(2)

        task.status = TaskStatus.FAILED
        task.save()
        task.post_message("assistant", "❗ Max steps reached without solving task")
        console.print("Reached max steps without solving task", style="red")

        return task

    @retry(
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.INFO),
    )
    def take_action(
        self,
        recipetool: SurfRecipesTool,
        task: Task,
        thread: RoleThread,
        current_state: dict,
    ) -> Tuple[RoleThread, dict, bool]:
        """Take an action

        Args:
            recipetool (SurfRecipesTool): Surf recipes tool
            task (str): Task to accomplish
            thread (RoleThread): Role thread for the task

        Returns:
            bool: Whether the task is complete
        """
        try:
            # Check to see if the task has been cancelled
            if task.remote:
                task.refresh()
                console.print("task status: ", task.status.value)
            if (
                task.status == TaskStatus.CANCELING
                or task.status == TaskStatus.CANCELED
            ):
                console.print(f"task is {task.status}", style="red")
                if task.status == TaskStatus.CANCELING:
                    task.status = TaskStatus.CANCELED
                    task.save()
                return thread, current_state, True

            console.print("taking action...", style="white")

            # Create a copy of the thread, and remove old images
            _thread = thread.copy()
            _thread.remove_images()

            # Craft the message asking the MLLM for an action
            msg = RoleMessage(
                role="user",
                text=(f"Your current task is {current_state}. Please select an action from the provided schema."),
            )
            _thread.add_msg(msg)

            # Make the action selection
            response = router.chat(
                _thread,
                namespace="action",
                expect=V1ActionSelection,
                agent_id=self.name(),
            )
            task.add_prompt(response.prompt)

            try:
                # Post to the user letting them know what the model selected
                selection = response.parsed
                if not selection:
                    raise ValueError("No action selection parsed")

                task.post_message("assistant", f"👁️ {selection.observation}")
                task.post_message("assistant", f"💡 {selection.reason}")
                console.print(f"action selection: ", style="white")
                console.print(JSON.from_data(selection.model_dump()))

                task.post_message(
                    "assistant",
                    f"▶️ Taking action '{selection.action.name}' with parameters: {selection.action.parameters}",
                )

            except Exception as e:
                console.print(f"Response failed to parse: {e}", style="red")
                raise

            # The agent will return 'result' if it believes it's finished
            if selection.action.name == "result":
                console.print("final result: ", style="green")
                console.print(JSON.from_data(selection.action.parameters))
                task.post_message(
                    "assistant",
                    f"✅ I think the task is done, please review the result.",
                )
                task.status = TaskStatus.FINISHED
                task.save()
                return _thread, current_state, True

            # Find the selected action in the tool
            action = recipetool.find_action(selection.action.name)
            console.print(f"found action: {action}", style="blue")
            if not action:
                console.print(f"action returned not found: {selection.action.name}")
                raise SystemError("action not found")

            # Take the selected action
            try:
                action_response = recipetool.use(action, **selection.action.parameters)
            except Exception as e:
                raise ValueError(f"Trouble using action: {e}")

            console.print(f"action output: {action_response}", style="blue")
            if action_response:
                task.post_message(
                    "assistant", f"👁️ Result from taking action: {action_response}"
                )

            # Record the action for feedback and tuning
            task.record_action(
                state=EnvState(),
                prompt=response.prompt,
                action=selection.action,
                tool=recipetool.ref(),
                result=action_response,
                agent_id=self.name(),
                model=response.model,
            )

            _thread.add_msg(response.msg)

            new_state = action_response
            return _thread, new_state, False

        except Exception as e:
            console.print("Exception taking action: ", e)
            traceback.print_exc()
            task.post_message("assistant", f"⚠️ Error taking action: {e} -- retrying...")
            raise e

    @classmethod
    def supported_devices(cls) -> List[Type[Device]]:
        """Devices this agent supports

        Returns:
            List[Type[Device]]: A list of supported devices
        """
        return [Desktop]

    @classmethod
    def config_type(cls) -> Type[SurfRecipesConfig]:
        """Type of config

        Returns:
            Type[DinoConfig]: Config type
        """
        return SurfRecipesConfig

    @classmethod
    def from_config(cls, config: SurfRecipesConfig) -> "SurfRecipes":
        """Create an agent from a config

        Args:
            config (DinoConfig): Agent config

        Returns:
            SurfRecipes: The agent
        """
        return SurfRecipes()

    @classmethod
    def default(cls) -> "SurfRecipes":
        """Create a default agent

        Returns:
            SurfRecipes: The agent
        """
        return SurfRecipes()

    @classmethod
    def init(cls) -> None:
        """Initialize the agent class"""
        return


Agent = SurfRecipes
