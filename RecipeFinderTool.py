from toolfuse import Tool, action, observation
from mllm import RoleThread, Router
from typing import List, Dict, Union
import json, requests, PIL
from prompt_to_analyze_requirements import analyzer_prompt

from dotenv import load_dotenv
import os
load_dotenv()
SPOONACULAR_API_KEY = os.environ['SPOONACULAR_API_KEY']

class RecipeFinderTool(Tool):

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
        print(response.text)
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
        img = PIL.Image.open(requests.get(recipe_card_url, stream=True).raw)
        img.show()
        return "Task Complete"