import json
import os
from anthropic import Anthropic
from typing import Dict, List, Any
import time
from pathlib import Path


def load_env_file():
    """
    Завантажує API ключ з .env файлу, якщо він існує
    """
    env_file = Path("src/.env")
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == 'ANTHROPIC_API_KEY' and value:
                        os.environ['ANTHROPIC_API_KEY'] = value
                        print("✓ API ключ завантажено з .env файлу")
                        return True
    return False


def translate_category(category: str, client: Anthropic) -> str:
    """
    Перекладає назву категорії з польської на українську через Claude API
    """
    prompt = (
        f"Переклади назву категорії з польської на українську: {category}. "
        f"Переклади лише загальні слова. Якщо слово є брендом (назва виробника або моделі), не перекладай його. "
        f"Визнач самостійно, що є брендом. Поверни тільки переклад без лапок чи пояснень."
    )

    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=100,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        translation = message.content[0].text.strip()
        print(f"  '{category}' → '{translation}'")
        return translation

    except Exception as e:
        print(f"  ⚠ Помилка перекладу '{category}': {e}")
        return category


def count_categories(data: List[Dict[str, Any]]) -> int:
    """
    Підраховує загальну кількість категорій у структурі
    """
    count = len(data)
    for item in data:
        if "children" in item and item["children"]:
            count += count_categories(item["children"])
    return count


def translate_category_structure(
    data: List[Dict[str, Any]],
    client: Anthropic,
    delay: float = 0.5,
    progress: dict = None
) -> List[Dict[str, Any]]:
    """
    Рекурсивно перекладає всі назви категорій у структурі
    """
    if progress is None:
        progress = {"current": 0, "total": 0}

    translated_data = []

    for item in data:
        # Створюємо копію елемента
        translated_item = item.copy()

        # Перекладаємо назву категорії
        if "name" in translated_item:
            progress["current"] += 1
            print(f"[{progress['current']}/{progress['total']}]", end=" ")

            original_name = translated_item["name"]
            translated_item["name"] = translate_category(original_name, client)

            # Затримка між запитами
            time.sleep(delay)

        # Рекурсивно обробляємо дочірні категорії
        if "children" in translated_item and translated_item["children"]:
            translated_item["children"] = translate_category_structure(
                translated_item["children"],
                client,
                delay,
                progress
            )

        translated_data.append(translated_item)

    return translated_data


def process_file(input_filename: str, output_filename: str, client: Anthropic):
    """
    Обробляє один JSON файл: читає, перекладає та зберігає результат
    """
    print(f"\n{'='*70}")
    print(f"📄 Обробка файлу: {input_filename}")
    print(f"{'='*70}")

    # Читаємо вхідний файл
    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ ПОМИЛКА: Файл {input_filename} не знайдено!")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ ПОМИЛКА: Некоректний JSON у файлі {input_filename}: {e}")
        return False

    # Підраховуємо категорії
    total_categories = count_categories(data)
    print(f"\n📊 Знайдено категорій: {total_categories}")
    print(f"\n🔄 Починаємо переклад...\n")

    # Перекладаємо структуру
    progress = {"current": 0, "total": total_categories}
    translated_data = translate_category_structure(data, client, progress=progress)

    # Зберігаємо результат
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(translated_data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"✅ Переклад завершено! Результат збережено у: {output_filename}")
    print(f"{'='*70}")

    return True


def main():
    """
    Головна функція для обробки всіх файлів
    """
    print("\n" + "="*70)
    print("🚀 СКРИПТ ПЕРЕКЛАДУ КАТЕГОРІЙ З ПОЛЬСЬКОЇ НА УКРАЇНСЬКУ")
    print("="*70 + "\n")

    # Спроба завантажити з .env файлу
    if not load_env_file():
        print("ℹ  Файл .env не знайдено або не містить API ключа")

    # Перевіряємо наявність API ключа
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n❌ ПОМИЛКА: Не встановлено API ключ!")
        print("\nСпособи встановлення API ключа:")
        print("1. Створіть файл .env та додайте: ANTHROPIC_API_KEY=your_key")
        print("2. Встановіть змінну середовища: set ANTHROPIC_API_KEY=your_key")
        return

    # Ініціалізуємо клієнт
    try:
        client = Anthropic(api_key=api_key)
        print("✓ Claude API клієнт ініціалізовано")
    except Exception as e:
        print(f"❌ ПОМИЛКА ініціалізації клієнта: {e}")
        return

    # Файли для обробки
    files_to_process = [
        # ("2.json", "2_1.json"),
        ("docs/3.json", "3_1.json"),
        # ("4.json", "4_1.json")
    ]

    success_count = 0
    total_files = len(files_to_process)

    # Обробляємо кожен файл
    for input_file, output_file in files_to_process:
        try:
            if process_file(input_file, output_file, client):
                success_count += 1
        except KeyboardInterrupt:
            print("\n\n⚠️  Переривання користувачем. Завершення роботи...")
            break
        except Exception as e:
            print(f"\n❌ Несподівана помилка при обробці {input_file}: {e}")
            continue

    # Підсумок
    print("\n" + "="*70)
    print(f"📈 ПІДСУМОК: Успішно оброблено {success_count} з {total_files} файлів")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
