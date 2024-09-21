from mllm import RoleThread, Router
from RecipeFinderTool import RecipeFinderTool
from prompt_to_return_action import action_finder_prompt

import json, sys, pprint
from dotenv import load_dotenv
load_dotenv()

task_description = sys.argv[1] # "Find me a gluten-free vegetarian soup recipe with tomato and carrots and without any eggs."

def get_next_action(msg: str, current_state: dict) -> dict:
    thread.post(role="user", msg=f"{msg} Given the current state: {current_state}, suggest the next action.")
    response = router.chat(thread)
    return response

thread = RoleThread()
router = Router(preference=["gpt-4-turbo"])

tool = RecipeFinderTool()
available_actions = tool.json_schema()
action_finder_msg = f"{action_finder_prompt} Here are the actions available to you: {available_actions}"

current_state = {"task_description": task_description}

while(True):
    next_action = get_next_action(msg=action_finder_msg, current_state=current_state)
    next_action_json = json.loads(next_action.msg.text)
    print("\n\nNext action json: ")
    pprint.pprint(next_action_json)

    action = tool.find_action(next_action_json['action'])
    result = tool.use(action, **next_action_json['parameters'])
    print("\n\nResult: ")
    pprint.pprint(result)

    current_state = result
    if current_state == "Task Complete":
        print("Task Completed. Going to stop now.")
        break