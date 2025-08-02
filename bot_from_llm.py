import asyncio
import logging
from time import sleep
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, PhotoSize, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.formatting import escape_markdown
from typing import Dict, Any, List
import json
import os
from dotenv import load_dotenv
import traceback
from llm_api import switch_to_assistant_needed

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Import our custom classes
from db.db_manager import DatabaseManager
from questions_manager import QuestionManager, QuestionType

class SkinCareQuestionnaireBot:
    def __init__(self, bot_token: str, questions_file: str = "questions.json", db_path: str = "skincare_questionnaire.db"):
        self.bot = AsyncTeleBot(token=bot_token)
        self.db = DatabaseManager(db_path)
        self.question_manager = QuestionManager(questions_file)
        
        # State management
        self.admin_messages = {}
        self.waiting_for_answer = set()  # Users currently answering questions
        self.waiting_for_photo = set()   # Users waiting to upload photos
        self.waiting_for_followup = set()  # Users waiting to provide followup info
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.register_handlers()

    def create_yes_no_keyboard(self, question_index: int) -> InlineKeyboardMarkup:
        """Create inline keyboard for yes/no questions"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        
        # Create buttons with callback data containing question index
        yes_button = InlineKeyboardButton("✅ Ano", callback_data=f"yn_{question_index}_yes")
        no_button = InlineKeyboardButton("❌ Ne", callback_data=f"yn_{question_index}_no")
        
        keyboard.add(yes_button, no_button)
        return keyboard

    def create_start_keyboard(self) -> InlineKeyboardMarkup:
        """Create keyboard for start command"""
        keyboard = InlineKeyboardMarkup()
        start_button = InlineKeyboardButton("🚀 Začít konzultaci", callback_data="start_questionnaire")
        keyboard.add(start_button)
        return keyboard

    def create_continue_keyboard(self) -> InlineKeyboardMarkup:
        """Create keyboard for continuing questionnaire"""
        keyboard = InlineKeyboardMarkup()
        continue_button = InlineKeyboardButton("▶️ Pokračovat", callback_data="continue_questionnaire")
        keyboard.add(continue_button)
        return keyboard
    
    def create_photo_skip_keyboard(self, question_index: int) -> InlineKeyboardMarkup:
        """Create keyboard with skip option for photo questions"""
        keyboard = InlineKeyboardMarkup()
        skip_button = InlineKeyboardButton("⏭️ Přeskočit", callback_data=f"skip_photo_{question_index}")
        keyboard.add(skip_button)
        return keyboard

    def create_followup_skip_keyboard(self, question_index: int) -> InlineKeyboardMarkup:
        """Create keyboard with skip option for follow-up questions"""
        keyboard = InlineKeyboardMarkup()
        skip_button = InlineKeyboardButton("⏭️ Přeskočit", callback_data=f"skip_followup_{question_index}")
        keyboard.add(skip_button)
        return keyboard
    
    def create_text_skip_keyboard(self, question_index: int) -> InlineKeyboardMarkup:
        """Create keyboard with skip option for text questions"""
        keyboard = InlineKeyboardMarkup()
        skip_button = InlineKeyboardButton("⏭️ Přeskočit", callback_data=f"skip_text_{question_index}")
        keyboard.add(skip_button)
        return keyboard

    def run_bot(self):
        """Start the bot with improved error handling"""
        self.logger.info("Starting skincare consultation bot...")
        try:
            asyncio.run(self.bot.polling(non_stop=True, timeout=60, request_timeout=90))
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.error(f"Bot polling stopped due to an error: {e}\nFull traceback:\n{tb}")
            sleep(5)
            self.run_bot()

    def register_handlers(self):
        """Register all message handlers"""

        @self.bot.callback_query_handler(func=lambda call: True)
        async def handle_callback_query(call: CallbackQuery):
            """Handle all callback queries from inline keyboards"""
            try:
                user_id = call.from_user.id
                data = call.data

                # VALIDATE: Check if this is the current active message
                if data.startswith(("yn_", "skip_")):
                    current_message_id = self.db.get_user_last_message(user_id, 'question')
                    if current_message_id and call.message.message_id != current_message_id:
                        # This is an old message button
                        await self.bot.answer_callback_query(
                            call.id, 
                            "⚠️ Tato otázka už není aktivní. Pokračujte s nejnovější otázkou.",
                            show_alert=True
                        )
                        return
                
                # Answer the callback to remove loading state
                await self.bot.answer_callback_query(call.id)
                
                # Handle start questionnaire
                if data == "start_questionnaire":
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    await self._send_question(call.message.chat.id, user_id, 0)
                    return
                
                # Handle continue questionnaire
                if data == "continue_questionnaire":
                    user_data = self.db.get_user(user_id)
                    current_question_index = user_data['current_question_index']
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    await self._send_question(call.message.chat.id, user_id, current_question_index)
                    return
                
                # Handle finish questionnaire
                if data == "finish_questionnaire":
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    await self.bot.send_message(
                        call.message.chat.id, 
                        "✅ Rozhodli jste se ukončit konzultaci."
                    )
                    await self._complete_questionnaire(call.message.chat.id, user_id)
                    return
                
                # Handle skip photo
                if data.startswith("skip_photo_"):
                    question_index = int(data.split("_")[2])
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    await self._handle_skip_photo(call.message.chat.id, user_id, question_index)
                    return
                
                # Handle skip follow-up
                if data.startswith("skip_followup_"):
                    question_index = int(data.split("_")[2])
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    await self._handle_skip_followup(call.message.chat.id, user_id, question_index)
                    return
                
                # NEW: Handle skip text answer
                if data.startswith("skip_text_"):
                    question_index = int(data.split("_")[2])
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    await self._handle_skip_text(call.message.chat.id, user_id, question_index)
                    return
                
                # Handle yes/no answers
                if data.startswith("yn_"):
                    parts = data.split("_")
                    question_index = int(parts[1])
                    answer = parts[2]  # "yes" or "no"
                    
                    # Convert to Czech
                    answer_text = "Ano" if answer == "yes" else "Ne"
                    
                    # Remove keyboard from the message
                    await self.bot.edit_message_reply_markup(
                        call.message.chat.id, 
                        call.message.message_id, 
                        reply_markup=None
                    )
                    
                    # Send confirmation with selected answer
                    await self.bot.send_message(
                        call.message.chat.id, 
                        f"✅ Odpověď uložena: *{answer_text}*",
                        parse_mode="MARKDOWN"
                    )
                    
                    # Process the answer
                    await self._process_keyboard_answer(call.message.chat.id, user_id, question_index, answer_text)
                    return
                    
            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(f"Error in callback handler: {e}\nFull traceback:\n{tb}")
                await self.bot.send_message(
                    call.message.chat.id,
                    "😔 Došlo k chybě při zpracování odpovědi. Zkuste to prosím znovu."
                )

        @self.bot.message_handler(commands=['start'])
        async def handle_start(msg: Message):
            """Handle /start command in Czech"""
            user = msg.from_user
            self.db.create_or_update_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            user_data = self.db.get_user(user.id)
            
            if user_data['questionnaire_completed']:
                await self.bot.send_message(
                    msg.chat.id,
                    "🎉 Již jste dokončili kosmetickou konzultaci! Děkujeme za účast.\n\n"
                    "Použijte /restart pro nové vyplnění nebo /vysledky pro zobrazení odpovědí.",
                    parse_mode="MARKDOWN"
                )
            else:
                total_questions = self.question_manager.get_total_questions()
                current_index = user_data['current_question_index']
                
                if current_index == 0:
                    welcome_text = (
                        "👋 *Vítejte v kosmetické konzultaci!*\n\n"
                        f"📋 Celkem otázek: {total_questions}\n"
                        "📷 Budete požádáni o nahrání 2 fotografií\n"
                        "💾 Můžete se kdykoli zastavit a pokračovat později\n\n"
                        "🚀 Jste připraveni začít?"
                    )
                    keyboard = self.create_start_keyboard()
                    await self.bot.send_message(
                        msg.chat.id, 
                        welcome_text, 
                        parse_mode="MARKDOWN",
                        reply_markup=keyboard
                    )
                else:
                    if user_data.get('waiting_for_followup'):
                        followup_index = user_data.get('followup_question_index', current_index - 1)
                        followup_text = self.question_manager.get_followup_text(followup_index)
                        question_text = self.question_manager.get_question(followup_index).text

                        # Get the user's original answer for this question
                        user_answers = self.db.get_user_answers(msg.from_user.id)
                        original_answer = "Odpověď nenalezena"
                        
                        # Find the answer for the specific question index
                        for answer in user_answers:
                            if answer['question_index'] == followup_index:
                                original_answer = answer['answer_text']
                                break

                        # FIX: Add skip keyboard for follow-up question
                        keyboard = self.create_followup_skip_keyboard(followup_index)
                        
                        welcome_text = (
                            f"🔄 *Pokračování konzultace*\n\n"
                            f"Čekáme na doplňující informace k předchozí otázce:\n"
                            f"{question_text}\n\n"
                            f"Vaše odpoveď: **{original_answer}**\n\n"
                            f"💬 {followup_text}\n\n"
                            f"⏭️ _Můžete přeskočit kliknutím na tlačítko níže_"
                        )
                        
                        await self.bot.send_message(
                            msg.chat.id, 
                            welcome_text, 
                            parse_mode="MARKDOWN",
                            reply_markup=keyboard  # FIX: Add the keyboard here
                        )
                    else:
                        welcome_text = (
                            f"🔄 *Pokračování konzultace*\n\n"
                            f"📊 Postup: {current_index}/{total_questions}\n"
                            "Pokračujte tam, kde jste skončili."
                        )
                        keyboard = self.create_continue_keyboard()
                        await self.bot.send_message(
                            msg.chat.id, 
                            welcome_text, 
                            parse_mode="MARKDOWN",
                            reply_markup=keyboard
                        )

        @self.bot.message_handler(commands=['restart'])
        async def handle_restart(msg: Message):
            """Reset user's questionnaire progress"""
            user_id = msg.from_user.id
            self.db.reset_user_progress(user_id)
            self._clear_user_states(user_id)
            
            await self.bot.send_message(
                msg.chat.id,
                "🔄 Konzultace byla resetována. Použijte /start pro nové zahájení.",
                parse_mode="MARKDOWN"
            )

        @self.bot.message_handler(commands=['results'])
        async def handle_results(msg: Message):
            """Show user's answers in Czech"""
            user_id = msg.from_user.id
            answers = self.db.get_user_answers(user_id)
            photos = self.db.get_user_photos(user_id)
            
            if not answers and not photos:
                await self.bot.send_message(
                    msg.chat.id,
                    "📋 Zatím nemáte žádné odpovědi. Použijte /start pro zahájení konzultace."
                )
                return
            
            results_text = "📋 *Vaše odpovědi z kosmetické konzultace:*\n\n"
            
            # Group answers by question index
            question_answers = {}
            for answer in answers:
                q_idx = answer['question_index']
                if q_idx not in question_answers:
                    question_answers[q_idx] = []
                question_answers[q_idx].append(answer)
            
            for q_idx in sorted(question_answers.keys()):
                answer_list = question_answers[q_idx]
                main_answer = answer_list[0]
                
                results_text += f"*Otázka {q_idx + 1}:* {escape_markdown(main_answer['question_text'])}\n"
                
                if main_answer['answer_type'] == 'photo':
                    if main_answer['answer_text'] == 'None':
                        results_text += f"*Odpověď:* 📷 ⏭️ Fotografie přeskočena\n"
                    else:
                        results_text += f"*Odpověď:* 📷 Fotografie nahrána\n"
                else:
                    # Handle skipped text answers
                    if main_answer['answer_text'] == 'None':
                        results_text += f"*Odpověď:* ⏭️ Přeskočeno\n"
                    else:
                        results_text += f"*Odpověď:* {escape_markdown(main_answer['answer_text'])}\n"
                
                # Add followup text if exists and not None
                if main_answer['followup_text']:
                    if main_answer['followup_text'] == 'None':
                        results_text += f"*Doplňující info:* ⏭️ Přeskočeno\n"
                    else:
                        results_text += f"*Doplňující info:* {escape_markdown(main_answer['followup_text'])}\n"
                
                results_text += "\n"
            
            # Split long messages
            if len(results_text) > 4000:
                parts = self._split_message(results_text, 4000)
                for part in parts:
                    await self.bot.send_message(msg.chat.id, part, parse_mode="MARKDOWN")
            else:
                await self.bot.send_message(msg.chat.id, results_text, parse_mode="MARKDOWN")
            
            # Send photos separately (only non-skipped ones)
            if photos:
                await self.bot.send_message(msg.chat.id, "📷 *Vaše nahrané fotografie:*", parse_mode="MARKDOWN")
                for photo in photos:
                    try:
                        caption = f"Otázka {photo['question_index'] + 1}"
                        if photo['photo_description']:
                            caption += f": {photo['photo_description']}"
                        await self.bot.send_photo(msg.chat.id, photo['file_id'], caption=caption)
                    except Exception as e:
                        tb = traceback.format_exc()
                        self.logger.error(f"Failed to send photo {photo['file_id']}: {e}\nFull traceback:\n{tb}")

        @self.bot.message_handler(commands=['help'])
        async def handle_help(msg: Message):
            """Show help information in Czech"""
            help_text = """
📚 *Příkazy botu:*

/start - Začít nebo pokračovat v konzultaci
/restart - Resetovat postup a začít znovu
/results - Zobrazit vaše odpovědi
/help - Zobrazit tuto nápovědu
/stats - Zobrazit statistiky

*Jak vyplňovat konzultaci:*
• 🔘 Pro otázky Ano/Ne klikněte na tlačítka
• 📝 Pro textové otázky napište odpověď
• 🔢 Pro hodnocení zadejte číslo v uvedeném rozsahu
• 📷 Pro fotografie klikněte na 📎 a vyberte fotku
• 💾 Váš postup se ukládá automaticky
• ✅ Při odpovědi "Ano" na některé otázky budete požádáni o doplňující informace
• ⏭️ **NOVÉ:** Jakoukoliv otázku můžete přeskočit tlačítkem "Přeskočit"
• 🔄 Přeskočené odpovědi se zobrazí jako "Přeskočeno" ve výsledcích

*Typy otázek, které lze přeskočit:*
• 📝 Textové odpovědi
• 🔢 Hodnocení na škále
• 📋 Výběr z možností
• 📷 Nahrání fotografií
• 💬 Doplňující informace
"""
            await self.bot.send_message(msg.chat.id, help_text, parse_mode="MARKDOWN")


        @self.bot.message_handler(commands=['stats'])
        async def handle_stats(msg: Message):
            """Show questionnaire statistics in Czech"""
            stats = self.db.get_statistics()
            stats_text = f"""
📊 *Statistiky kosmetické konzultace:*

👥 Celkem uživatelů: {stats['total_users']}
✅ Dokončených konzultací: {stats['completed_users']}
🔄 Probíhá konzultace: {stats['active_users']}
📈 Míra dokončení: {stats['completion_rate']:.1%}
📷 Nahráno fotografií: {stats['total_photos']}
⏭️ Přeskočeno fotografií: {stats['skipped_photos']}
⏭️ Přeskočeno textových odpovědí: {stats['skipped_text']}
⏭️ Přeskočeno doplňujících info: {stats['skipped_followups']}
👤 Průměrný věk: {stats['average_age']} let
🚬 Kuřáků: {stats['smokers_count']}
"""
            await self.bot.send_message(msg.chat.id, stats_text, parse_mode="MARKDOWN")

        @self.bot.message_handler(content_types=['photo'])
        async def handle_photo(msg: Message):
            """Handle photo uploads"""
            user_id = msg.from_user.id
            
            try:
                user_data = self.db.get_user(user_id)
                if not user_data:
                    await self.bot.send_message(msg.chat.id, "Použijte /start pro zahájení konzultace.")
                    return
                
                if user_data['questionnaire_completed']:
                    await self.bot.send_message(msg.chat.id, "✅ Konzultace je již dokončena.")
                    return
                
                current_question_index = user_data['current_question_index']
                question = self.question_manager.get_question(current_question_index)
                
                if not question or question.question_type != QuestionType.PHOTO:
                    await self.bot.send_message(
                        msg.chat.id, 
                        "📷 Momentálně neočekávám fotografii. Pokračujte prosím v konzultaci."
                    )
                    return
                
                # Get the best quality photo
                photo: PhotoSize = max(msg.photo, key=lambda p: p.file_size)
                
                # Save photo
                self.db.save_photo(
                    user_id=user_id,
                    question_index=current_question_index,
                    question_text=question.text,
                    file_id=photo.file_id,
                    file_unique_id=photo.file_unique_id,
                    file_size=photo.file_size,
                    photo_description=msg.caption
                )
                
                self.waiting_for_photo.discard(user_id)
                
                await self.bot.send_message(msg.chat.id, "✅ Fotografie byla úspěšně nahrána!")
                
                # Send next question
                next_question_index = current_question_index + 1
                await self._send_question(msg.chat.id, user_id, next_question_index)
                
            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(f"Error handling photo: {e}\nFull traceback:\n{tb}")
                await self.bot.send_message(
                    msg.chat.id,
                    "😔 Chyba při nahrávání fotografie. Zkuste to prosím znovu."
                )

        @self.bot.message_handler(
            func=lambda msg: msg.text is not None and '/' not in msg.text,
        )
        async def handle_message(msg: Message):
            """Handle regular text messages"""
            user_id = msg.from_user.id
            message_text = msg.text.strip()
            
            try:
                # Ensure user exists
                user = msg.from_user
                self.db.create_or_update_user(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name
                )
                
                user_data = self.db.get_user(user_id)
                current_question_index = user_data['current_question_index']
                total_questions = self.question_manager.get_total_questions()
                
                # Check if questionnaire is completed
                if user_data['questionnaire_completed']:

                    # AG: SEND DIRECTLY TO SPECIALIST
                    await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!")

                    # await self.bot.send_message(
                    #     msg.chat.id,
                    #     "✅ Konzultace je již dokončena! Použijte /vysledky pro zobrazení nebo /restart pro nové vyplnění."
                    # )
                    return
                
                # Check if questionnaire was never started
                questionnaire_not_started = (
                    current_question_index == 0 and
                    user_id not in self.waiting_for_answer and
                    user_id not in self.waiting_for_photo and
                    not user_data.get('waiting_for_followup')
                )
                
                if questionnaire_not_started:
                    # Route to assistant for users who haven't started questionnaire
                    await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!")
                    return
                
                # Handle followup answers
                if user_data.get('waiting_for_followup'):

                    actual_question = self.question_manager.get_question(current_question_index-1)
                    actual_question_text = actual_question.text
                    actualfollowup_question_text = actual_question.followup_text
                    actual_question_text_full = actual_question_text + ' ' + actualfollowup_question_text

                    if switch_to_assistant_needed(last_question=actual_question_text_full, user_message=message_text):
                        await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!")
                        return

                    followup_question_index = user_data.get('followup_question_index')
                    if followup_question_index is not None:
                        self.db.save_followup_answer(user_id, followup_question_index, message_text)
                        user_data = self.db.get_user(user_id)
                        self.waiting_for_followup.discard(user_id)
                        
                        await self.bot.send_message(msg.chat.id, "✅ Doplňující informace uloženy!")
                        
                        # Continue to next question
                        next_question_index = followup_question_index + 1
                        await self._send_question(msg.chat.id, user_id, next_question_index)
                        return
                    
                    # AG: reset user_data.get('waiting_for_followup')


                # Process answer if user is in questionnaire mode
                if user_id in self.waiting_for_answer:
                    actual_question = self.question_manager.get_question(current_question_index)
                    actual_question_text = actual_question.text

                    if switch_to_assistant_needed(last_question=actual_question_text, user_message=message_text):
                        await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!")
                    else:
                        await self._process_answer(msg.chat.id, user_id, current_question_index, message_text)
                elif user_id in self.waiting_for_photo:
                    await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!")
                    # await self.bot.send_message(
                    #     msg.chat.id,
                    #     "📷 Očekávám fotografii. Klikněte na 📎 a vyberte fotku z vašeho zařízení."
                    # )
                else:
                    # Provide guidance
                    if current_question_index == 0:
                        await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!")
                        # await self.bot.send_message(
                        #     msg.chat.id,
                        #     "Použijte /start pro zahájení konzultace nebo /help pro nápovědu."
                        # )
                    else:
                        # welcome_text = (
                        #     f"Máte nedokončenou konzultaci (otázka {current_question_index + 1}/{total_questions}). "
                        #     "Klikněte na tlačítko pro pokračování."
                        # )
                        keyboard = self.create_continue_keyboard()
                        # await self.bot.send_message(
                        #     msg.chat.id,
                        #     welcome_text,
                        #     reply_markup=keyboard
                        # )
                        await self.bot.send_message(msg.chat.id, "✅ SWITCHING TO ASSISTANT!", reply_markup=keyboard)

            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(f"Error in handle_message: {e}\nFull traceback:\n{tb}")
                await self.bot.send_message(
                    msg.chat.id,
                    "😔 Došlo k chybě. Zkuste to prosím znovu nebo použijte /help."
                )

    async def _handle_skip_photo(self, chat_id: int, user_id: int, question_index: int):
        """Handle skipping photo upload"""
        question = self.question_manager.get_question(question_index)
        
        # Save None as answer for skipped photo
        self.db.save_answer(
            user_id=user_id,
            question_index=question_index,
            question_text=question.text,
            answer_text="None",  # Store None as string
            answer_type='photo'
        )
        
        # Clear waiting state
        self.waiting_for_photo.discard(user_id)
        
        await self.bot.send_message(chat_id, "⏭️ Fotografie přeskočena")
        
        # Send next question
        next_question_index = question_index + 1
        await self._send_question(chat_id, user_id, next_question_index)

    async def _handle_skip_followup(self, chat_id: int, user_id: int, question_index: int):
        """Handle skipping follow-up question"""
        # Save None as followup text
        self.db.save_followup_answer(user_id, question_index, "None")
        
        # Clear waiting state
        self.waiting_for_followup.discard(user_id)
        
        await self.bot.send_message(chat_id, "⏭️ Doplňující informace přeskočeny")
        
        # Continue to next question
        next_question_index = question_index + 1
        await self._send_question(chat_id, user_id, next_question_index)

    async def _handle_skip_text(self, chat_id: int, user_id: int, question_index: int):
        """Handle skipping text answer"""
        question = self.question_manager.get_question(question_index)
        
        # Save None as answer for skipped text question
        self.db.save_answer(
            user_id=user_id,
            question_index=question_index,
            question_text=question.text,
            answer_text="None",
            answer_type='text'
        )
        
        # Clear waiting state
        self.waiting_for_answer.discard(user_id)
        
        await self.bot.send_message(chat_id, "⏭️ Otázka přeskočena")
        
        # Send next question
        next_question_index = question_index + 1
        await self._send_question(chat_id, user_id, next_question_index)

    async def _send_question(self, chat_id: int, user_id: int, question_index: int):
        """Send a specific question to the user with appropriate keyboard"""
        total_questions = self.question_manager.get_total_questions()
        
        if question_index >= total_questions:
            await self._complete_questionnaire(chat_id, user_id)
            return
        
        await self._invalidate_old_question_message(chat_id, user_id)

        question = self.question_manager.get_question(question_index)
        question_text = self.question_manager.get_question_text_with_options(question_index)
        
        # Add progress indicator
        progress_text = f"📊 *Otázka {question_index + 1}/{total_questions}*\n\n{question_text}"
        
        # Determine if we need keyboard
        keyboard = None
        if question.question_type == QuestionType.YES_NO:
            keyboard = self.create_yes_no_keyboard(question_index)
        elif question.question_type == QuestionType.PHOTO:
            keyboard = self.create_photo_skip_keyboard(question_index)
            progress_text += "\n\n⏭️ _Můžete přeskočit kliknutím na tlačítko níže_"
        elif question.question_type in [QuestionType.TEXT, QuestionType.CHOICE, QuestionType.SCALE]:
            # NEW: Add skip button for text-based questions
            keyboard = self.create_text_skip_keyboard(question_index)
            progress_text += "\n\n⏭️ _Můžete přeskočit kliknutím na tlačítko níže_"
        
        sent_message = await self.bot.send_message(
            chat_id,
            progress_text,
            parse_mode="MARKDOWN",
            reply_markup=keyboard
        )

        # STORE NEW MESSAGE ID
        if keyboard:  # Only store messages with keyboards
            self.db.save_user_message(user_id, sent_message.message_id, 'question')
        
        # Set appropriate waiting state
        if question.question_type == QuestionType.PHOTO:
            self.waiting_for_photo.add(user_id)
        elif question.question_type != QuestionType.YES_NO:  # For yes/no, we wait for callback
            self.waiting_for_answer.add(user_id)

    async def _process_keyboard_answer(self, chat_id: int, user_id: int, question_index: int, answer: str):
        """Process answer from keyboard button"""
        question = self.question_manager.get_question(question_index)
        
        # Save answer
        self.db.save_answer(
            user_id=user_id,
            question_index=question_index,
            question_text=question.text,
            answer_text=answer
        )
        
        # Check if we need followup for YES answers
        if (question.question_type == QuestionType.YES_NO and 
            answer == "Ano" and 
            question.has_followup):

            # INVALIDATE CURRENT MESSAGE (the yes/no question)
            # await self._invalidate_old_question_message(chat_id, user_id)
            
            # Set followup state
            self.db.set_waiting_for_followup(user_id, question_index)
            self.waiting_for_followup.add(user_id)
            
            followup_text = question.followup_text
            keyboard = self.create_followup_skip_keyboard(question_index)
            message_text = f"💬 {followup_text}\n\n⏭️ _Můžete přeskočit kliknutím na tlačítko níže_"
            
            sent_message = await self.bot.send_message(
                chat_id, 
                message_text,
                parse_mode="MARKDOWN",
                reply_markup=keyboard
            )
            self.db.save_user_message(user_id, sent_message.message_id, 'question')
        else:
            # No followup needed, advance to next question
            next_question_index = question_index + 1
            await self._send_question(chat_id, user_id, next_question_index)

    async def _process_answer(self, chat_id: int, user_id: int, question_index: int, answer: str):
        """Process user's answer to a question"""
        question = self.question_manager.get_question(question_index)
        
        # Validate answer
        is_valid, processed_answer = self.question_manager.validate_answer(question_index, answer)
        
        if not is_valid:
            await self.bot.send_message(chat_id, f"❌ {processed_answer}")
            return
        
        # Save answer
        self.db.save_answer(
            user_id=user_id,
            question_index=question_index,
            question_text=question.text,
            answer_text=processed_answer
        )
        
        # Clear waiting state
        self.waiting_for_answer.discard(user_id)
        
        await self.bot.send_message(chat_id, "✅ Odpověď uložena!")
        next_question_index = question_index + 1
        await self._send_question(chat_id, user_id, next_question_index)

    async def _complete_questionnaire(self, chat_id: int, user_id: int):
        """Complete the questionnaire for user"""
        self.db.mark_questionnaire_completed(user_id)
        self._clear_user_states(user_id)
        
        completion_text = """
🎉 *Gratulujeme! Kosmetická konzultace je dokončena!*

Děkujeme za váš čas a upřímné odpovědi.
Vaše data byla uložena.

📋 Použijte /results pro zobrazení odpovědí
🔄 Použijte /restart pro novou konzultaci
        """
        
        await self.bot.send_message(chat_id, completion_text, parse_mode="MARKDOWN")

    def _clear_user_states(self, user_id: int):
        """Clear all user states"""
        self.waiting_for_answer.discard(user_id)
        self.waiting_for_photo.discard(user_id)
        self.waiting_for_followup.discard(user_id)
        # Clear stored message IDs
        self.db.clear_user_messages(user_id, 'question')

    def _split_message(self, text: str, max_length: int = 4000) -> List[str]:
        """Split long message into smaller parts"""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        while text:
            if len(text) <= max_length:
                parts.append(text)
                break
            
            split_pos = text.rfind('\n', 0, max_length)
            if split_pos == -1:
                split_pos = max_length
            
            parts.append(text[:split_pos])
            text = text[split_pos:].lstrip('\n')
        
        return parts
    
    async def _invalidate_old_question_message(self, chat_id: int, user_id: int):
        """Invalidate old question message keyboard"""
        try:
            # Get last message ID from database
            last_message_id = self.db.get_user_last_message(user_id, 'question')
            
            if last_message_id:
                try:
                    # Option 1: Remove keyboard only (recommended)
                    # await self.bot.edit_message_reply_markup(
                    #     chat_id=chat_id,
                    #     message_id=last_message_id,
                    #     reply_markup=None
                    # )
                    
                    # Option 2: Delete entire message (uncomment if preferred)
                    await self.bot.delete_message(chat_id, last_message_id)
                    
                except Exception as e:
                    # Message might be too old or already deleted
                    self.logger.debug(f"Could not edit/delete message {last_message_id}: {e}")
                
        except Exception as e:
            self.logger.error(f"Error invalidating old message: {e}")

# Usage example
if __name__ == "__main__":
    # Configuration
    QUESTIONS_FILE = "questions.json"
    DB_PATH = "db/questionnaire.db"
    
    # Initialize and run bot
    try:
        bot = SkinCareQuestionnaireBot(
            bot_token=BOT_TOKEN,
            questions_file=QUESTIONS_FILE,
            db_path=DB_PATH
        )
        bot.run_bot()
    except Exception as e:
        print(f"Failed to start bot: {e}")
        print("Make sure you've set your BOT_TOKEN correctly!")