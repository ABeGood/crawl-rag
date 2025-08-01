from pydantic import BaseModel, Field, validator
import re

class NormalizedTextResponse(BaseModel):
    normalized_text: str = Field(..., min_length=1, description="The normalized version of the original text")
    
    @validator('normalized_text')
    def validate_normalized_text(cls, v):
        if not v or v.isspace():
            raise ValueError('normalized_text cannot be empty or contain only whitespace')
        return v.strip()
    

class MessageClassifierResponse(BaseModel):
    switch_to_assistant: bool = Field(..., description="User message classification")


def extract_json_from_markdown(text: str) -> str:
    """Extract JSON content from markdown code blocks."""
    # Method 1: Using regex to find content between ```json and ```
    json_pattern = r'```(?:json)?\s*(.*?)\s*```'
    match = re.search(json_pattern, text, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    # Method 2: If no code blocks found, try to find JSON-like content
    # Look for content between { and }
    json_like_pattern = r'(\{.*\})'
    match = re.search(json_like_pattern, text, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    # If nothing found, return original text
    return text.strip()