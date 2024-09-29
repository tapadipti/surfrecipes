import hashlib
import logging
import os
import time
import json
from typing import List, Optional, Tuple, Dict, Union

import requests
from agentdesk.device import Desktop
from mllm import RoleMessage, RoleThread, Router
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from rich.console import Console
from taskara import Task
from toolfuse import Tool, action, observation

from .prompt_to_analyze_requirements import analyzer_prompt

router = Router.from_env()
console = Console()

logger = logging.getLogger(__name__)
logger.setLevel(int(os.getenv("LOG_LEVEL", logging.DEBUG)))

SPOONACULAR_API_KEY = os.environ['SPOONACULAR_API_KEY']
if not SPOONACULAR_API_KEY:
    print ("Please set your SPOONACULAR_API_KEY first.")
    raise

class SurfRecipesTool(Tool):
    """A semantic desktop replaces click actions with semantic description rather than coordinates"""

    def __init__(
        self, task: Task, desktop: Desktop, data_path: str = "./.data"
    ) -> None:
        """
        Initialize and open a URL in the application.

        Args:
            task: Agent task. Defaults to None.
            desktop: Desktop instance to wrap.
            data_path (str, optional): Path to data. Defaults to "./.data".
        """
        super().__init__(wraps=desktop)
        self.desktop = desktop

        self.data_path = data_path
        self.img_path = os.path.join(self.data_path, "images", task.id)
        os.makedirs(self.img_path, exist_ok=True)

        self.task = task

    @observation
    def get_requirements(self, requirements: str) -> Dict[str, Union[str, List[str]]]:
        """
        This is the first step in solving a recipe finder task. It takes a text describing what the user wants and returns a structured breakdown of user requirements. The structured breakdown clarifies the food, diet, intolerances, include_ingredients and exclude_ingredients that the user wants in the recipe. This breakdown can then be used to search for suitable recipes.
        """
        thread = RoleThread()
        router = Router(preference=["gpt-4-turbo"])

        analyzer_msg = f"{analyzer_prompt} Here is the user requirement in plain English: {requirements}"
        thread.post(role="user", msg=analyzer_msg)

        response = router.chat(thread)
        requirements_breakdown = json.loads(response.msg.text)

        return {
            "food": requirements_breakdown["food"],
            "diet": requirements_breakdown["diet"],
            "intolerances": requirements_breakdown["intolerances"],
            "include_ingredients": requirements_breakdown["include_ingredients"],
            "exclude_ingredients": requirements_breakdown["exclude_ingredients"],
        }

    @action
    def search_recipe(self, requirements_breakdown: Dict[str, str]) -> str:
        """
        Searches for a recipe that meet the user's requirements. The user's requirements are provided as a structured dictionary with the following keys: food, diet, intolerances, include_ingredients, exclude_ingredients. Using this dictionary, this method queries the spoonacular recipe search api and returns the ID of a recipe that meets the requirements.
        """
        params = {'apiKey': SPOONACULAR_API_KEY, 'number': 1}
        if requirements_breakdown['food']: params['query'] = requirements_breakdown['food']
        if requirements_breakdown['diet']: params['diet'] = requirements_breakdown['diet']
        if requirements_breakdown['intolerances']:
            if type(requirements_breakdown['intolerances']) == list:
                params['intolerances'] = ','.join(requirements_breakdown['intolerances'])
            else:
                params['intolerances'] = requirements_breakdown['intolerances']
        if requirements_breakdown['include_ingredients']:
            if type(requirements_breakdown['include_ingredients']) == list:
                params['includeIngredients'] = ','.join(requirements_breakdown['include_ingredients'])
            else:
                params['includeIngredients'] =requirements_breakdown['include_ingredients']
        if requirements_breakdown['exclude_ingredients']:
            if type(requirements_breakdown['exclude_ingredients']) == list:
                params['excludeIngredients'] = ','.join(requirements_breakdown['exclude_ingredients'])
            else:
                params['excludeIngredients'] =requirements_breakdown['exclude_ingredients']

        search_recipe_api_url = "https://api.spoonacular.com/recipes/complexSearch"
        response = requests.get(search_recipe_api_url, params=params)
        recipe = json.loads(response.text)
        recipe_id = recipe['results'][0]['id']
        return recipe_id

    @action
    def get_recipe_details(self, recipe_id: str) -> str:
        """
        Fetches the details of a recipe identified by the given recipe ID. The fetched details are contained in an image hosted in a recipe_card_url. Later, the recipe_card_url can be shown to the user.
        """
        params = {'apiKey': SPOONACULAR_API_KEY}
        get_recipe_card_api_url = f"https://api.spoonacular.com/recipes/{recipe_id}/card"
        recipe_card_response = requests.get(get_recipe_card_api_url, params=params)
        recipe_card = json.loads(recipe_card_response.text)
        recipe_card_url = recipe_card['url']
        return recipe_card_url

    @observation
    def display_recipe_details(self, recipe_card_url: str) -> None:
        """Displays the details of a recipe using a recipe card available in the specified recipe_card_url."""
        img = Image.open(requests.get(recipe_card_url, stream=True).raw)
        img.show()
        return "Task Complete"