from dotenv import load_dotenv
from openai import OpenAI
import os
from validators import MessageClassifierResponse, SpecialistResponse, extract_json_from_markdown
import json
import logging
from sim_search import find_similar_questions

logger = logging.getLogger(__name__)

load_dotenv()

api_key = os.environ.get("OPENAI_TOKEN")
client = OpenAI(api_key=api_key)

instruction_1 = f"""
TASK:
You are a classifier for a Czech language questionnaire system. Your job is to determine whether a user's message is:

An answer to the current questionnaire question, OR
A request for customer support/assistance

INPUT FORMAT:
You will receive:

Questionnaire Question: The current question the user should be answering
User Message: The user's response in Czech

CLASSIFICATION RULES:
Classify as QUESTIONNAIRE ANSWER ("switch_to_assistant": false) when:

The user provides a direct answer to the question
The message contains relevant information that addresses the question
The user is attempting to complete the questionnaire step
Minor clarification requests about the current question

Classify as CUSTOMER SUPPORT NEEDED ("switch_to_assistant": true) when:

The user asks for help with the questionnaire process itself
The user reports technical issues or errors
The user requests information about company services/policies
The user wants to speak with a human representative
The message is completely unrelated to the current question
The user expresses confusion about the entire questionnaire

INSTRUCTIONS:

Read the questionnaire question carefully
Analyze the user message in the context of that question
Determine if the message reasonably attempts to answer the question or seeks support
Output your classification in the specified JSON format

OUTPUT FORMAT:
Return only valid JSON in this exact format:
{{{{"switch_to_assistant": false}}}}
OR
{{{{"switch_to_assistant": true}}}}

INPUT DATA:
Questionnaire Question:
{{QUESTION}}
User Message:
{{USER_MESSAGE}}

EXAMPLES:
Example 1 - Questionnaire Answer:
Question: "Jaký je váš věk?" (What is your age?)
User: "35 let" (35 years old)
Output: {{{{"switch_to_assistant": false}}}}
Example 2 - Customer Support Needed:
Question: "Jaký je váš věk?" (What is your age?)
User: "Nefunguje mi tlačítko, potřebuji pomoc" (The button doesn't work, I need help)
Output: {{{{"switch_to_assistant": true}}}}
Example 3 - Questionnaire Answer (with clarification):
Question: "Jaký je váš věk?" (What is your age?)
User: "Myslíte věk v dokončených letech? 34" (Do you mean age in completed years? 34)
Output: {{{{"switch_to_assistant": false}}}}
Now analyze the provided question and user message, then return your classification.
"""

classifier_instruction = f"""
Your task is to classify user message in Czech language. User is filling a questionary, but during the process he can ask assistant for a consultation or help.
Yoy need to classify if the user messahe is an answer to a questionary question or if he need to be switched to a customer support assistant.
Toy will be provided with the two pieces of information:
1. Actual question from the questionary.
2. User message.

Guidelines fuser message classification:
1. Read the actual question from the questionary.
2. Read the user message and compare it with the actual question from the questionary.
3. Define is the user message is related to the actual question from the questionary or if this message needs reaction from customer support.
4. Structure your output in json format. {{{{"switch_to_assistant": true}}}} if this message needs reaction from customer support and {{{{"switch_to_assistant": false}}}} if this message is an answer to the actual question from the questionary.


Here is the actual question from the questionary:

<questionary_question>
{{QUESTION}}
</questionary_question>

Here is the user message:

<user_message>
{{USER_MESSAGE}}
</user_message>

Please analyze the actual question from the questionary and user message. Then, is the user message is related to the actual question from the questionary or if this message needs reaction from customer support.

Provide your normalized version of the text in json format.
Example:
{{{{
  "switch_to_assistant": true,
}}}}
"""

def switch_to_assistant_needed(last_question:str, user_message:str):
    prompt = classifier_instruction.format(QUESTION = last_question, USER_MESSAGE = user_message)

    response = client.responses.create(
        model="o4-mini-2025-04-16",
        input=prompt,
    )
    response_raw = extract_json_from_markdown(response.output_text)

    MessageClassifierResponse.model_validate_json(response_raw)
    response_dict = json.loads(response_raw)

    return response_dict['switch_to_assistant']


specialist_instruction = f"""
You are an AI customer support assistant for a Czech online cosmetics shop. Your task is to answer customer questions accurately and helpfully. You will be provided with similar question-answer pairs to help guide your responses.

First, you will be given a set of question-answer pairs that are similar to the current customer's question. These will be used as reference for your response. The similar question-answer pairs will be provided in the following format:

<similar_qa_pairs>
{{SIMILAR_QA_PAIRS}}
</similar_qa_pairs>

Next, you will be given the customer's question:

<customer_question>
{{CUSTOMER_QUESTION}}
</customer_question>

Analyze the customer's question and compare it to the similar question-answer pairs provided. Use these pairs as a guide for crafting your response, but do not simply copy them. Your answer should be tailored to the specific customer question.

When answering the question:
1. Ensure your response is relevant to the Czech online cosmetics shop context.
2. Provide accurate information based on the similar question-answer pairs and your knowledge of cosmetics.
3. Be polite, professional, and helpful in your tone.
4. If the question is about a specific product, include relevant details such as ingredients, usage instructions, or benefits.
5. If applicable, suggest related products or provide additional helpful information.
6. Structure your output in json format: {{{{"confidence": int (0-5), "answer": str (actul answer to user's query)}}}}
7. Your answer must be in Czech language

If you are not at least 4/5 confident in your ability to answer the question accurately, you must ask the customer for additional information. In this case, respond with:

<request_more_info>
{{{{
  "confidence": 3, 
  "answer": "Omlouvám se, ale potřebuji další informace, abych vám mohl lépe pomoct. Mohli byste prosím poskytnout více podrobností o [konkrétní aspekt otázky]?"
}}}}
</request_more_info>

If you are confident in your answer, provide your response in the following format:

<answer>
{{{{
  "confidence": 4, 
  "answer": "[Your detailed response to the customer's question in Czech language]"
}}}}
</answer>

Remember to always prioritize customer satisfaction and provide accurate, helpful information related to the Czech online cosmetics shop.
"""

def call_specialist(user_message:str):
    
    similar_questions_list = find_similar_questions(user_message)

    similar_questions_str = ""

    for i, qa_dict in enumerate(similar_questions_list, 1):
      # Extract question and answer from the dictionary
      question = qa_dict.get('question', '')
      answer = qa_dict.get('answer', '')
      
      # Add formatted question and answer
      similar_questions_str += f"Question {i}:\n"
      similar_questions_str += f"{question}\n\n"
      similar_questions_str += f"Answer {i}:\n"
      similar_questions_str += f"{answer}\n\n"
      
      # Add separator between Q&A pairs (except for the last one)
      if i < len(similar_questions_list):
          similar_questions_str += "\n\n"

    prompt = specialist_instruction.format(SIMILAR_QA_PAIRS = similar_questions_str, CUSTOMER_QUESTION = user_message)

    response = client.responses.create(
        model="o4-mini-2025-04-16",
        input=prompt,
    )
    response_raw = extract_json_from_markdown(response.output_text)

    SpecialistResponse.model_validate_json(response_raw)
    response_dict = json.loads(response_raw)

    return response_dict['answer']