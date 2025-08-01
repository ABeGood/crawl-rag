import os
from dotenv import load_dotenv
from openai import OpenAI
import logging
import json
from time import sleep
from telebot import custom_filters
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReactionTypeEmoji
from telegram.constants import ParseMode
from telebot.apihelper import ApiTelegramException

import asyncio

DEBUG = True

load_dotenv()
telegram_token = os.environ.get("TELEGRAM_TOKEN")

logging.basicConfig(
    level=logging.DEBUG, 
    filename='bot.log', 
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def format_telegram_message(response_data: dict) -> tuple[str, list[str]]:
    """
    Format response data for Telegram API with markdown-compatible formatting.
    
    Args:
        response_data (Dict[str, Any]): Dictionary containing response, sources, and images
        
    Returns:
        Tuple[str, List[str]]: (formatted_markdown_text, images_list)
    """
    
    # Extract main response text
    response_text = response_data.get('response', '')
    sources = response_data.get('sources', [])
    images = response_data.get('images', [])
    
    # Clean and format the response text for Telegram markdown
    formatted_response = escape_telegram_markdown(response_text)
    
    # Build the complete message
    message_parts = []
    
    # Add the main response
    if formatted_response:
        message_parts.append(formatted_response)
    
    # Add sources section if sources exist
    if sources:
        message_parts.append("\n\n*Источники:*")
        
        # Format each source as a markdown link on a new line
        for i, source in enumerate(sources, 1):
            if isinstance(source, str) and source.strip():
                # Extract domain name for display text
                display_text = extract_domain_name(source)
                # Format as Telegram-compatible markdown link
                link_text = f"[{display_text}]({source})"
                message_parts.append(f"{i}. {link_text}")
    
    # Join all parts
    final_message = "\n".join(message_parts)
    
    # Ensure images is a list
    images_list = images if isinstance(images, list) else []
    
    return final_message, images_list


def escape_telegram_markdown(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2 compatibility.
    
    Args:
        text (str): Original text to escape
        
    Returns:
        str: Escaped text compatible with Telegram
    """
    
    # First, convert headers (###, ##, #) to bold formatting
    text = convert_headers_to_bold(text)
    
    # Then, preserve existing markdown formatting by temporarily replacing it
    text = preserve_existing_markdown(text)
    
    # Escape special characters that could break Telegram parsing
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    # Note: Character escaping is commented out as it's not needed for current use case
    # for char in special_chars:
    #     text = text.replace(char, f'\\{char}')
    
    # Restore preserved markdown
    text = restore_preserved_markdown(text)
    
    return text


def convert_headers_to_bold(text: str) -> str:
    """Convert markdown headers (###, ##, #) to bold formatting.
    
    Args:
        text (str): Text with potential headers
    Returns:
        str: Text with headers converted to bold
    """
    import re
    
    # Store replacements to restore later
    replacements = {
        '**': '<<<BOLD>>>',
        '*': '<<<ITALIC>>>',
        '__': '<<<UNDERLINE>>>',
        '~~': '<<<STRIKE>>>',
        '`': '<<<CODE>>>',
    }
    
    # Temporarily replace existing markdown with placeholders
    for original, placeholder in replacements.items():
        text = text.replace(original, placeholder)
    
    # Pattern to match headers: 1-6 # symbols followed by space and text
    # Captures the header text without the # symbols
    header_pattern = r'^(#{1,6})\s+(.+)$'
    
    # Process each line
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        # Check if line is a header
        match = re.match(header_pattern, line.strip())
        if match:
            header_text = match.group(2).strip()
            # Convert to bold formatting
            processed_lines.append(f"**{header_text}**")
        else:
            processed_lines.append(line)
    
    # Rejoin lines
    result = '\n'.join(processed_lines)
    
    # Restore original markdown formatting
    for original, placeholder in replacements.items():
        result = result.replace(placeholder, original)
    
    return result


def restore_preserved_markdown(text: str) -> str:
    """
    Restore preserved markdown formatting.
    """
    
    # Restore replacements
    replacements = {
        '<<<BOLD>>>': '*',
        '<<<ITALIC>>>': '_',
        '<<<UNDERLINE>>>': '__',
        '<<<STRIKE>>>': '~',
        '<<<CODE>>>': '`',
    }
    
    for placeholder, original in replacements.items():
        text = text.replace(placeholder, original)
    
    return text


def preserve_existing_markdown(text: str) -> str:
    """
    Temporarily replace existing markdown with placeholders.
    """
    
    # Store replacements to restore later
    replacements = {
        '**': '<<<BOLD>>>',
        '*': '<<<ITALIC>>>',
        '__': '<<<UNDERLINE>>>',
        '~~': '<<<STRIKE>>>',
        '`': '<<<CODE>>>',
    }
    
    for original, placeholder in replacements.items():
        text = text.replace(original, placeholder)
    
    return text


class TelegramBot:
    bot : AsyncTeleBot

    def __init__(self, bot_token:str) -> None:
        self.bot = AsyncTeleBot(token=bot_token)
        self.admin_messages = {}

        self.logger = logging.getLogger(__name__)

        self.register_handlers()

    def run_bot(self):
        """Start the bot"""
        
        # Start bot polling
        self.logger.info("Starting bot...")
        try:
             asyncio.run(self.bot.polling(non_stop=True, timeout=60, request_timeout=90)) # Increased timeout
        except Exception as e:
            self.logger.error(f"Bot polling stopped due to an error: {e}")
            # You might want to add a retry mechanism here, e.g.,
            sleep(5)
            self.run_bot()


    def register_handlers(self):
        """Register all message handlers"""

        @self.bot.message_handler(
            func=lambda msg: msg.text is not None and '/' not in msg.text,
        )
        async def handle_message(msg):
            if msg.text == "Hi":
                await self.bot.send_message(msg.chat.id, "Hello!", parse_mode=ParseMode.MARKDOWN)
            else:
                try:
                    pass
                    
                except Exception as e:
                    await self.bot.send_message(msg.chat.id, f'Что-то отвалилось :(\n\n{e}')

                    if DEBUG:
                        try:
                            pass
                        except Exception as e:
                            pass

tg_bot = TelegramBot(bot_token=str(telegram_token))
tg_bot.run_bot()
