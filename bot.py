import asyncio
import logging
import os
import requests
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
else:
    bot = None
    dp = None

users_data = {}

class ProfileStates(StatesGroup):
    waiting_for_weight = State()
    waiting_for_height = State()
    waiting_for_age = State()
    waiting_for_activity = State()
    waiting_for_city = State()
    waiting_for_calorie_goal = State()

class FoodStates(StatesGroup):
    waiting_for_food_name = State()
    waiting_for_food_weight = State()

router = Router()

def get_weather_temperature(city):
    if not OPENWEATHER_API_KEY:
        return 20.0  # default temperature if no API key
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data['main']['temp']
        else:
            logger.warning(f"Failed to get weather data: {response.status_code}")
            return 20.0
    except Exception as e:
        logger.error(f"Error getting weather data: {e}")
        return 20.0

def calculate_water_goal(user_data):
    weight = user_data.get('weight', 70)
    activity = user_data.get('activity', 30)
    city = user_data.get('city', 'Moscow')
    
    base_water = weight * 30
    
    activity_water = (activity // 30) * 500
    
    temperature = get_weather_temperature(city)
    weather_water = 0
    if temperature > 25:
        weather_water = 750
    
    return base_water + activity_water + weather_water

def calculate_calorie_goal(user_data):
    weight = user_data.get('weight', 70)
    height = user_data.get('height', 170)
    age = user_data.get('age', 30)
    activity = user_data.get('activity', 30)
    
    bmr = 10 * weight + 6.25 * height - 5 * age + 5  # for men, +5; for women, -161
    
    if activity < 30:
        activity_multiplier = 1.2  # sedentary
    elif activity < 60:
        activity_multiplier = 1.375  # lightly active
    elif activity < 90:
        activity_multiplier = 1.55  # moderately active
    elif activity < 120:
        activity_multiplier = 1.725  # very active
    else:
        activity_multiplier = 1.9  # extra active
    
    activity_calories = (activity // 30) * 200
    
    return int(bmr * activity_multiplier) + activity_calories

def get_food_calories(food_name):
    food_db = {
        'банан': {'name': 'Банан', 'calories_per_100g': 89, 'unit': 'г'},
        'яблоко': {'name': 'Яблоко', 'calories_per_100g': 52, 'unit': 'г'},
        'гречка': {'name': 'Гречка', 'calories_per_100g': 132, 'unit': 'г'},
        'рис': {'name': 'Рис', 'calories_per_100g': 130, 'unit': 'г'},
        'курица': {'name': 'Курица', 'calories_per_100g': 165, 'unit': 'г'},
        'говядина': {'name': 'Говядина', 'calories_per_100g': 250, 'unit': 'г'}
    }
    
    try:
        url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={food_name}&json=true"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('products'):
                product = data['products'][0]
                
                product_name = product.get('product_name', food_name.capitalize())
                
                nutrients = product.get('nutriments', {})
                calories_per_100g = nutrients.get('energy-kcal_100g')
                
                if not calories_per_100g and 'energy_100g' in nutrients:
                    energy_kj = nutrients.get('energy_100g')
                    if energy_kj:
                        calories_per_100g = round(energy_kj / 4.184)
                
                if calories_per_100g:
                    return {
                        'name': product_name,
                        'calories_per_100g': int(calories_per_100g),
                        'unit': 'г'
                    }
        
        if food_name.lower() in food_db:
            return food_db[food_name.lower()]
        
        for key, value in food_db.items():
            if food_name.lower() in key or key in food_name.lower():
                return value
        
        return {'name': food_name.capitalize(), 'calories_per_100g': 100, 'unit': 'г'}
        
    except Exception as e:
        logger.error(f"Error getting food calories for {food_name}: {e}")
        if food_name.lower() in food_db:
            return food_db[food_name.lower()]
        
        for key, value in food_db.items():
            if food_name.lower() in key or key in food_name.lower():
                return value
        
        return {'name': food_name.capitalize(), 'calories_per_100g': 100, 'unit': 'г'}

def calculate_workout_calories(workout_type, duration):
    workout_calories = {
        'бег': 10,
        'беговые лыжи': 12,
        'велосипед': 8,
        'плавание': 10,
        'йога': 4,
        'тренажерный зал': 7,
        'ходьба': 5,
        'футбол': 8,
        'баскетбол': 9
    }
    
    calories_per_minute = 7
    for key, value in workout_calories.items():
        if key in workout_type.lower():
            calories_per_minute = value
            break
    
    return calories_per_minute * duration

def calculate_workout_water(workout_type, duration):
    workout_water = {
        'бег': 200,
        'беговые лыжи': 250,
        'велосипед': 150,
        'плавание': 100,
        'йога': 100,
        'тренажерный зал': 200,
        'ходьба': 100,
        'футбол': 200,
        'баскетбол': 200
    }
    
    water_per_30min = 200
    for key, value in workout_water.items():
        if key in workout_type.lower():
            water_per_30min = value
            break
    
    return (duration // 30) * water_per_30min


@router.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "Привет! Я бот для отслеживания воды, калорий и активности.\n\n"
        "Доступные команды:\n"
        "/set_profile - Настроить профиль\n"
        "/log_water <мл> - Записать выпитую воду\n"
        "/log_food <название> - Записать прием пищи\n"
        "/log_workout <тип> <минуты> - Записать тренировку\n"
        "/check_progress - Проверить прогресс\n"
        "/help - Показать справку"
    )
    await message.answer(welcome_text)

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "Я помогаю следить за водным балансом, калориями и активностью.\n\n"
        "Как пользоваться:\n"
        "1. Настройте профиль командой /set_profile\n"
        "2. Записывайте выпитую воду командой /log_water <мл>\n"
        "3. Записывайте приемы пищи командой /log_food <название>\n"
        "4. Записывайте тренировки командой /log_workout <тип> <минуты>\n"
        "5. Проверяйте прогресс командой /check_progress\n"
    )
    await message.answer(help_text)

@router.message(Command("set_profile"))
async def cmd_set_profile(message: Message, state: FSMContext):
    user_id = message.from_user.id
    users_data[user_id] = {}
    await message.answer("Введите ваш вес (в кг):")
    await state.set_state(ProfileStates.waiting_for_weight)

@router.message(ProfileStates.waiting_for_weight, F.text.regexp(r'^\d+(\.\d+)?$'))
async def process_weight(message: Message, state: FSMContext):
    """Process weight input"""
    try:
        weight = float(message.text)
        user_id = message.from_user.id
        users_data[user_id]['weight'] = weight
        await message.answer("Введите ваш рост (в см):")
        await state.set_state(ProfileStates.waiting_for_height)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для веса:")

@router.message(ProfileStates.waiting_for_height, F.text.regexp(r'^\d+(\.\d+)?$'))
async def process_height(message: Message, state: FSMContext):
    """Process height input"""
    try:
        height = float(message.text)
        user_id = message.from_user.id
        users_data[user_id]['height'] = height
        await message.answer("Введите ваш возраст:")
        await state.set_state(ProfileStates.waiting_for_age)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для роста:")

@router.message(ProfileStates.waiting_for_age, F.text.regexp(r'^\d+$'))
async def process_age(message: Message, state: FSMContext):
    """Process age input"""
    try:
        age = int(message.text)
        user_id = message.from_user.id
        users_data[user_id]['age'] = age
        await message.answer("Сколько минут активности у вас в день?")
        await state.set_state(ProfileStates.waiting_for_activity)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное целое число для возраста:")

@router.message(ProfileStates.waiting_for_activity, F.text.regexp(r'^\d+$'))
async def process_activity(message: Message, state: FSMContext):
    """Process activity input"""
    try:
        activity = int(message.text)
        user_id = message.from_user.id
        users_data[user_id]['activity'] = activity
        await message.answer("В каком городе вы находитесь?")
        await state.set_state(ProfileStates.waiting_for_city)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное целое число для активности:")

@router.message(ProfileStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    """Process city input and calculate goals"""
    city = message.text
    user_id = message.from_user.id
    users_data[user_id]['city'] = city
    
    # calculate goals
    water_goal = calculate_water_goal(users_data[user_id])
    calorie_goal = calculate_calorie_goal(users_data[user_id])
    
    users_data[user_id]['water_goal'] = water_goal
    users_data[user_id]['calorie_goal'] = calorie_goal
    
    # initialize tracking values
    users_data[user_id]['logged_water'] = 0
    users_data[user_id]['logged_calories'] = 0
    users_data[user_id]['burned_calories'] = 0
    
    await message.answer(
        f"Профиль успешно настроен!\n\n"
        f"Ваша цель по воде: {water_goal} мл\n"
        f"Ваша цель по калориям: {calorie_goal} ккал\n\n"
        f"Теперь вы можете начать отслеживание!"
    )
    await state.clear()

@router.message(Command("log_water"))
async def cmd_log_water(message: Message, command: CommandObject):
    """Log water consumption"""
    user_id = message.from_user.id
    
    if user_id not in users_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile")
        return
    
    if not command.args:
        await message.answer("Укажите количество воды в мл. Пример: /log_water 250")
        return
    
    try:
        amount = int(command.args)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное положительное число. Пример: /log_water 250")
        return
    
    if 'logged_water' not in users_data[user_id]:
        users_data[user_id]['logged_water'] = 0
    
    users_data[user_id]['logged_water'] += amount
    
    water_goal = users_data[user_id].get('water_goal', 2000)
    logged_water = users_data[user_id]['logged_water']
    
    remaining = max(0, water_goal - logged_water)
    
    response = f"Записано: {amount} мл воды\n"
    response += f"Всего выпито: {logged_water} мл из {water_goal} мл\n"
    if remaining > 0:
        response += f"Осталось выпить: {remaining} мл"
    else:
        response += "Вы выполнили норму воды на сегодня!"
    
    await message.answer(response)

@router.message(Command("log_food"))
async def cmd_log_food(message: Message, state: FSMContext):
    """Start food logging process"""
    user_id = message.from_user.id
    
    if user_id not in users_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile")
        return
    
    if message.text.strip() != "/log_food":
        food_name = message.text[len("/log_food "):].strip()
        if food_name:
            await state.update_data(food_name=food_name)
            await message.answer(f"{food_name.capitalize()} - сколько грамм вы съели?")
            await state.set_state(FoodStates.waiting_for_food_weight)
            return
    
    await message.answer("Что вы съели?")
    await state.set_state(FoodStates.waiting_for_food_name)

@router.message(FoodStates.waiting_for_food_name)
async def process_food_name(message: Message, state: FSMContext):
    """Process food name input"""
    food_name = message.text
    await state.update_data(food_name=food_name)
    await message.answer(f"{food_name} - сколько грамм вы съели?")
    await state.set_state(FoodStates.waiting_for_food_weight)

@router.message(FoodStates.waiting_for_food_weight, F.text.regexp(r'^\d+(\.\d+)?$'))
async def process_food_weight(message: Message, state: FSMContext):
    """Process food weight and log food"""
    try:
        weight = float(message.text)
        if weight <= 0:
            raise ValueError("Weight must be positive")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное положительное число для веса:")
        return
    
    user_data = await state.get_data()
    food_name = user_data.get('food_name', 'Еда')
    food_info = get_food_calories(food_name)
    calories_per_100g = food_info['calories_per_100g']
    food_display_name = food_info['name']
    
    calories = round((calories_per_100g * weight) / 100, 1)
    
    user_id = message.from_user.id
    
    if 'logged_calories' not in users_data[user_id]:
        users_data[user_id]['logged_calories'] = 0
    
    users_data[user_id]['logged_calories'] += calories
    
    response = f"{food_display_name} - {calories} ккал ({weight} г)"
    await message.answer(f"Записано: {response}")
    
    await state.clear()

@router.message(Command("log_workout"))
async def cmd_log_workout(message: Message, command: CommandObject):
    """Log workout activity"""
    user_id = message.from_user.id
    
    if user_id not in users_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile")
        return
    
    if not command.args:
        await message.answer("Укажите тип тренировки и время. Пример: /log_workout бег 30")
        return
    
    args = command.args.split()
    if len(args) < 2:
        await message.answer("Укажите тип тренировки и время. Пример: /log_workout бег 30")
        return
    
    workout_type = " ".join(args[:-1])
    try:
        duration = int(args[-1])
        if duration <= 0:
            raise ValueError("Duration must be positive")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное положительное число для времени. Пример: /log_workout бег 30")
        return
    
    calories_burned = calculate_workout_calories(workout_type, duration)
    water_needed = calculate_workout_water(workout_type, duration)
    if 'burned_calories' not in users_data[user_id]:
        users_data[user_id]['burned_calories'] = 0
    
    users_data[user_id]['burned_calories'] += calories_burned
    if water_needed > 0:
        if 'logged_water' not in users_data[user_id]:
            users_data[user_id]['logged_water'] = 0
        users_data[user_id]['logged_water'] -= water_needed
    
    response = f"{workout_type.capitalize()} {duration} минут - {calories_burned} ккал"
    if water_needed > 0:
        response += f"\nРекомендуется выпить дополнительно: {water_needed} мл воды"
    
    await message.answer(response)


@router.message(Command("check_progress"))
async def cmd_check_progress(message: Message):
    """Show user progress"""
    user_id = message.from_user.id
    
    if user_id not in users_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile")
        return
    
    user_data = users_data[user_id]
    
    # get goals
    water_goal = user_data.get('water_goal', 2000)
    calorie_goal = user_data.get('calorie_goal', 2000)
    
    logged_water = user_data.get('logged_water', 0)
    logged_calories = user_data.get('logged_calories', 0)
    burned_calories = user_data.get('burned_calories', 0)
    
    water_remaining = max(0, water_goal - logged_water)
    calorie_balance = logged_calories - burned_calories
    calories_remaining = max(0, calorie_goal - calorie_balance)
    
    response = "Прогресс:\n\n"
    
    response += "Вода:\n"
    response += f"- Выпито: {logged_water} мл из {water_goal} мл\n"
    if water_remaining > 0:
        response += f"- Осталось: {water_remaining} мл\n"
    else:
        response += "- Норма выполнена!\n"
    
    response += "\n"
    
    response += "Калории:\n"
    response += f"- Потреблено: {logged_calories} ккал\n"
    response += f"- Сожжено: {burned_calories} ккал\n"
    response += f"- Баланс: {calorie_balance} ккал из {calorie_goal} ккал\n"
    if calories_remaining > 0:
        response += f"- Осталось: {calories_remaining} ккал\n"
    else:
        response += "- Норма выполнена!\n"
    
    await message.answer(response)

async def main():
    dp.include_router(router)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
