import os
import requests
import fitz
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from config import TELEGRAM_BOT_TOKEN, OPENAI_API_KEY
from bs4 import BeautifulSoup

def fetch_program_info(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    content = soup.get_text(separator=' ', strip=True)
    return content

# URLs программ
ai_url = "https://abit.itmo.ru/program/master/ai"
ai_product_url = "https://abit.itmo.ru/program/master/ai_product"

# Извлечение информации
ai_info = fetch_program_info(ai_url)
ai_product_info = fetch_program_info(ai_product_url)

# --- Константы ---
AI_URL = "https://api.itmo.su/constructor-ep/api/v1/static/programs/10033/plan/abit/pdf"
AI_PRODUCT_URL = "https://api.itmo.su/constructor-ep/api/v1/static/programs/10130/plan/abit/pdf"
DATA_DIR = "data"

# --- Инициализация OpenAI ---
openai.api_key = OPENAI_API_KEY

# --- Скачивание PDF (один раз при старте) ---
os.makedirs(DATA_DIR, exist_ok=True)


def download_pdf(url, path):
    if not os.path.exists(path):
        r = requests.get(url)
        with open(path, "wb") as f:
            f.write(r.content)


download_pdf(AI_URL, os.path.join(DATA_DIR, "AI.pdf"))
download_pdf(AI_PRODUCT_URL, os.path.join(DATA_DIR, "AI_Product.pdf"))


# --- Извлечение текста из PDF ---
def extract_text(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


ai_text = extract_text(os.path.join(DATA_DIR, "AI.pdf"))
ai_product_text = extract_text(os.path.join(DATA_DIR, "AI_Product.pdf"))

# --- Telegram Conversation States ---
ASK_BACKGROUND, ANSWER_QUESTIONS = range(2)


# --- Функции для LLM ---
def recommend_program(background: str):
    prompt = f"""
    У абитуриента следующий бэкграунд: "{background}".
    Есть две магистерские программы:
    1. AI - учебный план: {ai_text[:2000]}...
    2. AI Product - учебный план: {ai_product_text[:2000]}...

    Определи, какая программа лучше подходит этому абитуриенту. Ответь только названием программы: "AI" или "AI Product".
    """
    response = openai.chat.completions.create(
        model="o4-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return response.choices[0].message.content.strip()


def answer_question(question: str, program: str):
    if program == "AI":
        text = ai_text + ai_info
    else:
        text = ai_product_text + ai_product_info

    prompt = f"""
    Ты помощник по магистерской программе. Текст учебного плана:
    {text[:3000]}...

    Вопрос: "{question}"
    Ответь кратко и только по учебному плану.
    """
    response = openai.chat.completions.create(
        model="o4-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return response.choices[0].message.content.strip()


# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я помогу выбрать магистерскую программу. Расскажите немного о вашем бэкграунде."
    )
    return ASK_BACKGROUND


async def ask_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_bg = update.message.text
    context.user_data['background'] = user_bg

    program = recommend_program(user_bg)
    context.user_data['program'] = program

    await update.message.reply_text(f"Я рекомендую программу: {program}. Можете задавать вопросы по учебному плану.")
    return ANSWER_QUESTIONS


async def answer_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    program = context.user_data.get('program')

    answer = answer_question(question, program)
    await update.message.reply_text(answer)
    return ANSWER_QUESTIONS


# --- Setup Telegram Bot ---
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        ASK_BACKGROUND: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_background)],
        ANSWER_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, answer_questions)]
    },
    fallbacks=[]
)

app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(conv_handler)

if __name__ == "__main__":
    print("Бот запущен...")
    app.run_polling()
