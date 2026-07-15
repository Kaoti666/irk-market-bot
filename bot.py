import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                            InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove)

# === НАСТРОЙКА ===
TOKEN = "8914164722:AAHXa2MhYp98fSFUS_hocfewwXW_-lknD5M"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# === НАСТОЯЩАЯ БАЗА ДАННЫХ (SQLite) ===
DB_FILE = "/data/market_base.db"

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

# Шаги для продавца (FSM)
class SellSteps(StatesGroup):
    city = State()
    photo = State()
    desc = State()
    price = State()
    phone = State()

# Шаги для покупателя (FSM)
class BuySteps(StatesGroup):
    city = State()

# Инлайн-кнопка отмены на промежуточных шагах
def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])

# Главное меню
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Купить"), KeyboardButton(text="📦 Продать")],
            [KeyboardButton(text="❌ Мои объявления")]
        ],
        resize_keyboard=True
    )

# Клавиатура выбора городов
def cities_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Иркутск"), KeyboardButton(text="Тайшет")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Старт бота
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я надежный бот для торговли в Иркутске и Тайшете.\n"
        "Здесь всё сохраняется в базу данных и работает по номерам телефонов!",
        reply_markup=main_menu()
    )

# Сброс шагов при отмене
@dp.callback_query(F.data == "cancel_action")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Действие отменено")
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=main_menu())

# ================= ВЕТКА ПРОДАТЬ =================
@dp.message(F.text == "📦 Продать")
async def start_sell(message: types.Message, state: FSMContext):
    await message.answer("📍 Шаг 1: Выберите ваш город на кнопках:", reply_markup=cities_menu())
    await state.set_state(SellSteps.city)

@dp.message(SellSteps.city, F.text.in_({"Иркутск", "Тайшет"}))
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("📸 Шаг 2: Отправьте ФОТОГРАФИЮ товара:", reply_markup=get_cancel_kb())
    await state.set_state(SellSteps.photo)

@dp.message(SellSteps.city)
async def bad_city_sell(message: types.Message):
    await message.answer("⚠️ Пожалуйста, выберите город кнопкой (Иркутск или Тайшет):", reply_markup=cities_menu())

@dp.message(SellSteps.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
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
        await message.answer("❌ Введите цену только цифрами (например, 1500):", reply_markup=get_cancel_kb())
        return
    await state.update_data(price=message.text)
    
    # Кнопка для быстрой отправки номера телефона
    phone_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить свой номер", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("📞 Шаг 5: Отправьте ваш номер телефона кнопкой ниже или напишите его вручную:", reply_markup=phone_kb)
    await state.set_state(SellSteps.phone)

# Ловим номер телефона (и через кнопку контакта, и текстом)
@dp.message(SellSteps.phone, F.contact | F.text)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text.strip()
        
    user_data = await state.get_data()
    
    # Сохраняем в реальную базу данных SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (user_id, city, photo, desc, price, phone) VALUES (?, ?, ?, ?, ?, ?)",
        (message.from_user.id, user_data['city'], user_data['photo'], user_data['desc'], user_data['price'], phone)
    )
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("🎉 Товар успешно сохранен в базу данных и выставлен!", reply_markup=main_menu())

# ================= ВЕТКА КУПИТЬ =================
@dp.message(F.text == "🛍 Купить")
async def start_buy(message: types.Message, state: FSMContext):
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
        
        # Кнопка для быстрого звонка или перехода в чат, если номер кликабельный
        await message.answer_photo(photo=photo, caption=caption, reply_markup=main_menu())

@dp.message(BuySteps.city)
async def bad_city_buy(message: types.Message):
    await message.answer("⚠️ Пожалуйста, выберите город кнопкой (Иркутск или Тайшет):", reply_markup=cities_menu())

# ================= ОТКАТ И УДАЛЕНИЕ ОБЪЯВЛЕНИЙ =================
@dp.message(F.text == "❌ Мои объявления")
async def show_my_products(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, desc, price, city FROM products WHERE user_id = ?", (message.from_user.id,))
    my_items = cursor.fetchall()
    conn.close()
    
    if not my_items:
        await message.answer(" у вас пока нет активных объявлений.", reply_markup=main_menu())
        return
        
    await message.answer("📋 Ваши товары в базе данных:")
    for item in my_items:
        db_id, desc, price, city = item
        text = f"🏙 Город: {city}\n📄 {desc}\n💰 Цена: {price} руб."
        
        # Инлайн-кнопка для моментального удаления товара из БЗ
        del_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить это объявление", callback_data=f"del_{db_id}")]
        ])
        await message.answer(text, reply_markup=del_kb)

# Обработчик нажатия на кнопку удаления
@dp.callback_query(F.data.startswith("del_"))
async def delete_product(callback: types.CallbackQuery):
    product_id = callback.data.split("_")[1]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    
    await callback.message.delete() # Удаляем саму карточку из чата ТГ
    await callback.answer("Объявление удалено из БЗ!")

async def main():
    print("🚀 Бот успешно запущен и подключен к SQLite базе данных!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
