import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv()

api_key = os.environ.get("OPENAI_TOKEN")
client = OpenAI(api_key=api_key)

def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    return client.embeddings.create(input = [text], model=model).data[0].embedding


def load_qa_data_with_embeddings(filename):
    """Load Q&A data with embeddings from JSON file"""
    with open(filename, 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    return qa_data


QA_DATA_PATH = 'data/qa_data_norm_questions_w_vectors.json'

# Load data with embeddings
qa_data = load_qa_data_with_embeddings(QA_DATA_PATH)


def find_similar_questions(query, top_k=5):
    """
    Find most similar questions to the input query
    
    Args:
        query (str): User's question in Czech
        qa_data_file (str): Path to JSON file with embeddings
        top_k (int): Number of similar questions to return
    
    Returns:
        list: Top k most similar Q&A pairs with similarity scores
    """
    
    # Create embedding for user query
    query_embedding = get_embedding(query)
    query_embedding = np.array(query_embedding).reshape(1, -1)
    
    # Extract question embeddings from data
    question_embeddings = []
    for qa in qa_data:
        question_embeddings.append(qa['question_norm_embedding'])
    
    question_embeddings = np.array(question_embeddings)
    
    # Calculate cosine similarities
    similarities = cosine_similarity(query_embedding, question_embeddings)[0]
    
    # Get top k most similar questions
    top_indices = np.argsort(similarities)[::-1][:top_k]
    
    # Prepare results
    similar_questions = []
    for idx in top_indices:
        similar_questions.append({
            'id': qa_data[idx]['id'],
            'qa_pair': qa_data[idx],
            'similarity_score': float(similarities[idx]),
            'question': qa_data[idx]['question_norm'],
            'answer': qa_data[idx]['answer']
        })
    
    return similar_questions