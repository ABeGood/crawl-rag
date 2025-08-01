from dotenv import load_dotenv
from openai import OpenAI
import os
from validators import NormalizedTextResponse, extract_json_from_markdown
import json
import logging

logger = logging.getLogger(__name__)

load_dotenv()

api_key = os.environ.get("OPENAI_TOKEN")
client = OpenAI(api_key=api_key)


instruction = f"""
You are tasked with normalizing text from customer communications with an online cosmetics shop in Czech language. The goal is to refine the text to make it structurally, grammatically, and punctuationally correct while preserving the original meaning and making only minimal necessary changes.

Guidelines for text normalization:
1. Correct obvious spelling errors
2. Fix grammatical mistakes
3. Adjust punctuation where necessary
4. Improve sentence structure if it's unclear
5. Maintain the original tone and style of the message
6. Preserve all information from the original text
7. Make only minimal changes required for clarity and correctness

Here is the original text to be normalized:

<original_text>
{{ORIGINAL_TEXT}}
</original_text>

Please analyze the text for errors and areas that need improvement. Then, make minimal changes to normalize the text while ensuring that all original information remains intact.

Provide your normalized version of the text in json format.
Example:
{{{{
  "normalized_text": "Dobrý den, chtěl bych si objednat rtěnku, ale nevím, jaká barva by se mi hodila. Můžete mi poradit?",
}}}}
"""

def normalize_question(question:str):
    prompt = instruction.format(ORIGINAL_TEXT = question)

    response = client.responses.create(
        model="gpt-4o-2024-11-20",
        input=prompt,
    )
    response_raw = extract_json_from_markdown(response.output_text)

    NormalizedTextResponse.model_validate_json(response_raw)
    norm_response_dict = json.loads(response_raw)

    return norm_response_dict

def create_normalized_question(qa_data):
    """Create embeddings and organize for efficient retrieval"""
    
    enhanced_data = []
    
    for qa in qa_data:
        # Create embeddings
        logger.info(f'ID: {qa["id"]}')
        logger.info(f'Input question: {qa['question']}')

        norm_question = normalize_question(qa['question'])
        logger.info(f'Norm question: {norm_question['normalized_text']}')

        # Add to original structure
        enhanced_qa = {
            **qa,  # Original data
            'question_norm': norm_question['normalized_text'],
        }
        
        enhanced_data.append(enhanced_qa)
    
    return enhanced_data

if __name__ == '__main__':
    input_file_path = 'data/qa.json'

    with open(input_file_path, 'r', encoding='utf-8') as f:
        qa_data = json.load(f)

    data_w_norm_questions = create_normalized_question(qa_data)

    output_file_path = 'data/qa_w_norm_questions.json'
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(data_w_norm_questions, f, indent=2, ensure_ascii=False)