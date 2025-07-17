import os
import json
from openai import AsyncOpenAI

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# async def run_gpt(prompt: str, model: str = 'gpt-4.1-nano', system_prompt: str = 'You are a financial data assistant.', format_type: str = 'json_object') -> dict:
#     """
#     Unified GPT caller for processing prompts and returning parsed JSON.

#     Args:
#         prompt (str): The user prompt content
#         model (str): The OpenAI model to use
#         system_prompt (str): The system-level instruction prompt
#         format_type (str): The expected response format type

#     Returns:
#         dict: The parsed JSON response from the GPT model
#     """
#     response = await openai_client.chat.completions.create(
#         model=model,
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": prompt}
#         ],
#         response_format={"type": format_type},
#         temperature=0.0
#     )

#     return json.loads(response.choices[0].message.content)

async def run_gpt(prompt: str, model: str = 'gpt-4o', system_prompt: str = 'You are a financial data assistant.', format_type: str = 'json') -> dict:
    """
    Unified GPT caller for processing prompts and returning parsed JSON.

    Args:
        prompt (str): The user prompt content
        model (str): The OpenAI model to use
        system_prompt (str): The system-level instruction prompt
        format_type (str): The expected response format type ('json' or 'text')

    Returns:
        dict: The parsed JSON response from the GPT model
    """
    response = await openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        response_format=format_type,  # must be a string like 'json'
        temperature=0.0
    )

    return json.loads(response.choices[0].message.content)


