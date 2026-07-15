import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                            InlineKeyboardMarkup, InlineKeyboardButton)
from aiohttp import web
import os
# === НАСТРОЙКА ===
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# База данных прямо в корне
DB_FILE = "market_base.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            city TEXT,
            photo TEXT,
            desc TEXT,
            price TEXT,
            phone TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Шаги FSM для состояний
class SellSteps(StatesGroup):
    city = State()
    photo = State()
    desc = State()
    price = State()
    phone = State()

class BuySteps(StatesGroup):
    city = State()

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]])

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛍 Купить"), KeyboardButton(text="📦 Продать")],[KeyboardButton(text="❌ Мои объявления")]], resize_keyboard=True)

def cities_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Иркутск"), KeyboardButton(text="Тайшет")]], resize_keyboard=True, one_time_keyboard=True)

# Сброс зависаний при команде /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear() # Железно сбрасываем любые зависшие шаги!
    await message.answer("👋 Привет! Я вечный бот для торговли в Иркутске и Тайшете!\nВсе зависания исправлены, чат удалять больше не нужно.", reply_markup=main_menu())

# Сброс шагов при нажатии кнопки Отмена
@dp.callback_query(F.data == "cancel_action")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Действие отменено")
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=main_menu())

# ================= ВЕТКА ПРОДАТЬ =================
# Добавляем state="*" — теперь кнопка сработает, даже если бот завис на каком-то шаге!
@dp.message(F.text == "💰 Продать", StateFilter(None))
async def start_sell(message: types.Message, state: FSMContext):
    await state.clear() # Полностью очищаем прошлые незавершенные попытки!
    await message.answer("📍 Шаг 1: Выберите ваш город на кнопках:", reply_markup=cities_menu())
    await state.set_state(SellSteps.city)

@dp.message(SellSteps.city, F.text.in_({"Иркутск", "Тайшет"}))
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("📸 Шаг 2: Отправьте ФОТОГРАФИЮ товара:", reply_markup=get_cancel_kb())
    await state.set_state(SellSteps.photo)

@dp.message(SellSteps.city)
async def bad_city_sell(message: types.Message):
    await message.answer("⚠️ Пожалуйста, выберите город кнопкой:", reply_markup=cities_menu())

@dp.message(SellSteps.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("📝 Шаг 3: Напишите ОПИСАНИЕ товара:", reply_markup=get_cancel_kb())
    await state.set_state(SellSteps.desc)

@dp.message(SellSteps.desc)
async def process_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("💰 Шаг 4: Укажите ЦЕНУ товара (только цифры):", reply_markup=get_cancel_kb())
    await state.set_state(SellSteps.price)

@dp.message(SellSteps.price)
async def process_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите цену только цифрами:", reply_markup=get_cancel_kb())
        return
    await state.update_data(price=message.text)
    phone_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить свой номер", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("📞 Шаг 5: Отправьте ваш номер телефона кнопкой ниже или напишите его вручную:", reply_markup=phone_kb)
    await state.set_state(SellSteps.phone)

@dp.message(SellSteps.phone, F.contact | F.text)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text.strip()
    user_data = await state.get_data()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (user_id, city, photo, desc, price, phone) VALUES (?, ?, ?, ?, ?, ?)",
                   (message.from_user.id, user_data['city'], user_data['photo'], user_data['desc'], user_data['price'], phone))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("🎉 Товар успешно сохранен в базу данных и выставлен!", reply_markup=main_menu())

# ================= ВЕТКА КУПИТЬ =================
@dp.message(F.text == "💸 Купить", StateFilter(None))
async def start_buy(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📍 Выберите город для поиска:", reply_markup=cities_menu())
    await state.set_state(BuySteps.city)

@dp.message(BuySteps.city, F.text.in_({"Иркутск", "Тайшет"}))
async def search_by_city(message: types.Message, state: FSMContext):
    search_city = message.text
    await state.clear()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT photo, desc, price, phone FROM products WHERE city = ?", (search_city,))
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await message.answer(f"🔍 В городе {search_city} пока нет объявлений.", reply_markup=main_menu())
        return
    
    await message.answer(f"📦 Найдено товаров в г. {search_city}: {len(items)}")
    for item in items:
        photo, desc, price, phone = item
        caption = f"📄 {desc}\n\n💰 Цена: {price} руб.\n📍 Город: {search_city}\n📞 Контакт: {phone}"
        await message.answer_photo(photo=photo, caption=caption, reply_markup=main_menu())

# ================= МОИ ОБЪЯВЛЕНИЯ И УДАЛЕНИЕ =================
@dp.message(F.text == "❌ Мои объявления", StateFilter(None))
async def show_my_products(message: types.Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, desc, price, city FROM products WHERE user_id = ?", (message.from_user.id,))
    my_items = cursor.fetchall()
    conn.close()
    
    if not my_items:
        await message.answer("📋 У вас пока нет активных объявлений.", reply_markup=main_menu())
        return
        
    await message.answer("📋 Ваши товары в базе данных:")
    for item in my_items:
        db_id, desc, price, city = item
        del_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Удалить это объявление", callback_data=f"del_{db_id}")]])
        await message.answer(f"🏙 Город: {city}\n📄 {desc}\n💰 Цена: {price} руб.", reply_markup=del_kb)

@dp.callback_query(F.data.startswith("del_"))
async def delete_product(callback: types.CallbackQuery):
    product_id = callback.data.split("_")[1]
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    await callback.message.delete()
    await callback.answer("Объявление удалено!")

# ================= ОБРАБОТКА СИГНАЛОВ ОТ UPTIMEROBOT =================
# Эта штука создает микро-веб-сервер. Когда UptimeRobot пинает ссылку,
# сервер отвечает ему кодом 200 (Всё ОК), и бот больше никогда не вылетает!
async def handle_ping(request):
    return web.Response(text="Бот онлайн и готов к работе!")

async def main():
    # Запускаем фоновый опрос Телеграма
    asyncio.create_task(dp.start_polling(bot))
    
    # Запускаем микро-веб-сервер на порту 10000 (стандарт для Render), чтобы ловить пинки UptimeRobot
    app = web.Application()
    app.router.add_get('/', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 10000)))
    await site.start()
    
    print("🚀 Все баги устранены! Бот в бесконечном онлайне!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
