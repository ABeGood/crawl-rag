import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class QuestionType(Enum):
    TEXT = "text"
    CHOICE = "choice"
    SCALE = "scale"
    YES_NO = "yes_no"
    PHOTO = "photo"

@dataclass
class Question:
    index: int
    text: str
    question_type: QuestionType = QuestionType.TEXT
    choices: Optional[List[str]] = None
    scale_min: int = 1
    scale_max: int = 10
    required: bool = True
    has_followup: bool = False  # For YES_NO questions that need additional info
    followup_text: Optional[str] = None  # Text to show when asking for followup
    
    def __post_init__(self):
        if self.question_type == QuestionType.CHOICE and not self.choices:
            raise ValueError("Choices must be provided for choice questions")

class QuestionManager:
    def __init__(self, questions_file: str):
        self.questions_file = questions_file
        self.questions: List[Question] = []
        self.followup_questions = set()  # Questions that need followup for YES answers
        self.load_questions()

    def load_questions(self):
        """Load questions from .txt file with enhanced formatting support"""
        try:
            with open(self.questions_file, 'r', encoding='utf-8') as file:
                content = file.read().strip()
            
            self._load_json_questions(content)
                
        except FileNotFoundError:
            raise FileNotFoundError(f"Questions file '{self.questions_file}' not found")
        except Exception as e:
            raise Exception(f"Error loading questions: {e}")

    def _load_json_questions(self, content: str):
        """Load questions from JSON format"""
        data = json.loads(content)
        
        for i, item in enumerate(data):
            if isinstance(item, str):
                question = Question(index=i, text=item.strip())
            elif isinstance(item, dict):
                question = Question(
                    index=i,
                    text=item['text'].strip(),
                    question_type=QuestionType(item.get('type', 'text')),
                    choices=item.get('choices'),
                    scale_min=item.get('scale_min', 1),
                    scale_max=item.get('scale_max', 10),
                    required=item.get('required', True),
                    has_followup=item.get('has_followup', False),
                    followup_text=item.get('followup_text')
                )
            else:
                raise ValueError(f"Invalid question format at index {i}")
            
            self.questions.append(question)


    def get_question(self, index: int) -> Optional[Question]:
        """Get question by index"""
        if 0 <= index < len(self.questions):
            return self.questions[index]
        return None

    def get_total_questions(self) -> int:
        """Get total number of questions"""
        return len(self.questions)

    def get_question_text_with_options(self, index: int) -> str:
        """Get formatted question text with options if applicable"""
        question = self.get_question(index)
        if not question:
            return "Otázka nenalezena"
        
        text = f"*Otázka {index + 1}/{self.get_total_questions()}:*\n\n{question.text}"
        
        if question.question_type == QuestionType.CHOICE and question.choices:
            text += "\n\nVyberte jednu z možností:"
            for i, choice in enumerate(question.choices, 1):
                text += f"\n{i}. {choice}"
        elif question.question_type == QuestionType.SCALE:
            text += f"\n\nOhodnoťte na škále od {question.scale_min} do {question.scale_max}"
        elif question.question_type == QuestionType.YES_NO:
            text += "\n\nOdpovězte: Ano nebo Ne"
            if question.has_followup:
                text += "\n\n💡 _Pokud odpovíte 'Ano', budete požádáni o doplňující informace_"
        elif question.question_type == QuestionType.PHOTO:
            text += "\n\n📷 Prosím, nahrajte fotografii"
        
        return text

    def get_followup_text(self, question_index: int) -> Optional[str]:
        """Get followup question text for YES_NO questions"""
        question = self.get_question(question_index)
        if question and question.has_followup:
            return question.followup_text
        return None

    def validate_answer(self, question_index: int, answer: str, is_photo: bool = False) -> tuple[bool, str]:
        """Validate user's answer for a specific question"""
        question = self.get_question(question_index)
        if not question:
            return False, "Otázka nenalezena"
        
        if question.question_type == QuestionType.PHOTO:
            if is_photo:
                return True, "photo_uploaded"
            else:
                return False, "Prosím, nahrajte fotografii"
        
        answer = answer.strip()
        
        if question.question_type == QuestionType.CHOICE and question.choices:
            try:
                choice_num = int(answer)
                if 1 <= choice_num <= len(question.choices):
                    return True, question.choices[choice_num - 1]
            except ValueError:
                pass
            
            for choice in question.choices:
                if answer.lower() == choice.lower():
                    return True, choice
            
            return False, f"Prosím, vyberte číslo od 1 do {len(question.choices)} nebo napište jednu z možností"
        
        elif question.question_type == QuestionType.SCALE:
            try:
                scale_value = int(answer)
                if question.scale_min <= scale_value <= question.scale_max:
                    return True, str(scale_value)
                else:
                    return False, f"Prosím, zadejte číslo od {question.scale_min} do {question.scale_max}"
            except ValueError:
                return False, f"Prosím, zadejte číslo od {question.scale_min} do {question.scale_max}"
        
        elif question.question_type == QuestionType.YES_NO:
            answer_lower = answer.lower()
            if answer_lower in ['ano', 'yes', 'y', '1', 'pravda', 'true', 'áno']:
                return True, "Ano"
            elif answer_lower in ['ne', 'no', 'n', '0', 'nepravda', 'false', 'nie']:
                return True, "Ne"
            else:
                return False, "Prosím, odpovězte 'Ano' nebo 'Ne'"
        
        else:  # TEXT question
            if len(answer) == 0:
                return False, "Prosím, zadejte odpověď"
            return True, answer

    def create_skincare_questions_file(self, filename: str = "questions.txt"):
        """Create the skincare questions file"""
        skincare_questions = """[SCALE] Váš věk? | 1-120
[YES_NO] Kuřák?
[YES_NO] Léčíte se s nějakým onemocněním, užíváte pravidelně léky, hormony?
[YES_NO] Pracujete nebo pobýváte v zátěžovém prostředí?
Nahrát první fotografii.
Nahrát druhou fotografii.
[YES_NO] Dehydratovaná, suchá pleť?
[YES_NO] Citlivá pleť?
[YES_NO] Mastná pleť?
[YES_NO] Projevy stárnutí, zralá pleť?
[YES_NO] Pigmentové skvrny, fotostárnutí?
Jak vypadá moje každodenní péče o pleť?
Jaké kosmetické značky používám?
[YES_NO] Navštěvuji kosmetický salón?
Doplňující informace?"""
        
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(skincare_questions)
        
        print(f"Skincare questions file created: {filename}")

# Usage example
if __name__ == "__main__":
    # Create skincare questions file
    qm = QuestionManager.__new__(QuestionManager)
    # qm.create_skincare_questions_file()
    
    # Load and test
    qm = QuestionManager("questions.txt")
    
    print(f"Loaded {qm.get_total_questions()} questions")
    
    # Test question formatting
    for i in range(min(5, qm.get_total_questions())):
        print(f"\n{qm.get_question_text_with_options(i)}")
        question = qm.get_question(i)
        if question.has_followup:
            print(f"Followup: {question.followup_text}")